"""Bounded service reuse/start behavior and real local TLS health checks."""
from contextlib import redirect_stdout
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tools import alliance_workflow as workflow
from tools.alliance_transport import prepare_identity, server_context


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance workflow ")
        self.root = Path(self.temp.name)
        (self.root / "runtime").mkdir()
        (self.root / "tools").mkdir()
        (self.root / "tools/Run-WindowsAllianceBattles.ps1").touch()
        self.runtime = self.root / "runtime"
        self.report = {"steps": [], "status": "failed", "report_path": str(self.root / "report.json")}
        self.patches = [patch.object(workflow, "ROOT", self.root),
            patch.object(workflow, "validate_runtime", return_value=self.runtime),
            patch.object(workflow, "public_profile", return_value={"server_address": "127.0.0.1"}),
            patch.object(workflow, "database_check", return_value=True),
            patch.object(workflow, "backend_check", return_value=True),
            patch.object(workflow, "bridge_check", return_value=True)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def run_helper(self, start=True, battles=False):
        with redirect_stdout(io.StringIO()):
            workflow.run(self.runtime, self.root / "msys", start, self.report, include_battles=battles)

    def test_healthy_services_reused_no_duplicate_or_mutation(self):
        with patch.object(workflow, "open_port", return_value=True), patch.object(workflow, "launch") as launch:
            self.run_helper(battles=True)
        launch.assert_not_called()
        self.assertEqual([row["id"] for row in self.report["steps"]], ["W01", "W02", "W03", "W04", "W05", "W06", "W07"])
        self.assertEqual([row["action"] for row in self.report["steps"][1:-1]], ["reused"] * 5)
        workflow.bridge_check.assert_any_call({"server_address": "127.0.0.1"}, battles=True)
        self.assertEqual(self.report["status"], "passed")

    def test_check_only_never_launches_and_reports_first_stopped(self):
        with patch.object(workflow, "open_port", return_value=False), patch.object(workflow, "launch") as launch:
            with self.assertRaisesRegex(workflow.WorkflowError, "W02_service_stopped"):
                self.run_helper(start=False)
        launch.assert_not_called()
        self.assertEqual(self.report["steps"][-1]["status"], "stopped")

    def test_occupied_wrong_database_is_not_replaced(self):
        workflow.database_check.return_value = False
        with patch.object(workflow, "open_port", return_value=True), patch.object(workflow, "launch") as launch:
            with self.assertRaisesRegex(workflow.WorkflowError, "W02_occupied_but_unhealthy"):
                self.run_helper()
        launch.assert_not_called()

    def test_starts_in_order_and_waits_for_real_health(self):
        calls = []
        child = Mock(pid=1234); child.poll.return_value = None
        def launch(wrapper, runtime, msys, log):
            self.assertTrue(log.is_file())
            calls.append(wrapper)
            return child
        with patch.object(workflow, "open_port", side_effect=[False, True] * 5), patch.object(workflow, "launch", side_effect=launch):
            self.run_helper(battles=True)
        self.assertEqual(calls, [row[3] for row in (*workflow.STEPS, workflow.BATTLE_STEP, workflow.MULTIPLAYER_STEP)])
        self.assertEqual(len(list(self.root.glob("report-W*.txt"))), 5)
        child.terminate.assert_not_called(); child.kill.assert_not_called()

    def test_failure_keeps_prior_services_and_never_starts_later(self):
        live = Mock(pid=1); live.poll.return_value = None
        failed = Mock(pid=2); failed.poll.return_value = 9
        with patch.object(workflow, "open_port", side_effect=[False, True, False]), patch.object(workflow, "launch", side_effect=[live, failed]) as launch:
            with self.assertRaisesRegex(workflow.WorkflowError, "W03_launcher_exited"):
                self.run_helper(battles=True)
        self.assertEqual(launch.call_count, 2)
        live.kill.assert_not_called(); live.terminate.assert_not_called()
        failed.kill.assert_not_called(); failed.terminate.assert_not_called()
        self.assertEqual(self.report["steps"][-1]["id"], "W03")

    def test_newly_started_wrong_release_stops_without_retry_or_killing_child(self):
        child = Mock(pid=1234); child.poll.return_value = None
        workflow.backend_check.side_effect = workflow.WorkflowError(workflow.BACKEND_RELEASE_ERROR)
        with patch.object(workflow, "open_port", side_effect=[True, False, True]), \
                patch.object(workflow, "launch", return_value=child) as launch, \
                patch.object(workflow.time, "sleep") as sleep:
            with self.assertRaisesRegex(workflow.WorkflowError, "^W03_backend_release_mismatch$"):
                self.run_helper(battles=True)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0], "Run-WindowsAlliance.ps1")
        sleep.assert_not_called()
        child.kill.assert_not_called(); child.terminate.assert_not_called()
        self.assertEqual(self.report["steps"][-1]["id"], "W03")
        self.assertEqual(self.report["steps"][-1]["status"], "failed")
        self.assertEqual(self.report["steps"][-1]["action"], "started")
        workflow.bridge_check.assert_not_called()

    def test_optional_battles_missing_helper_refuses_before_start(self):
        (self.root / "tools/Run-WindowsAllianceBattles.ps1").unlink()
        with patch.object(workflow, "launch") as launch:
            with self.assertRaisesRegex(workflow.WorkflowError, "battles_helper_unavailable"):
                self.run_helper(battles=True)
        launch.assert_not_called()

    def test_workflow_guard_excludes_duplicate_launchers_and_is_retained(self):
        with workflow.workflow_lock(self.runtime):
            with self.assertRaisesRegex(workflow.WorkflowError, "another_workflow"):
                with workflow.workflow_lock(self.runtime): self.fail("overlapping launcher")
        self.assertEqual((self.runtime / "workflow.guard").read_bytes(), b"\0")
        with workflow.workflow_lock(self.runtime): pass

    def test_existing_report_refused_without_service_access(self):
        target = self.root / "existing.json"; target.write_bytes(b"keep")
        with patch.object(workflow, "run") as run, redirect_stdout(io.StringIO()):
            code = workflow.main(["--runtime", str(self.runtime), "--msys", str(self.root), "--report", str(target), "--start"])
        self.assertEqual(code, 1); run.assert_not_called(); self.assertEqual(target.read_bytes(), b"keep")

    def test_private_failure_details_do_not_enter_report(self):
        target = self.root / "report.json"
        with patch.object(workflow, "run", side_effect=RuntimeError("PRIVATE_PASSWORD")), redirect_stdout(io.StringIO()) as output:
            code = workflow.main(["--runtime", str(self.runtime), "--msys", str(self.root), "--report", str(target)])
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_PASSWORD", target.read_text() + output.getvalue())
        self.assertEqual(json.loads(target.read_text())["error"], "workflow_incomplete")
        self.assertEqual(json.loads(target.read_text())["wan_disconnected"], "not_observed")


