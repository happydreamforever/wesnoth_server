"""Metadata guard/API boundary tests; fake Win32 calls are not Windows validation."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import ctypes
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "inspect_windows_caller_regions", ROOT / "tools/inspect_windows_caller_regions.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def identity():
    return {"pid": 4600, "image": inspector.EXPECTED_IMAGE,
            "creation_filetime": 134367890590000001,
            "creation_local_second": "2026-10-17T03:24:19",
            "exit_code": 259, "exit_filetime": None}


def region(address, state=inspector.MEM_COMMIT, kind=inspector.MEM_PRIVATE):
    return {"BaseAddress": address & ~0xFFF, "AllocationBase": 0x10000000,
            "AllocationProtect": 0x40, "RegionSize": 4096, "State": state,
            "Protect": 0x120, "Type": kind}


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.before, self.after = identity(), identity()
        self.identity_count = 0
        self.open_error = self.query_error = self.map_error = self.close_error = None
        self.region_function = region

    def open_process(self):
        self.calls.append(("open",))
        if self.open_error:
            raise self.open_error
        return 73

    def identity(self, handle):
        self.calls.append(("identity", handle))
        self.identity_count += 1
        return copy.deepcopy(self.before if self.identity_count == 1 else self.after)

    def query_region(self, handle, address):
        self.calls.append(("query", handle, address))
        if self.query_error:
            raise self.query_error
        return self.region_function(address)

    def mapped_filename(self, handle, address):
        self.calls.append(("mapped", handle, address))
        if self.map_error:
            raise self.map_error
        return r"\Device\HarddiskVolume3\fixture.dll"

    def close_handle(self, handle):
        self.calls.append(("close", handle))
        if self.close_error:
            raise self.close_error


class NativeFunction:
    def __init__(self, implementation):
        self.implementation = implementation
        self.calls = []

    def __call__(self, *arguments):
        self.calls.append(arguments)
        return self.implementation(*arguments)


class NativeDLL:
    def __init__(self):
        self.OpenProcess = NativeFunction(lambda *args: 73)
        self.CloseHandle = NativeFunction(lambda *args: 1)
        self.QueryFullProcessImageNameW = NativeFunction(self.image)
        self.GetProcessTimes = NativeFunction(self.times)
        self.GetExitCodeProcess = NativeFunction(self.exit_code)
        self.VirtualQueryEx = NativeFunction(self.query)
        self.K32GetMappedFileNameW = NativeFunction(self.mapped)

    @staticmethod
    def image(handle, flags, buffer, count):
        buffer.value = inspector.EXPECTED_IMAGE
        ctypes.cast(count, ctypes.POINTER(inspector.DWORD)).contents.value = len(buffer.value)
        return 1

    @staticmethod
    def times(handle, created, exited, kernel, user):
        value = ctypes.cast(created, ctypes.POINTER(inspector.FILETIME)).contents
        ticks = 134367890590000001
        value.low, value.high = ticks & 0xFFFFFFFF, ticks >> 32
        # An active process's exit FILETIME is undefined and must not be trusted.
        undefined_exit = ctypes.cast(exited, ctypes.POINTER(inspector.FILETIME)).contents
        undefined_exit.low, undefined_exit.high = 1234, 5678
        return 1

    @staticmethod
    def exit_code(handle, code):
        ctypes.cast(code, ctypes.POINTER(inspector.DWORD)).contents.value = 259
        return 1

    @staticmethod
    def query(handle, address, output, length):
        value = ctypes.cast(output, ctypes.POINTER(inspector.MEMORY_BASIC_INFORMATION64)).contents
        for name, content in region(address).items():
            setattr(value, name, content)
        return 48

    @staticmethod
    def mapped(handle, address, buffer, length):
        buffer.value = r"\Device\HarddiskVolume3\fixture.dll"
        return len(buffer.value)


class CallerRegionTests(unittest.TestCase):
    def collect(self, api=None):
        api = api or FakeAPI()
        return inspector.collect_metadata(lambda: api)

    def test_fixed_target_and_thirteen_exact_addresses(self):
        self.assertEqual(inspector.TARGET_PID, 4600)
        self.assertEqual(inspector.ADDRESSES, (
            0x100FE806, 0x100FEBC9, 0x100FE541, 0x100FEE64, 0x1010A733,
            0x100F85AB, 0x100F85FE, 0x1002D3E8, 0x100376E2, 0x10037023,
            0x10037633, 0x10036E8A, 0x1010429F))

    def test_layout_uses_windows_widths_and_64_bit_offsets(self):
        self.assertEqual(ctypes.sizeof(inspector.DWORD), 4)
        self.assertEqual(ctypes.sizeof(inspector.BOOL), 4)
        self.assertEqual(ctypes.sizeof(inspector.FILETIME), 8)
        structure = inspector.MEMORY_BASIC_INFORMATION64
        self.assertEqual(ctypes.sizeof(structure), 48)
        for name, offset in {"BaseAddress": 0, "AllocationBase": 8,
                             "AllocationProtect": 16, "RegionSize": 24,
                             "State": 32, "Protect": 36, "Type": 40}.items():
            self.assertEqual(getattr(structure, name).offset, offset)

    def test_success_uses_one_handle_for_two_guards_and_exact_queries(self):
        api = FakeAPI()
        report = self.collect(api)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["errors"], [])
        self.assertEqual(api.calls, [("open",), ("identity", 73)]
                         + [("query", 73, address) for address in inspector.ADDRESSES]
                         + [("identity", 73), ("close", 73)])
        self.assertEqual([row["address"] for row in report["regions"]],
                         [hex(address) for address in inspector.ADDRESSES])
        self.assertTrue(all(row["mapped_file"]["status"] == "not_applicable"
                            for row in report["regions"]))

    def test_wrong_image_pid_time_or_exited_process_never_queries(self):
        for field, value in (("pid", 4601), ("image", r"C:\other\svchost.exe"),
                             ("creation_local_second", "2026-10-17T03:24:20"),
                             ("exit_code", 0)):
            with self.subTest(field=field):
                api = FakeAPI()
                api.before[field] = value
                result = self.collect(api)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["regions"], [])
                self.assertEqual(api.calls, [("open",), ("identity", 73), ("close", 73)])
                self.assertEqual(result["errors"][0]["operation"], "identity_before")

    def test_image_comparison_is_case_insensitive(self):
        api = FakeAPI()
        api.before["image"] = api.after["image"] = inspector.EXPECTED_IMAGE.upper()
        self.assertEqual(self.collect(api)["status"], "complete")

    def test_open_denied_records_exact_error_and_does_not_try_another_pid(self):
        for code in (5, 87):
            api = FakeAPI()
            api.open_error = inspector.CollectionError("OpenProcess", "win32_call_failed", code)
            report = self.collect(api)
            self.assertEqual(report["errors"][0]["winerror"], code)
            self.assertEqual(api.calls, [("open",)])
            self.assertEqual(report["regions"], [])

    def test_private_free_reserved_and_image_metadata_semantics(self):
        cases = [(inspector.MEM_COMMIT, inspector.MEM_PRIVATE, False),
                 (inspector.MEM_FREE, inspector.MEM_IMAGE, False),
                 (inspector.MEM_RESERVE, inspector.MEM_PRIVATE, False),
                 (inspector.MEM_COMMIT, inspector.MEM_IMAGE, True),
                 (inspector.MEM_COMMIT, inspector.MEM_MAPPED, True)]
        for state, kind, mapped in cases:
            with self.subTest(state=state, kind=kind):
                api = FakeAPI()
                api.region_function = lambda address: region(address, state, kind)
                report = self.collect(api)
                self.assertEqual(report["status"], "complete")
                self.assertEqual(sum(call[0] == "mapped" for call in api.calls), 13 if mapped else 0)
                row = report["regions"][0]
                self.assertEqual(row["mapped_file"]["status"], "available" if mapped else "not_applicable")
                if state == inspector.MEM_FREE:
                    for key in ("allocation_base", "allocation_protection", "protection", "type"):
                        self.assertIsNone(row[key])
                elif state == inspector.MEM_RESERVE:
                    self.assertIsNone(row["protection"])
                    self.assertIsNotNone(row["allocation_base"])
                else:
                    self.assertEqual(row["protection"]["flags"], ["PAGE_EXECUTE_READ", "PAGE_GUARD"])

    def test_mapping_failure_does_not_claim_no_file(self):
        api = FakeAPI()
        api.region_function = lambda address: region(address, kind=inspector.MEM_IMAGE)
        api.map_error = inspector.CollectionError("K32GetMappedFileNameW", "win32_call_failed", 299)
        report = self.collect(api)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(report["regions"]), 13)
        self.assertEqual(len(report["errors"]), 13)
        for row in report["regions"]:
            self.assertEqual(row["mapped_file"]["status"], "unavailable")
            self.assertIsNone(row["mapped_file"]["path"])
            self.assertEqual(row["mapped_file"]["error"]["winerror"], 299)

    def test_query_failure_is_bounded_and_still_checks_end_identity(self):
        api = FakeAPI()
        api.query_error = inspector.CollectionError("VirtualQueryEx", "win32_call_failed", 87)
        report = self.collect(api)
        self.assertEqual(len(report["errors"]), 13)
        self.assertEqual(len(report["regions"]), 13)
        self.assertEqual(api.identity_count, 2)
        self.assertEqual(api.calls[-1], ("close", 73))

    def test_malformed_region_is_not_reported_as_valid(self):
        for base, size in ((0, 0), (0, 4096), (0x100FE000, 1 << 64)):
            api = FakeAPI()
            def bad_region(address):
                result = region(address)
                result.update(BaseAddress=base, RegionSize=size)
                return result
            api.region_function = bad_region
            result = self.collect(api)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["errors"][0]["reason"], "returned_region_does_not_cover_address")

    def test_end_guard_rejects_exit_and_subsecond_creation_change(self):
        for field, value in (("creation_filetime", identity()["creation_filetime"] + 1),
                             ("exit_code", 0),
                             ("creation_local_second", "2026-10-17T02:24:19")):
            api = FakeAPI()
            api.after[field] = value
            report = self.collect(api)
            self.assertEqual(len(report["regions"]), 13)
            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(report["errors"][-1]["operation"], "identity_after")
            self.assertEqual(api.calls[-1], ("close", 73))

    def test_unexpected_exception_closes_handle_without_leaking_text(self):
        api = FakeAPI()
        api.query_error = RuntimeError("synthetic sensitive exception sentinel")
        result = self.collect(api)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(api.calls[-1], ("close", 73))
        self.assertNotIn("sentinel", json.dumps(result))
        self.assertEqual(result["errors"][-1]["error_type"], "RuntimeError")

    def test_close_failure_keeps_report_but_does_not_claim_completion(self):
        api = FakeAPI()
        api.close_error = inspector.CollectionError("CloseHandle", "win32_call_failed", 6)
        report = self.collect(api)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["errors"][-1]["winerror"], 6)
        self.assertEqual(sum(call[0] == "close" for call in api.calls), 1)

    def test_unknown_protection_bits_are_retained(self):
        self.assertEqual(inspector.protection(0x1004), {
            "value": "0x1004", "flags": ["PAGE_READWRITE", "UNKNOWN_0x1000"]})

    def test_filetime_preserves_exact_ticks_and_labels_local_conversion(self):
        value = inspector.FILETIME(low=1, high=31284962)
        ticks = inspector.filetime_ticks(value)
        result = inspector.creation_fields(ticks)
        self.assertEqual(result["creation_filetime"], ticks)
        self.assertIsNotNone(datetime.fromisoformat(result["creation_utc"]).tzinfo)
        self.assertIsNotNone(datetime.fromisoformat(result["creation_local"]).tzinfo)
        self.assertIsNone(datetime.fromisoformat(result["creation_local_second"]).tzinfo)
        self.assertIn("timezone", inspector.new_report()["target"]["creation_time_guard"])

    def test_native_boundary_binds_queries_only_and_uses_expected_sizes(self):
        dll = NativeDLL()
        api = inspector.NativeAPI(dll)
        handle = api.open_process()
        self.assertEqual(dll.OpenProcess.calls, [(0x400, False, 4600)])
        self.assertIs(dll.OpenProcess.restype, ctypes.c_void_p)
        observed = api.identity(handle)
        self.assertEqual(observed["image"], inspector.EXPECTED_IMAGE)
        self.assertEqual(observed["creation_filetime"], 134367890590000001)
        self.assertIsNone(observed["exit_filetime"])
        raw = api.query_region(handle, inspector.ADDRESSES[0])
        self.assertEqual(raw["RegionSize"], 4096)
        self.assertEqual(dll.VirtualQueryEx.calls[0][-1], 48)
        self.assertEqual(api.mapped_filename(handle, inspector.ADDRESSES[0]),
                         r"\Device\HarddiskVolume3\fixture.dll")
        self.assertEqual(dll.K32GetMappedFileNameW.calls[0][-1], 32768)
        api.close_handle(handle)
        self.assertEqual(dll.CloseHandle.calls, [(73,)])

    def test_native_zero_return_retains_winerror(self):
        dll = NativeDLL()
        api = inspector.NativeAPI(dll)
        for name, call in (
                ("OpenProcess", lambda: api.open_process()),
                ("VirtualQueryEx", lambda: api.query_region(73, inspector.ADDRESSES[0])),
                ("K32GetMappedFileNameW", lambda: api.mapped_filename(73, inspector.ADDRESSES[0]))):
            old = getattr(dll, name).implementation
            getattr(dll, name).implementation = lambda *args: 0
            with patch.object(ctypes, "get_last_error", return_value=5, create=True):
                with self.assertRaises(inspector.CollectionError) as context:
                    call()
            self.assertEqual(context.exception.details["winerror"], 5)
            getattr(dll, name).implementation = old

    def test_keyboard_interrupt_saves_incomplete_metadata_and_closes_handle(self):
        api = FakeAPI()
        api.query_error = KeyboardInterrupt()
        report = self.collect(api)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["errors"][-1]["reason"], "interrupted")
        self.assertEqual(api.calls[-1], ("close", 73))

    def test_runtime_structure_layout_guard_fails_before_opening_process(self):
        original = ctypes.sizeof
        def sizeof(value):
            return 44 if value is inspector.MEMORY_BASIC_INFORMATION64 else original(value)
        dll = NativeDLL()
        with patch.object(ctypes, "sizeof", side_effect=sizeof):
            with self.assertRaises(inspector.CollectionError) as context:
                inspector.NativeAPI(dll)
        self.assertEqual(context.exception.details["reason"], "unexpected_memory_information_layout")
        self.assertEqual(dll.OpenProcess.calls, [])

    def test_native_short_mbi_and_truncated_filename_are_rejected(self):
        dll = NativeDLL()
        api = inspector.NativeAPI(dll)
        dll.VirtualQueryEx.implementation = lambda *args: 28
        with self.assertRaises(inspector.CollectionError) as context:
            api.query_region(73, inspector.ADDRESSES[0])
        self.assertEqual(context.exception.details["reason"], "unexpected_structure_size")
        dll.K32GetMappedFileNameW.implementation = lambda *args: 32768
        with self.assertRaises(inspector.CollectionError) as context:
            api.mapped_filename(73, inspector.ADDRESSES[0])
        self.assertEqual(context.exception.details["reason"], "buffer_limit_reached")
        self.assertEqual(len(dll.K32GetMappedFileNameW.calls), 1)

    def test_native_refuses_other_platform_and_32_bit_host(self):
        with patch.object(inspector.sys, "platform", "linux"):
            result = inspector.collect_metadata()
        self.assertEqual(result["errors"][0]["reason"], "native_64_bit_windows_python_required")
        self.assertEqual(result["regions"], [])
        original_sizeof = ctypes.sizeof
        def sizeof(value):
            return 4 if value is ctypes.c_void_p else original_sizeof(value)
        with patch.object(inspector.sys, "platform", "win32"), \
                patch.object(ctypes, "sizeof", side_effect=sizeof):
            result = inspector.collect_metadata()
        self.assertEqual(result["errors"][0]["operation"], "platform")

    def test_unique_reports_preserve_existing_runtime_env_and_reports(self):
        with tempfile.TemporaryDirectory(prefix="caller metadata with spaces ") as folder:
            root = Path(folder)
            diagnostics = root / "diagnostics"
            (root / "runtime").mkdir()
            sentinels = {root / ".env": b"synthetic secret", root / "runtime/db": b"database"}
            for path, content in sentinels.items():
                path.write_bytes(content)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(inspector.run_collection(diagnostics, FakeAPI), 0)
                before = {p: p.read_bytes() for p in diagnostics.iterdir()}
                self.assertEqual(inspector.run_collection(diagnostics, FakeAPI), 0)
            self.assertEqual(len(list(diagnostics.glob("caller-regions-*.json"))), 2)
            for path, content in {**sentinels, **before}.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertIn("WINDOWS CALLER METADATA COLLECTED", output.getvalue())

    def test_failure_report_is_saved_with_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            def denied():
                raise inspector.CollectionError("OpenProcess", "win32_call_failed", 5)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(inspector.run_collection(Path(folder), denied), 1)
            report, = Path(folder).glob("caller-regions-*.json")
            self.assertEqual(json.loads(report.read_text())["errors"][0]["winerror"], 5)
            self.assertIn("Report saved:", output.getvalue())
            self.assertNotIn("WINDOWS CALLER METADATA COLLECTED", output.getvalue())

    def test_exclusive_output_collision_does_not_query_or_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(inspector.uuid, "uuid4") as fixed, \
                    patch.object(inspector, "datetime") as clock:
                fixed.return_value.hex = "fixed"
                clock.now.return_value.strftime.return_value = "fixed"
                target = Path(folder) / "caller-regions-fixed-fixed.json"
                target.write_bytes(b"retained evidence")
                with patch.object(inspector, "collect_metadata") as collect:
                    with self.assertRaises(FileExistsError):
                        inspector.run_collection(Path(folder))
                collect.assert_not_called()
                self.assertEqual(target.read_bytes(), b"retained evidence")

    def test_cli_disallows_target_or_address_overrides(self):
        with patch.object(inspector.sys, "argv", ["collector.py", "--pid", "1"]), \
                patch.object(inspector, "run_collection") as collect, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(inspector.main(), 2)
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
