"""Storage diagnostic ownership/lifecycle tests; no game runtime is opened."""
from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bson.int64 import Int64
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

SPEC = importlib.util.spec_from_file_location(
    "mongodb_startup_probe", Path(__file__).resolve().parents[1] / "tools/test_mongodb_startup.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Process:
    def __init__(self, pid):
        self.pid, self.code = pid, None
        self.terminated = self.killed = False

    def poll(self):
        return self.code

    def wait(self, timeout):
        if self.code is None:
            raise subprocess.TimeoutExpired("safe-fixture", timeout)
        return self.code

    def terminate(self):
        self.terminated, self.code = True, -15

    def kill(self):
        self.killed, self.code = True, -9


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mongo diagnostic spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scratch = self.root / "fresh fixture"
        self.report_path = self.root / "report.json"
        self.mongod = self.root / "mongod"
        self.mongod.write_bytes(b"fake executable never executed")
        self.private = self.root / ".env"
        self.private.write_bytes(b"PRIVATE_SENTINEL")
        self.processes, self.commands, self.launches = [], [], []
        self.documents = {}
        self.failure = ""
        fixture = self

        class Client:
            def __init__(self, process):
                self.process = process
                self.admin = self.alliance_startup_fixture = self
                self.identity_calls = 0

            def command(self, command, **kwargs):
                fixture.commands.append(command)
                if fixture.failure == "connection":
                    raise ServerSelectionTimeoutError("PRIVATE_ERROR_MUST_NOT_ESCAPE")
                if command == "serverStatus":
                    self.identity_calls += 1
                    wrong_pid = fixture.failure == "pid" or (fixture.failure == "pid_shutdown" and self.identity_calls >= 3)
                    return {"pid": Int64(self.process.pid + int(wrong_pid)),
                            "version": probe.VERSION}
                if command == "getCmdLineOpts":
                    return {"parsed": {"net": {"bindIp": "127.0.0.1", "port": 30124 if fixture.failure == "options" else 30123},
                        "storage": {"dbPath": str(fixture.scratch / "data")}}}
                if command == "shutdown":
                    if fixture.failure != "shutdown":
                        self.process.code = 0
                    raise AutoReconnect("closed")
                return {"ok": 1}

            def get_collection(self, name, write_concern):
                fixture.assertEqual(write_concern.document, {"w": 1, "j": True, "wtimeout": 3000})
                return self

            def insert_one(self, document):
                fixture.commands.append("insert")
                if fixture.failure == "interrupt":
                    raise KeyboardInterrupt
                fixture.documents[document["_id"]] = dict(document)

            def find_one(self, query, **kwargs):
                fixture.commands.append("read")
                if fixture.failure == "lost" and len(fixture.processes) == 2:
                    return None
                return fixture.documents.get(query["_id"])

            def close(self):
                pass

        def launch(args, **kwargs):
            process = Process(600 + len(self.processes))
            if self.failure == "exit":
                process.code = 100
            self.processes.append(process)
            self.launches.append((args, kwargs))
            return process

        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(probe, "check_version"))
        stack.enter_context(patch.object(probe, "choose_port", return_value=30123))
        stack.enter_context(patch.object(probe.subprocess, "Popen", side_effect=launch))
        stack.enter_context(patch.object(probe, "client_for", side_effect=lambda port: Client(self.processes[-1])))

    def run_probe(self):
        report = probe.run(self.mongod, self.scratch, self.report_path)
        self.assertEqual(json.loads(self.report_path.read_text()), report)
        self.assertEqual(self.private.read_bytes(), b"PRIVATE_SENTINEL")
        self.assertNotIn("PRIVATE_ERROR", self.report_path.read_text())
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        return report

    def test_success_restarts_owned_storage_then_stops_and_retains_everything(self):
        report = self.run_probe()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["format"], 1)
        self.assertEqual(report["purpose"], "wesnoth-mongodb-startup-check")
        self.assertEqual(report["checks"], ["mongodb_8.0.32", "first_start_ping", "journaled_write",
                         "initial_read", "first_clean_shutdown", "restart_ping", "persisted_read", "final_clean_shutdown"])
        self.assertEqual(len(self.processes), 2)
        self.assertEqual(self.commands.count("insert"), 1)
        self.assertEqual(self.commands.count("shutdown"), 2)
        for args, options in self.launches:
            self.assertEqual(options["cwd"], self.scratch)
            self.assertNotEqual(options["stdout"], subprocess.PIPE)
            self.assertEqual(args[args.index("--dbpath") + 1], str(self.scratch / "data"))
            self.assertEqual(args[args.index("--bind_ip") + 1], "127.0.0.1")
            self.assertEqual(args[args.index("--port") + 1], "30123")
            self.assertNotIn("--repair", args)
        self.assertTrue((self.scratch / "owner.json").is_file())
        self.assertTrue((self.scratch / "logs/process-1.log").is_file())
        self.assertTrue((self.scratch / "logs/process-2.log").is_file())
        self.assertTrue(all(not process.terminated for process in self.processes))

    def test_wrong_server_pid_gets_no_writes_or_shutdown(self):
        self.failure = "pid"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "server_pid_mismatch")
        self.assertEqual(set(self.commands), {"serverStatus"})
        self.assertEqual(report["cleanup"], ["terminated"])

    def test_changed_identity_before_shutdown_never_gets_shutdown_command(self):
        self.failure = "pid_shutdown"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "server_pid_mismatch")
        self.assertEqual(self.commands.count("insert"), 1)
        self.assertNotIn("shutdown", self.commands)
        self.assertEqual(report["cleanup"], ["terminated"])

    def test_wrong_storage_options_never_receive_write_or_shutdown(self):
        self.failure = "options"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "server_options_mismatch")
        self.assertNotIn("insert", self.commands)
        self.assertNotIn("shutdown", self.commands)

    def test_initial_exit_preserves_logs_and_never_retries_start(self):
        self.failure = "exit"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "owned_process_exited")
        self.assertEqual(len(self.processes), 1)
        self.assertEqual(self.commands, [])
        self.assertEqual(report["processes"][0]["exit_code"], 100)

    def test_connection_timeout_stops_own_child_without_database_commands(self):
        self.failure = "connection"
        with patch.object(probe.time, "monotonic", side_effect=[0, 0, 31]), patch.object(probe.time, "sleep"):
            report = self.run_probe()
        self.assertEqual(report["error"]["code"], "startup_timeout")
        self.assertNotIn("insert", self.commands)
        self.assertNotIn("shutdown", self.commands)
        self.assertTrue(self.processes[0].terminated)

    def test_shutdown_timeout_is_failure_and_forced_cleanup_is_reported(self):
        self.failure = "shutdown"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "shutdown_timeout")
        self.assertEqual(report["cleanup"], ["terminated"])
        self.assertEqual(len(self.processes), 1)

    def test_restart_reads_saved_canary_and_detects_lost_persistence(self):
        self.failure = "lost"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "canary_mismatch")
        self.assertEqual(report["phase"], "persisted_read")
        self.assertEqual(report["cleanup"], ["not_needed", "graceful_after_failure"])

    def test_interrupt_stops_child_and_emits_failed_report(self):
        self.failure = "interrupt"
        report = self.run_probe()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error"]["type"], "KeyboardInterrupt")
        self.assertEqual(report["cleanup"], ["graceful_after_failure"])
        self.assertFalse(self.processes[0].terminated)

    def test_existing_scratch_is_preserved_without_process(self):
        self.scratch.mkdir()
        sentinel = self.scratch / "keep"
        sentinel.write_bytes(b"ORIGINAL")
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "scratch_already_exists")
        self.assertEqual(sentinel.read_bytes(), b"ORIGINAL")
        self.assertEqual(self.processes, [])

    def test_existing_report_is_preserved_without_process(self):
        self.report_path.write_bytes(b"ORIGINAL_REPORT")
        with self.assertRaises(FileExistsError):
            probe.run(self.mongod, self.scratch, self.report_path)
        self.assertEqual(self.report_path.read_bytes(), b"ORIGINAL_REPORT")
        self.assertFalse(self.scratch.exists())

    def test_symlinked_ancestor_is_rejected_with_saved_error(self):
        (self.root / "redirect").symlink_to(self.root, target_is_directory=True)
        self.scratch = self.root / "redirect/fresh fixture"
        report = self.run_probe()
        self.assertEqual(report["error"]["code"], "redirected_path")
        self.assertEqual(self.processes, [])

    def test_main_success_marker_requires_all_checks(self):
        output = io.StringIO()
        self.failure = "lost"
        with redirect_stdout(output):
            code = probe.main(["--mongod", str(self.mongod), "--scratch", str(self.scratch),
                               "--report", str(self.report_path)])
        self.assertEqual(code, 1)
        self.assertNotIn(probe.SUCCESS, output.getvalue())


class HelperTests(unittest.TestCase):
    def test_cleanup_kills_only_owned_child_after_terminate_timeout(self):
        process = Process(123)
        with patch.object(process, "terminate") as terminate:
            self.assertEqual(probe.force_cleanup(process), "killed")
        terminate.assert_called_once_with()
        self.assertTrue(process.killed)

    def test_version_requires_exact_first_line_and_retains_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "logs").mkdir()
            def version(args, **options):
                options["stdout"].write(b"db version v8.0.32\nBuild Info: {}\n")
                return subprocess.CompletedProcess(args, 0)
            with patch.object(probe.subprocess, "run", side_effect=version):
                probe.check_version(root / "mongod", root)
            self.assertIn(b"8.0.32", (root / "logs/version.txt").read_bytes())
            (root / "logs/version.txt").unlink()
            def wrong(args, **options):
                options["stdout"].write(b"db version v8.0.320\n")
                return subprocess.CompletedProcess(args, 0)
            with patch.object(probe.subprocess, "run", side_effect=wrong), self.assertRaises(probe.ProbeFailure):
                probe.check_version(root / "mongod", root)


if __name__ == "__main__":
    unittest.main()