@unittest.skipUnless(shutil.which("openssl"), "Requires local OpenSSL fixture generation")
class RealTlsHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="alliance workflow tls ")
        cls.identity = Path(cls.temp.name) / "identity"
        with redirect_stdout(io.StringIO()):
            cls.profile, _ = prepare_identity(cls.identity, "127.0.0.1", 15001, Path(shutil.which("openssl")))
        cls.context = server_context(cls.identity)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def check(self, *, battles=False, multiplayer=False, reply=None, preamble=b"\0\0\0\0", profile=None):
        requests = []
        errors = []
        port = 15000 if multiplayer else 15002 if battles else 15001
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port)); listener.listen(1); listener.settimeout(10)
            def serve():
                try:
                    raw, _ = listener.accept()
                    with raw:
                        raw.settimeout(8)
                        requests.append(workflow.receive_exact(raw, 4, workflow.time.monotonic() + 5))
                        raw.sendall(preamble)
                        if preamble != b"\0\0\0\0": return
                        with self.context.wrap_socket(raw, server_side=True) as peer:
                            if not multiplayer:
                                length = int.from_bytes(workflow.receive_exact(peer, 4, workflow.time.monotonic() + 5), "big")
                                requests.append(gzip.decompress(workflow.receive_exact(peer, length, workflow.time.monotonic() + 5)))
                            if reply is not None:
                                payload = gzip.compress(reply)
                                peer.sendall(len(payload).to_bytes(4, "big") + payload)
                except Exception as error: errors.append(type(error).__name__)
            thread = threading.Thread(target=serve); thread.start()
            result = workflow.bridge_check(profile or self.profile, battles=battles, multiplayer=multiplayer)
            thread.join(12)
            self.assertFalse(thread.is_alive())
        return result, requests, errors

    def test_actual_pinned_tls_existing_bridge_no_account_data(self):
        reply = b'[alliance_health]\nservice="alliance-accounts"\napi="2"\nimplementation_release="1192617"\n[/alliance_health]\n'
        result, requests, errors = self.check(reply=reply)
        self.assertTrue(result); self.assertEqual(errors, [])
        self.assertEqual(requests, [b"\0\0\0\1", b"[alliance_health]\n[/alliance_health]\n"])
        for bad in (reply.replace(b'1192617', b'1192615'), reply.replace(b'1192617', b'1192616'),
                    reply.replace(b'api="2"', b'api="1"')):
            self.assertFalse(self.check(reply=bad)[0])

    def test_actual_battle_health_fixed_bounded_read_only_request(self):
        reply = b'[alliance_health]\nservice="alliance-battles"\napi="1"\nimplementation_release="1192617"\n[/alliance_health]\n'
        result, requests, errors = self.check(battles=True, reply=reply)
        self.assertTrue(result); self.assertEqual(errors, [])
        self.assertEqual(requests[1], b"[alliance_health]\n[/alliance_health]\n")
        self.assertFalse(self.check(battles=True, reply=reply.replace(b'1192617', b'1192615'))[0])
        self.assertFalse(self.check(battles=True, reply=reply.replace(b'1192617', b'1192616'))[0])

    def test_actual_native_multiplayer_release_greeting_without_login(self):
        greeting=b'[version]\nalliance_protocol="2"\nimplementation_release="1192617"\n[/version]\n'
        result,requests,errors=self.check(multiplayer=True,reply=greeting)
        self.assertTrue(result);self.assertEqual(errors,[])
        self.assertEqual(requests,[b"\0\0\0\1"])
        for bad in (greeting.replace(b'1192617',b'1192615'),greeting.replace(b'1192617',b'1192616'),
                    greeting.replace(b'[/version]',b'alliance_protocol="2"\n[/version]'),b'x'*16385):
            self.assertFalse(self.check(multiplayer=True,reply=bad)[0])

    def test_downgrade_and_wrong_identity_fail_closed(self):
        self.assertFalse(self.check(preamble=b"\xff" * 4)[0])
        profile = {**self.profile, "server_address": "127.0.0.2"}
        # Connect to the fixture while retaining the mismatched numeric SAN.
        original = socket.create_connection
        with patch.object(workflow.socket, "create_connection", side_effect=lambda address, timeout: original(("127.0.0.1", address[1]), timeout=timeout)):
            result, requests, errors = self.check(profile=profile)
        self.assertFalse(result)
        self.assertEqual(requests, [b"\0\0\0\1"])
        self.assertIn("SSLError", errors)

    def test_wrong_health_duplicate_and_decompression_bomb_fail(self):
        for reply in (b'[alliance_health]\nservice="other"\napi="1"\n[/alliance_health]',
                      b'[alliance_health]\napi="1"\napi="1"\n[/alliance_health]', b"x" * 16385):
            with self.subTest(size=len(reply)):
                self.assertFalse(self.check(battles=True, reply=reply)[0])


if __name__ == "__main__": unittest.main()
