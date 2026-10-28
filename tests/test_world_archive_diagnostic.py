"""Real Linux child/pipe regressions; these do not claim Windows execution."""
import base64
from contextlib import contextmanager, redirect_stdout
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import test_world_worker_archive_prefix as fixtures
from tools import world_worker_archive_prefix as archive
from tools import world_worker_dependencies as deps


PRIVATE_SENTINEL = 'DO_NOT_EMIT_PRIVATE_DIAGNOSTIC_SENTINEL'


class PipeProxy:
    def __init__(self, stream, *, fragmented=False, fail=False, fail_close=False):
        self.stream = stream
        self.fragmented = fragmented
        self.fail = fail
        self.fail_close = fail_close
        self.calls = 0

    def read(self, size=-1):
        self.calls += 1
        if self.fail:
            raise OSError(errno.EIO, '/private/runtime/' + PRIVATE_SENTINEL)
        if self.fragmented:
            cap = (1, 7, 511, 513)[(self.calls - 1) % 4]
            size = cap if size < 0 else min(size, cap)
        return self.stream.read(size)

    def close(self):
        self.stream.close()
        if self.fail_close:
            raise OSError(errno.EIO, '/private/runtime/' + PRIVATE_SENTINEL)

    def __getattr__(self, name):
        return getattr(self.stream, name)


class ArchiveDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ArchivePrefix.setUpClass()

    def setUp(self):
        self.fixture = fixtures.ArchivePrefix()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.cache = self.fixture.cache
        self.prefix = self.fixture.prefix
        self.pin = self.fixture.pins[0]
        self.package = self.pin['name']
        self.archive_path = self.cache / self.pin['filename']
        self.tar_bytes = subprocess.run(
            [self.fixture.zstd, '-q', '-d', '-c', '--', str(self.archive_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        self.cache_before = {path.name: path.read_bytes() for path in self.cache.iterdir()}

    @contextmanager
    def emitting_child(self, payload=b'', *, exit_code=0, stall=False, fail_read=False,
                       only_extraction=False):
        """Replace only the external decoder process; retain real tar/pipe logic."""
        real = archive.subprocess.Popen
        children = []
        invocations = 0
        script = ('import base64,sys,time; '
                  f'sys.stdout.buffer.write(base64.b64decode({base64.b64encode(payload).decode()!r})); '
                  'sys.stdout.buffer.flush(); '
                  f'sys.stderr.write({PRIVATE_SENTINEL!r}); sys.stderr.flush(); '
                  + ('time.sleep(10); ' if stall else '') + f'sys.exit({exit_code})')

        def start(arguments, **options):
            nonlocal invocations
            invocations += 1
            if only_extraction and invocations == 1:
                child = real(arguments, **options)
            else:
                child = real([sys.executable, '-I', '-c', script], **options)
                if fail_read:
                    child.stdout = PipeProxy(child.stdout, fail=True)
            children.append(child)
            return child
        with patch.object(archive.subprocess, 'Popen', side_effect=start):
            yield children

    def check_details(self, caught, *, category, phase='preflight', exit_code=None,
                      tar_reason=None):
        self.assertIsInstance(caught, archive.ArchiveReadError)
        details = caught.details
        self.assertEqual(details['package'], self.package)
        self.assertEqual(details['phase'], phase)
        self.assertEqual(details['category'], category)
        self.assertEqual(details['decoder_exit'], exit_code)
        expected_hex = None if exit_code is None else f'0x{exit_code & 0xffffffff:08X}'
        self.assertEqual(details['decoder_exit_hex'], expected_hex)
        self.assertIs(type(details['decoded_bytes']), int)
        self.assertGreaterEqual(details['decoded_bytes'], 0)
        self.assertIs(type(details['elapsed_ms']), int)
        self.assertGreaterEqual(details['elapsed_ms'], 0)
        self.assertIs(type(details['timed_out']), bool)
        self.assertIs(type(details['forced_cleanup']), bool)
        self.assertTrue(details['cleanup_exit'] is None or type(details['cleanup_exit']) is int)
        self.assertTrue(details['member'] is None or isinstance(details['member'], str))
        if tar_reason is not None:
            self.assertEqual(details['tar_reason'], tar_reason)
        self.assertNotIn(PRIVATE_SENTINEL, str(caught))
        self.assertNotIn(PRIVATE_SENTINEL, json.dumps(details))
        self.assertNotIn('/private/runtime/', json.dumps(details))
        return details

    def check_preserved_and_reaped(self, children):
        self.assertTrue(children)
        for child in children:
            self.assertIsNotNone(child.poll())
            self.assertTrue(child.stdout.closed)
        self.assertFalse(self.prefix.exists())
        self.assertEqual({path.name: path.read_bytes() for path in self.cache.iterdir()}, self.cache_before)

    def test_real_child_exit_before_header_reports_code_without_private_stderr(self):
        output = io.StringIO()
        with redirect_stdout(output), self.emitting_child(exit_code=7) as children:
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = self.check_details(error.exception, category='tar_read_error', exit_code=7,
                                     tar_reason='empty_tar')
        self.assertEqual(details['decoded_bytes'], 0)
        self.assertIsNone(details['member'])
        self.assertFalse(details['timed_out'])
        self.assertFalse(details['forced_cleanup'])
        self.assertNotIn(PRIVATE_SENTINEL, output.getvalue())
        self.check_preserved_and_reaped(children)

    def test_partial_header_reports_natural_exit_and_truncation(self):
        payload = self.tar_bytes[:100]
        with self.emitting_child(payload, exit_code=23) as children:
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = self.check_details(error.exception, category='tar_read_error', exit_code=23,
                                     tar_reason='truncated_header')
        self.assertEqual(details['decoded_bytes'], len(payload))
        self.assertIsNone(details['member'])
        self.assertFalse(details['forced_cleanup'])
        self.check_preserved_and_reaped(children)

    def test_truncated_member_payload_with_zero_exit_is_not_success(self):
        payload = self.tar_bytes[:512 + 5]
        with self.emitting_child(payload, exit_code=0) as children:
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = self.check_details(error.exception, category='tar_read_error', exit_code=0,
                                     tar_reason='truncated_payload')
        self.assertEqual(details['decoded_bytes'], len(payload))
        self.assertEqual(details['member'], '.BUILDINFO')
        self.check_preserved_and_reaped(children)

    def test_partial_tar_stall_is_classified_as_timeout_and_child_is_reaped(self):
        payload = self.tar_bytes[:512 + 5]
        with self.emitting_child(payload, stall=True) as children, \
                patch.object(archive, 'DECODER_TIMEOUT', 0.2):
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = error.exception.details
        self.check_details(error.exception, category='decoder_timeout',
                           exit_code=details['decoder_exit'], tar_reason='truncated_payload')
        self.assertTrue(details['timed_out'])
        self.assertEqual(details['decoded_bytes'], len(payload))
        self.assertIsNotNone(details['decoder_exit'])
        self.assertLess(details['elapsed_ms'], 5000)
        self.check_preserved_and_reaped(children)

    def test_fragmented_real_zstd_pipe_reads_preserve_exact_extraction_and_reuse(self):
        real = archive.subprocess.Popen
        children = []
        def fragmented(arguments, **options):
            child = real(arguments, **options)
            child.stdout = PipeProxy(child.stdout, fragmented=True)
            children.append(child)
            return child
        with patch.object(archive.subprocess, 'Popen', side_effect=fragmented):
            expected = self.fixture.verify()
            self.fixture.prepare()
            self.fixture.prepare()
        self.assertEqual(archive.verify_locked_prefix(self.prefix, self.fixture.lock), expected)
        self.assertTrue(all(child.stdout.calls > 20 and child.poll() is not None and child.stdout.closed
                            for child in children))
        self.assertEqual({path.name: path.read_bytes() for path in self.cache.iterdir()}, self.cache_before)

    def test_pipe_io_error_reports_numeric_errno_without_private_path(self):
        with self.emitting_child(stall=True, fail_read=True) as children:
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = self.check_details(error.exception, category='io_error')
        self.assertEqual(details['errno'], errno.EIO)
        self.assertIsNone(details['winerror'])
        self.assertFalse(details['timed_out'])
        self.assertTrue(details['forced_cleanup'])
        self.assertIsNotNone(details['cleanup_exit'])
        self.check_preserved_and_reaped(children)

    def test_pipe_close_error_is_sanitized_and_final_wait_still_reaps_child(self):
        real = archive.subprocess.Popen
        children = []; wait_after_close = []
        def failing_close(arguments, **options):
            child = real(arguments, **options)
            child.stdout = PipeProxy(child.stdout, fail_close=True)
            original_wait = child.wait
            def wait(*args, **kwargs):
                wait_after_close.append(child.stdout.closed)
                return original_wait(*args, **kwargs)
            child.wait = wait
            children.append(child)
            return child
        with patch.object(archive.subprocess, 'Popen', side_effect=failing_close):
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.verify()
        details = self.check_details(error.exception, category='io_error', exit_code=0)
        self.assertEqual(details['decoder_stage'], 'cleanup')
        self.assertEqual(details['errno'], errno.EIO)
        self.assertIsNone(details['winerror'])
        self.assertEqual(details['cleanup_exit'], 0)
        self.assertFalse(details['timed_out'])
        self.assertFalse(details['forced_cleanup'])
        self.assertTrue(wait_after_close[-1])
        self.check_preserved_and_reaped(children)

    def test_extraction_failure_after_preflight_retains_owned_journal_and_resumes(self):
        with self.emitting_child(exit_code=7, only_extraction=True) as children:
            with self.assertRaises(archive.ArchiveReadError) as error:
                self.fixture.prepare()
        self.check_details(error.exception, category='tar_read_error', phase='extract',
                           exit_code=7, tar_reason='empty_tar')
        self.assertEqual(len(children), 2)
        self.check_preserved_and_reaped(children)
        journal = self.prefix.with_name(self.prefix.name + '.archive-preparation.json')
        staging = self.prefix.with_name(self.prefix.name + '.archive-preparing')
        self.assertTrue(journal.is_file())
        self.assertTrue(staging.is_dir())
        before = journal.read_bytes()
        self.assertFalse((staging / 'receipt.json').exists())
        self.fixture.prepare()
        archive.verify_locked_prefix(self.prefix, self.fixture.lock)
        self.assertEqual(journal.read_bytes(), before)
        self.assertFalse(staging.exists())

    def test_output_bound_applies_to_drain_after_valid_tar_terminator(self):
        limit = len(self.tar_bytes) + 512
        payload = self.tar_bytes + b'\0' * 2048
        with self.emitting_child(payload) as children, patch.object(archive, 'MAX_TAR_STREAM', limit):
            with self.assertRaisesRegex(deps.BuildError, 'stream exceeds'):
                self.fixture.verify()
        self.check_preserved_and_reaped(children)


if __name__ == '__main__':
    unittest.main()
