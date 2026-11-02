"""Startup phase bounds and append-only diagnostics, without production data."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from alliance import startup_progress as progress
from tools import alliance_workflow as workflow


class Clock:
    def __init__(self):
        self.now = 0.0
        self.events = []

    def monotonic(self): return self.now

    def sleep(self, seconds):
        self.now += seconds
        due = [(at, action) for at, action in self.events if at <= self.now]
        self.events = [(at, action) for at, action in self.events if at > self.now]
        for _, action in due: action()


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="battle progress ")
        self.root = Path(self.temp.name)
        self.path = self.root / "startup.jsonl"
        self.launch_id = progress.create_progress(self.path)

    def tearDown(self): self.temp.cleanup()

    def publisher(self): return progress.StartupProgress(self.path, self.launch_id)

    def test_fresh_header_and_four_phase_publisher_do_not_contain_credentials(self):
        output = io.StringIO()
        with redirect_stdout(output):
            publisher = self.publisher()
            for phase in progress.PHASES: publisher.phase(phase)
        state = progress.read_progress(self.path, self.launch_id)
        self.assertEqual(state["phase"], "serving")
        self.assertEqual([r["phase"] for r in state["records"]], list(progress.PHASES))
        self.assertEqual({r["pid"] for r in state["records"]}, {os.getpid()})
        self.assertNotIn(self.launch_id, output.getvalue())
        self.assertNotIn(str(self.path), output.getvalue())
        self.assertEqual(publisher.current_phase, "serving")
        with self.assertRaises(progress.ProgressError): publisher.phase("serving")
        with self.assertRaises(FileExistsError): progress.create_progress(self.path)

    def test_standalone_publisher_logs_all_phases_without_any_file(self):
        with redirect_stdout(io.StringIO()) as output:
            publisher = progress.StartupProgress()
            for phase in progress.PHASES: publisher.phase(phase)
        self.assertEqual(publisher.current_phase, "serving")
        self.assertEqual(output.getvalue().count("BATTLE STARTUP phase="), 4)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_wrong_launch_and_invalid_pair_are_rejected(self):
        with self.assertRaises(progress.ProgressError): progress.read_progress(self.path, "0"*32)
        with self.assertRaises(progress.ProgressError): progress.StartupProgress(self.path)
        with self.assertRaises(progress.ProgressError): progress.StartupProgress(launch_id=self.launch_id)

    def test_partial_last_append_is_pending_until_complete(self):
        publisher = self.publisher()
        with redirect_stdout(io.StringIO()): publisher.phase("runtime")
        original = self.path.read_bytes()
        record = dict(phase="worker_verification", launch_id=self.launch_id, pid=os.getpid(),
                      elapsed_ms=progress.read_progress(self.path,self.launch_id)["records"][-1]["elapsed_ms"]+1,
                      at_utc=progress.utc_now())
        data = (json.dumps(record) + "\n").encode()
        self.path.write_bytes(original + data[:20])
        state = progress.read_progress(self.path, self.launch_id)
        self.assertTrue(state["partial"])
        self.assertEqual(state["phase"], "runtime")
        self.path.write_bytes(original + data)
        self.assertEqual(progress.read_progress(self.path, self.launch_id)["phase"], "worker_verification")

    def test_malformed_duplicate_out_of_order_foreign_pid_and_oversize_refused(self):
        header = self.path.read_bytes()
        base = dict(phase="runtime", launch_id=self.launch_id, pid=os.getpid(), elapsed_ms=0, at_utc=progress.utc_now())
        invalid = [b'not-json\n', b'{}\n', b'{"phase":"runtime","phase":"runtime"}\n',
                   (json.dumps({**base, "phase": "listener"})+"\n").encode(),
                   (json.dumps({**base, "launch_id": "0"*32})+"\n").encode(),
                   (json.dumps({**base, "pid": True})+"\n").encode(), b'x'*progress.MAX_BYTES]
        first = (json.dumps(base)+"\n").encode()
        invalid.append(first + (json.dumps({**base, "phase":"worker_verification", "pid":os.getpid()+1})+"\n").encode())
        invalid.append(first + (json.dumps({**base, "phase":"worker_verification", "elapsed_ms":-1})+"\n").encode())
        for suffix in invalid:
            with self.subTest(suffix=suffix[:30]):
                self.path.write_bytes(header+suffix)
                with self.assertRaises(progress.ProgressError): progress.read_progress(self.path, self.launch_id)

    def test_publisher_refuses_changed_file_and_reader_refuses_links(self):
        publisher = self.publisher()
        replacement = self.root / "replacement"
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(progress.ProgressError): publisher.phase("runtime")
        alias = self.root / "alias"
        os.link(self.path, alias)
        with self.assertRaises(progress.ProgressError): progress.read_progress(self.path, self.launch_id)
        alias.unlink()
        target = self.root / "symlink"
        target.symlink_to(self.path)
        with self.assertRaises(progress.ProgressError): progress.read_progress(target, self.launch_id)


class StartupWaitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="battle wait ")
        self.root = Path(self.temp.name)
        self.path = self.root / "startup.jsonl"
        self.launch_id = progress.create_progress(self.path)
        self.clock = Clock()
        self.clock_patch = patch.object(workflow.time, "monotonic", self.clock.monotonic)
        self.sleep_patch = patch.object(workflow.time, "sleep", self.clock.sleep)
        self.clock_patch.start(); self.sleep_patch.start()
        self.output = io.StringIO()
        self.output_patch = redirect_stdout(self.output); self.output_patch.__enter__()
        self.publisher = progress.StartupProgress(self.path, self.launch_id)
        self.watch = workflow.StartupWatch(self.path, self.launch_id, self.clock.now)
        self.child = Mock(pid=1234); self.child.poll.return_value = None
        self.row = {"id":"W05", "status":"checking", "service":"battles"}

    def tearDown(self):
        self.output_patch.__exit__(None, None, None)
        self.clock_patch.stop(); self.sleep_patch.stop(); self.temp.cleanup()

    def phases(self, *events):
        for at, phase in events:
            self.clock.events.append((at, lambda phase=phase: self.publisher.phase(phase)))

    def wait(self, port_at=None, checked=None):
        def health(deadline=None):
            self.row["probe_attempts"] = self.row.get("probe_attempts",0)+1
            self.row["last_health_outcome"] = "healthy"
            return True
        with patch.object(workflow, "open_port", side_effect=lambda *_, **kwargs: port_at is not None and self.clock.now >= port_at):
            workflow.wait_for_startup(self.child,"127.0.0.1",15002,checked or health,self.row,watch=self.watch)

    def test_slow_verified_worker_over_old_300_seconds_reaches_real_health_once(self):
        self.publisher.phase("runtime")
        self.phases((2,"worker_verification"),(410,"listener"),(411,"serving"))
        self.wait(port_at=412)
        self.assertEqual(self.row["status"],"passed")
        self.assertEqual(self.row["startup_phase"],"serving")
        self.assertEqual(self.row["startup_elapsed_seconds"],412)
        self.assertEqual(self.row["probe_attempts"],1)
        self.child.kill.assert_not_called(); self.child.terminate.assert_not_called()

    def test_no_progress_stays_bounded_by_original_preflight_limit(self):
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait()
        self.assertEqual(self.clock.now,300)
        self.assertEqual(self.row["startup_timeout_phase"],"preflight")
        self.assertEqual(self.row["last_health_outcome"],"port_not_open")

    def test_hung_worker_has_fixed_verification_cap_without_heartbeat_extension(self):
        self.publisher.phase("runtime")
        self.phases((2,"worker_verification"))
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait()
        self.assertEqual(self.clock.now,902)
        self.assertEqual(self.row["startup_timeout_phase"],"worker_verification")

    def test_serving_marker_does_not_mean_health_or_reset_listener_deadline(self):
        self.publisher.phase("runtime")
        self.phases((1,"worker_verification"),(2,"listener"),(50,"serving"))
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait()
        self.assertEqual(self.clock.now,77)
        self.assertEqual(self.row["startup_timeout_phase"],"listener")

    def test_phase_first_observed_after_expiry_cannot_rescue_preflight(self):
        self.publisher.phase("runtime")
        self.phases((300,"worker_verification"))
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait(port_at=300)
        self.assertEqual(self.clock.now,300)
        self.assertEqual(self.row["startup_timeout_phase"],"preflight")
        self.assertEqual(self.row["probe_attempts"],0)

    def test_hard_total_cap_survives_phase_transition(self):
        with patch.dict(workflow.BATTLE_STARTUP_LIMITS,{"preflight":10,"worker_verification":100,"listener":100,"total":15}):
            self.watch = workflow.StartupWatch(self.path,self.launch_id,0)
        self.publisher.phase("runtime")
        self.phases((1,"worker_verification"),(14,"listener"))
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait()
        self.assertEqual(self.clock.now,15)
        self.assertEqual(self.row["startup_timeout_phase"],"total")

    def test_successful_probe_after_deadline_is_not_a_pass(self):
        def late_health(deadline=None):
            self.clock.now = 301
            return True
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_startup_unconfirmed"):
            self.wait(port_at=0,checked=late_health)
        self.assertEqual(self.row["status"],"unconfirmed")

    def test_final_phases_published_during_successful_probe_are_reported(self):
        self.publisher.phase("runtime")
        self.publisher.phase("worker_verification")
        def health(deadline=None):
            self.clock.now += 1
            self.publisher.phase("listener")
            self.publisher.phase("serving")
            return True
        self.wait(port_at=0,checked=health)
        self.assertEqual(self.row["startup_phase"],"serving")
        self.assertEqual(len(self.row["startup_phases"]),4)

    def test_transient_health_failures_then_success_do_not_launch_again(self):
        self.publisher.phase("runtime")
        self.publisher.phase("worker_verification")
        self.publisher.phase("listener")
        self.publisher.phase("serving")
        outcomes = iter(("probe_timeout","connection_error","healthy"))
        def health(deadline=None):
            result=next(outcomes)
            self.row["probe_attempts"]+=1
            self.row["last_health_outcome"]=result
            return result=="healthy"
        self.wait(port_at=0,checked=health)
        self.assertEqual(self.row["probe_attempts"],3)
        self.assertEqual(self.clock.now,2)

    def test_exit_stops_immediately_and_never_terminates_other_services(self):
        self.child.poll.side_effect=lambda: 2 if self.clock.now>=3 else None
        with self.assertRaisesRegex(workflow.WorkflowError,"W05_launcher_exited"):
            self.wait()
        self.assertEqual(self.clock.now,3)
        self.child.kill.assert_not_called(); self.child.terminate.assert_not_called()

    def test_forged_replacement_and_invalid_records_are_fixed_sanitized_errors(self):
        self.path.write_bytes(self.path.read_bytes()+b'PRIVATE_PASSWORD\n')
        with self.assertRaisesRegex(workflow.WorkflowError,"^W05_startup_progress_invalid$"):
            self.wait()
        self.assertNotIn("PRIVATE_PASSWORD",json.dumps(self.row)+self.output.getvalue())
        self.assertNotIn(self.launch_id,json.dumps(self.row)+self.output.getvalue())

    def test_identical_replacement_and_truncation_refused_between_polls(self):
        for replacement in (False,True):
            with self.subTest(replacement=replacement):
                self.watch = workflow.StartupWatch(self.path,self.launch_id,0)
                if replacement:
                    alternate=self.root/"alternate"
                    alternate.write_bytes(self.path.read_bytes())
                    os.replace(alternate,self.path)
                else:
                    self.path.write_bytes(b'')
                with self.assertRaises((progress.ProgressError,OSError)):
                    self.watch.observe(1)
                self.path.unlink()
                self.launch_id=progress.create_progress(self.path)

    def test_partial_append_never_changes_budget_and_clock_wall_time_is_not_used(self):
        self.publisher.phase("runtime")
        self.watch.observe(1)
        with self.path.open("ab") as stream:stream.write(b'{"phase":"worker_')
        self.watch.observe(299)
        self.assertEqual(self.watch.deadline,300)
        self.assertFalse(self.watch.observe(300))
        self.assertTrue(self.watch.partial)

    def test_backward_utc_clock_does_not_affect_monotonic_phase_limits(self):
        with patch.object(progress,"utc_now",return_value="2099-01-01T00:00:00.000+00:00"):
            self.publisher.phase("runtime")
        self.watch.observe(1)
        with patch.object(progress,"utc_now",return_value="2000-01-01T00:00:00.000+00:00"):
            self.publisher.phase("worker_verification")
        self.watch.observe(2)
        self.assertEqual(self.watch.deadline,902)
        self.assertFalse(self.watch.observe(902))


if __name__=="__main__":unittest.main()
