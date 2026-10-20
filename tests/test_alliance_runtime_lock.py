"""Process contention and abrupt-exit checks for the permanent runtime guard."""
import errno
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from alliance.config import ConfigurationError

locks = importlib.import_module("alliance.runtime_lock")
ROOT = Path(__file__).resolve().parents[1]


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance guard ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_normal_exception_and_repeated_use_keep_same_file(self):
        for failure in (False, True, False):
            try:
                with locks.runtime_lock(self.root):
                    self.assertFalse((self.root / "operation.lock").exists())
                    if failure:
                        raise RuntimeError("fixture failure")
            except RuntimeError:
                self.assertTrue(failure)
            self.assertEqual((self.root / "operation.guard").read_bytes(), b"\0")
        self.assertEqual((self.root / "operation.guard").read_bytes(), b"\0")

    def test_nested_exclusion_does_not_rewrite_guard(self):
        with locks.runtime_lock(self.root):
            before = (self.root / "operation.guard").stat()
            with self.assertRaisesRegex(ConfigurationError, "holds"):
                with locks.runtime_lock(self.root):
                    self.fail("second holder entered")
            after = (self.root / "operation.guard").stat()
            self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_real_process_exit_and_forced_exit_release_guard(self):
        source = (
            "from pathlib import Path\nimport sys\n"
            "from alliance.runtime_lock import runtime_lock\n"
            "with runtime_lock(Path(sys.argv[1])):\n"
            " print('HELD', flush=True)\n"
            " sys.stdin.readline()\n")
        for abrupt in (False, True):
            with self.subTest(abrupt=abrupt):
                child = subprocess.Popen([sys.executable, "-E", "-s", "-B", "-c", source, str(self.root)],
                                         cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(child.stdout.readline(), "HELD\n")
                    with self.assertRaises(ConfigurationError):
                        with locks.runtime_lock(self.root):
                            self.fail("competing process entered")
                    before = (self.root / "operation.guard").stat()
                    if abrupt:
                        child.kill()
                    else:
                        child.stdin.write("\n")
                        child.stdin.flush()
                    child.wait(timeout=10)
                    with locks.runtime_lock(self.root):
                        after = (self.root / "operation.guard").stat()
                        self.assertEqual(before.st_ino, after.st_ino)
                        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=10)

    def test_legacy_marker_blocks_without_reading_or_changing_it(self):
        marker = self.root / "operation.lock"
        original = b'{"pid": 7400, "started_at": "2026-10-20T12:36:21.894725+00:00"}'
        marker.write_bytes(original)
        with self.assertRaisesRegex(ConfigurationError, "legacy"):
            with locks.runtime_lock(self.root):
                self.fail("legacy marker ignored")
        self.assertEqual(marker.read_bytes(), original)
        backup = self.root / "operation.lock.fixture-backup"
        marker.rename(backup)
        with locks.runtime_lock(self.root):
            self.assertEqual(backup.read_bytes(), original)

    def test_guard_handle_is_not_inheritable(self):
        real = locks._acquire
        def inspect(fd):
            self.assertFalse(os.get_inheritable(fd))
            real(fd)
        with patch.object(locks, "_acquire", side_effect=inspect):
            with locks.runtime_lock(self.root):
                pass

    def test_invalid_guard_contents_are_preserved(self):
        guard = self.root / "operation.guard"
        for content in (b"x", b"existing unrelated contents"):
            guard.write_bytes(content)
            with self.assertRaisesRegex(ConfigurationError, "contents"):
                with locks.runtime_lock(self.root):
                    self.fail("invalid guard entered")
            self.assertEqual(guard.read_bytes(), content)

    @unittest.skipIf(os.name == "nt", "Unix link fixtures; Windows helper also checks native metadata")
    def test_symlink_hardlink_directory_and_fifo_are_refused(self):
        guard = self.root / "operation.guard"
        target = self.root / "target"
        target.write_bytes(b"\0")
        guard.symlink_to(target)
        with self.assertRaises(ConfigurationError):
            with locks.runtime_lock(self.root):
                pass
        guard.unlink()
        os.link(target, guard)
        with self.assertRaises(ConfigurationError):
            with locks.runtime_lock(self.root):
                pass
        guard.unlink()
        guard.mkdir()
        with self.assertRaises(ConfigurationError):
            with locks.runtime_lock(self.root):
                pass
        guard.rmdir()
        os.mkfifo(guard)
        with self.assertRaises(ConfigurationError):
            with locks.runtime_lock(self.root):
                pass
        guard.unlink()
        self.assertEqual(target.read_bytes(), b"\0")

    def test_open_file_and_named_identity_must_agree(self):
        first = self.root / "first"
        other = self.root / "other"
        first.write_bytes(b"\0")
        other.write_bytes(b"\0")
        fd = os.open(first, os.O_RDWR)
        try:
            locks._file_identity(first, fd)
            with self.assertRaises(ConfigurationError):
                locks._file_identity(other, fd)
        finally:
            os.close(fd)

    def test_unreadable_legacy_metadata_fails_closed(self):
        original = Path.lstat
        def inspect(path, *args, **kwargs):
            if path.name == "operation.lock":
                raise PermissionError("fixture inaccessible marker")
            return original(path, *args, **kwargs)
        with patch.object(Path, "lstat", inspect):
            with self.assertRaises(PermissionError):
                with locks.runtime_lock(self.root):
                    self.fail("could not rule out legacy marker")
        with locks.runtime_lock(self.root):
            pass

    def test_io_errors_are_not_reported_as_contention(self):
        for number in (errno.EIO, errno.EBADF, errno.EINVAL):
            with patch.object(locks, "_acquire", side_effect=OSError(number, "fixture")):
                with self.assertRaises(OSError):
                    with locks.runtime_lock(self.root):
                        pass
        for number in (errno.EACCES, errno.EAGAIN):
            with patch.object(locks, "_acquire", side_effect=OSError(number, "fixture")):
                with self.assertRaises(ConfigurationError):
                    with locks.runtime_lock(self.root):
                        pass

    def test_descriptor_closes_even_when_unlock_fails(self):
        with patch.object(locks, "_release", side_effect=OSError("fixture unlock failure")):
            with self.assertRaises(OSError):
                with locks.runtime_lock(self.root):
                    pass
        with locks.runtime_lock(self.root):
            pass

    def test_windows_nonblocking_byte_range_protocol(self):
        calls = []
        module = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0,
                                      locking=lambda *args: calls.append(args))
        with patch.dict(sys.modules, {"msvcrt": module}), \
             patch.object(locks.os, "name", "nt"), \
             patch.object(locks.os, "lseek") as seek:
            locks._acquire(41)
            locks._release(41)
        self.assertEqual(calls, [(41, 2, 1), (41, 0, 1)])
        self.assertEqual(seek.call_args_list[0].args, (41, 0, os.SEEK_SET))
        self.assertEqual(seek.call_args_list[1].args, (41, 0, os.SEEK_SET))


if __name__ == "__main__":
    unittest.main()
