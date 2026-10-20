"""Scratch-only filesystem probe behavior; Windows locking is not simulated as proof."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "probe_windows_file_sharing", ROOT / "tools/probe_windows_file_sharing.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FileSharingProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sharing probe paths with spaces ")
        self.root = Path(self.temp.name)
        self.parent = self.root / "diagnostics"
        self.output = io.StringIO()

    def tearDown(self):
        self.temp.cleanup()

    def run_probe(self, iterations=3):
        with redirect_stdout(self.output):
            return probe.run_probe(self.parent, iterations=iterations, delay=0)

    def scratch(self):
        paths = list(self.parent.glob("mongo-file-probe-*"))
        self.assertEqual(len(paths), 1)
        return paths[0]

    def events(self, scratch=None):
        root = scratch if scratch is not None else self.scratch()
        return [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]

    def test_actual_replacements_finish_with_correlatable_report(self):
        self.assertEqual(self.run_probe(), 0)
        scratch = self.scratch()
        events = self.events(scratch)
        self.assertEqual([item["event"] for item in events],
                         ["START", "PASS", "PASS", "PASS", "COMPLETE"])
        self.assertEqual([item["iteration"] for item in events if item["event"] == "PASS"],
                         [1, 2, 3])
        self.assertEqual(events[0]["scratch"], str(scratch))
        for event in events:
            self.assertEqual(event["pid"], os.getpid())
            self.assertIsNotNone(datetime.fromisoformat(event["utc"]).utcoffset())
        self.assertFalse((scratch / "WiredTiger.turtle.set").exists())
        self.assertGreater((scratch / "WiredTiger.turtle").stat().st_size, 0)
        self.assertIn(str(scratch / "events.jsonl"), self.output.getvalue())
        self.assertIn("does not prove MongoDB startup is fixed", self.output.getvalue())

    def test_later_replace_failure_preserves_both_generations_and_stops(self):
        original_replace = probe.os.replace
        generations = []
        failure = PermissionError(errno.EACCES, "fixture sharing violation")
        failure.winerror = 32

        def replace(source, target):
            generations.append(source.read_bytes())
            if len(generations) == 2:
                raise failure
            return original_replace(source, target)

        with patch.object(probe.os, "replace", side_effect=replace) as replace_mock:
            self.assertEqual(self.run_probe(iterations=20), 1)
        self.assertEqual(replace_mock.call_count, 2)
        scratch = self.scratch()
        self.assertNotEqual(generations[0], generations[1])
        self.assertEqual((scratch / "WiredTiger.turtle").read_bytes(), generations[0])
        self.assertEqual((scratch / "WiredTiger.turtle.set").read_bytes(), generations[1])
        events = self.events(scratch)
        self.assertEqual([item["event"] for item in events], ["START", "PASS", "FAIL"])
        self.assertEqual(events[-1]["operation"], "replace")
        self.assertEqual(events[-1]["iteration"], 2)
        self.assertEqual(events[-1]["winerror"], 32)
        self.assertEqual(events[-1]["errno"], errno.EACCES)
        self.assertEqual(events[-1]["error_type"], "PermissionError")

    def test_first_replace_failure_preserves_source_without_target(self):
        failure = PermissionError(errno.EACCES, "fixture denied")
        with patch.object(probe.os, "replace", side_effect=failure) as replace_mock:
            self.assertEqual(self.run_probe(iterations=20), 1)
        replace_mock.assert_called_once()
        scratch = self.scratch()
        self.assertGreater((scratch / "WiredTiger.turtle.set").stat().st_size, 0)
        self.assertFalse((scratch / "WiredTiger.turtle").exists())
        self.assertEqual([item["event"] for item in self.events(scratch)], ["START", "FAIL"])
        self.assertIsNone(self.events(scratch)[-1]["winerror"])

    def test_existing_scratch_source_is_never_truncated_or_removed(self):
        original_mkdtemp = probe.tempfile.mkdtemp
        sentinel = b"preexisting scratch evidence"

        def mkdtemp(*args, **kwargs):
            result = original_mkdtemp(*args, **kwargs)
            (Path(result) / "WiredTiger.turtle.set").write_bytes(sentinel)
            return result

        with patch.object(probe.tempfile, "mkdtemp", side_effect=mkdtemp), \
                patch.object(probe.os, "replace") as replace_mock:
            self.assertEqual(self.run_probe(), 1)
        replace_mock.assert_not_called()
        self.assertEqual((self.scratch() / "WiredTiger.turtle.set").read_bytes(), sentinel)
        self.assertEqual(self.events()[-1]["operation"], "create")
        self.assertEqual(self.events()[-1]["errno"], errno.EEXIST)

    def test_fsync_failure_stops_before_rename_and_preserves_written_source(self):
        with patch.object(probe.os, "fsync", side_effect=OSError(errno.EIO, "fixture I/O")) as sync, \
                patch.object(probe.os, "replace") as replace_mock:
            self.assertEqual(self.run_probe(), 1)
        sync.assert_called_once()
        replace_mock.assert_not_called()
        self.assertGreater((self.scratch() / "WiredTiger.turtle.set").stat().st_size, 0)
        self.assertFalse((self.scratch() / "WiredTiger.turtle").exists())
        self.assertEqual(self.events()[-1]["operation"], "fsync")
        self.assertEqual(self.events()[-1]["errno"], errno.EIO)

    def test_flush_failure_is_recorded_and_does_not_rename(self):
        original_open = Path.open
        opened_streams = []

        class FlushFailure:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.stream.close()

            def write(self, data):
                return self.stream.write(data)

            def flush(self):
                raise OSError(errno.ENOSPC, "fixture full disk")

        def open_path(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path.name == "WiredTiger.turtle.set":
                opened_streams.append(stream)
                return FlushFailure(stream)
            return stream

        with patch.object(Path, "open", new=open_path), \
                patch.object(probe.os, "replace") as replace_mock:
            self.assertEqual(self.run_probe(), 1)
        replace_mock.assert_not_called()
        self.assertEqual(len(opened_streams), 1)
        self.assertTrue(opened_streams[0].closed)
        self.assertGreater((self.scratch() / "WiredTiger.turtle.set").stat().st_size, 0)
        self.assertEqual(self.events()[-1]["operation"], "flush")
        self.assertEqual(self.events()[-1]["errno"], errno.ENOSPC)

    def test_unique_runs_preserve_previous_report_and_files(self):
        self.assertEqual(self.run_probe(), 0)
        first = self.scratch()
        before = {path.name: path.read_bytes() for path in first.iterdir()}
        self.assertEqual(self.run_probe(), 0)
        self.assertEqual(len(list(self.parent.glob("mongo-file-probe-*"))), 2)
        self.assertEqual({path.name: path.read_bytes() for path in first.iterdir()}, before)

    def test_opens_only_new_scratch_files_and_preserves_existing_runtime(self):
        runtime = self.root / "runtime" / "alliance" / "data"
        runtime.mkdir(parents=True)
        sentinels = {
            runtime / "WiredTiger.turtle": b"unrelated database sentinel",
            runtime / "WiredTiger.turtle.set": b"unrelated pending metadata sentinel",
            self.root / ".env": b"synthetic fixture; not real credentials",
        }
        for path, content in sentinels.items():
            path.write_bytes(content)
        original_open = Path.open
        opened = []

        def record_open(path, *args, **kwargs):
            opened.append((path, args[0] if args else kwargs.get("mode", "r")))
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", new=record_open):
            self.assertEqual(self.run_probe(), 0)
        scratch = self.scratch()
        self.assertTrue(opened)
        self.assertTrue(all(path.parent == scratch and mode.startswith("x")
                            for path, mode in opened))
        for path, content in sentinels.items():
            self.assertEqual(path.read_bytes(), content)

    def test_invalid_bounds_do_not_create_any_files(self):
        for iterations, delay in [(0, 0), (101, 0), (1, -1), (1, 2)]:
            with self.subTest(iterations=iterations, delay=delay):
                with self.assertRaises(ValueError):
                    probe.run_probe(self.parent, iterations=iterations, delay=delay)
        self.assertFalse(self.parent.exists())

    def test_cli_refuses_non_windows_before_running_probe(self):
        with patch.object(probe.sys, "platform", "linux"), \
                patch.object(probe, "run_probe") as run, redirect_stderr(self.output):
            self.assertEqual(probe.main(), 2)
        run.assert_not_called()
        self.assertIn("native Windows Python", self.output.getvalue())

    def test_cli_default_keeps_repository_diagnostics_location(self):
        with patch.object(probe.sys, "platform", "win32"), \
                patch.object(probe, "run_probe", return_value=0) as run:
            self.assertEqual(probe.main([]), 0)
        run.assert_called_once_with(ROOT / "diagnostics")

    def test_cli_explicit_parent_with_spaces_keeps_original_locations_unchanged(self):
        custom_parent = self.root / "local app data" / "Wesnoth diagnostics"
        sentinels = {
            self.parent / "old-report.jsonl": b"retained earlier report",
            self.root / "runtime" / "alliance" / "data" / "WiredTiger.turtle": b"old database",
            self.root / ".env": b"synthetic fixture, not real credentials",
        }
        for path, content in sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        with patch.object(probe.sys, "platform", "win32"), \
                patch.object(probe.time, "sleep"), redirect_stdout(self.output):
            self.assertEqual(probe.main(["--parent", str(custom_parent)]), 0)
        scratches = list(custom_parent.glob("mongo-file-probe-*"))
        self.assertEqual(len(scratches), 1)
        events = self.events(scratches[0])
        self.assertEqual(events[0]["iterations"], 20)
        self.assertEqual(sum(event["event"] == "PASS" for event in events), 20)
        self.assertEqual(events[-1]["event"], "COMPLETE")
        self.assertIn(str(scratches[0]), self.output.getvalue())
        self.assertEqual(list(self.parent.iterdir()), [self.parent / "old-report.jsonl"])
        for path, content in sentinels.items():
            self.assertEqual(path.read_bytes(), content)

    def test_cli_relative_parent_is_rejected_before_probe_or_files(self):
        before = list(self.root.iterdir())
        for parent in ["relative path", "../other", "", "C:drive-relative"]:
            with self.subTest(parent=parent), \
                    patch.object(probe.sys, "platform", "win32"), \
                    patch.object(probe, "run_probe") as run, redirect_stderr(self.output):
                with self.assertRaises(SystemExit) as raised:
                    probe.main(["--parent", parent])
                self.assertEqual(raised.exception.code, 2)
                run.assert_not_called()
        self.assertIn("--parent must be an absolute path", self.output.getvalue())
        self.assertEqual(list(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
