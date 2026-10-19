"""Inspect metadata at thirteen recorded caller addresses in one Windows process.

This diagnostic never reads process memory bytes. It queries only the captured
PID after a same-handle image/creation-time check, and writes a new JSON report.
The result describes current mappings, not what occupied them during the capture.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timedelta, timezone
import json
import ntpath
from pathlib import Path
import platform
import sys
import uuid


TARGET_PID = 4600
EXPECTED_IMAGE = r"C:\Windows\SysWOW64\svchost.exe"
EXPECTED_CREATION_LOCAL = "2026-10-17T03:24:19"
ADDRESSES = (
    0x100FE806, 0x100FEBC9, 0x100FE541, 0x100FEE64, 0x1010A733,
    0x100F85AB, 0x100F85FE, 0x1002D3E8, 0x100376E2, 0x10037023,
    0x10037633, 0x10036E8A, 0x1010429F,
)
PROCESS_QUERY_INFORMATION = 0x0400
STILL_ACTIVE = 259
MEM_COMMIT, MEM_RESERVE, MEM_FREE = 0x1000, 0x2000, 0x10000
MEM_PRIVATE, MEM_MAPPED, MEM_IMAGE = 0x20000, 0x40000, 0x1000000
MAX_PATH_CHARS = 32768
DWORD = ctypes.c_uint32
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


class FILETIME(ctypes.Structure):
    _fields_ = [("low", DWORD), ("high", DWORD)]


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    # Explicit Windows widths/alignment also make layout tests meaningful on Linux.
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", DWORD),
        ("PartitionId", ctypes.c_uint16),
        ("_alignment1", ctypes.c_uint16),
        ("RegionSize", ctypes.c_uint64),
        ("State", DWORD), ("Protect", DWORD), ("Type", DWORD),
        ("_alignment2", DWORD),
    ]


class CollectionError(Exception):
    def __init__(self, operation: str, reason: str, winerror: int | None = None):
        super().__init__(reason)
        self.details = {"operation": operation, "reason": reason, "winerror": winerror}


def filetime_ticks(value: FILETIME) -> int:
    return (value.high << 32) | value.low


def creation_fields(ticks: int) -> dict:
    seconds, remainder = divmod(ticks, 10_000_000)
    utc = FILETIME_EPOCH + timedelta(seconds=seconds, microseconds=remainder // 10)
    local = utc.astimezone()
    return {
        "creation_filetime": ticks,
        "creation_utc": utc.isoformat(),
        "creation_local": local.isoformat(),
        "creation_local_second": local.replace(tzinfo=None).isoformat(timespec="seconds"),
    }


class NativeAPI:
    """Only query APIs; no memory-read, privilege, process-control or dump API."""

    def __init__(self, kernel32=None):
        structure = MEMORY_BASIC_INFORMATION64
        offsets = {"BaseAddress": 0, "AllocationBase": 8, "AllocationProtect": 16,
                   "RegionSize": 24, "State": 32, "Protect": 36, "Type": 40}
        if ctypes.sizeof(structure) != 48 or any(
                getattr(structure, name).offset != offset for name, offset in offsets.items()):
            raise CollectionError("platform", "unexpected_memory_information_layout")
        if kernel32 is None:
            if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
                raise CollectionError("platform", "native_64_bit_windows_python_required")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.dll = kernel32
        signatures = {
            "OpenProcess": ([DWORD, BOOL, DWORD], HANDLE),
            "CloseHandle": ([HANDLE], BOOL),
            "QueryFullProcessImageNameW": (
                [HANDLE, DWORD, ctypes.c_wchar_p, ctypes.POINTER(DWORD)], BOOL),
            "GetProcessTimes": (
                [HANDLE] + [ctypes.POINTER(FILETIME)] * 4, BOOL),
            "GetExitCodeProcess": ([HANDLE, ctypes.POINTER(DWORD)], BOOL),
            "VirtualQueryEx": (
                [HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
                 ctypes.c_size_t], ctypes.c_size_t),
            "K32GetMappedFileNameW": (
                [HANDLE, ctypes.c_void_p, ctypes.c_wchar_p, DWORD], DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel32, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def failure(operation: str):
        raise CollectionError(operation, "win32_call_failed", ctypes.get_last_error())

    def open_process(self):
        handle = self.dll.OpenProcess(PROCESS_QUERY_INFORMATION, False, TARGET_PID)
        if not handle:
            self.failure("OpenProcess")
        return handle

    def close_handle(self, handle):
        if not self.dll.CloseHandle(handle):
            self.failure("CloseHandle")

    def identity(self, handle) -> dict:
        buffer = ctypes.create_unicode_buffer(MAX_PATH_CHARS)
        length = DWORD(MAX_PATH_CHARS)
        if not self.dll.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            self.failure("QueryFullProcessImageNameW")
        if not 0 < length.value < MAX_PATH_CHARS:
            raise CollectionError("QueryFullProcessImageNameW", "invalid_or_truncated_length")
        created, exited, kernel, user = (FILETIME() for _ in range(4))
        if not self.dll.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel), ctypes.byref(user)):
            self.failure("GetProcessTimes")
        code = DWORD()
        if not self.dll.GetExitCodeProcess(handle, ctypes.byref(code)):
            self.failure("GetExitCodeProcess")
        return {"pid": TARGET_PID, "image": buffer[:length.value],
                **creation_fields(filetime_ticks(created)),
                # GetProcessTimes exit time is undefined while the process runs.
                "exit_filetime": None if code.value == STILL_ACTIVE else filetime_ticks(exited),
                "exit_code": code.value}

    def query_region(self, handle, address: int) -> dict:
        result = MEMORY_BASIC_INFORMATION64()
        count = self.dll.VirtualQueryEx(handle, address, ctypes.byref(result), ctypes.sizeof(result))
        if count == 0:
            self.failure("VirtualQueryEx")
        if count != ctypes.sizeof(result):
            raise CollectionError("VirtualQueryEx", "unexpected_structure_size")
        return {name: int(getattr(result, name)) for name in (
            "BaseAddress", "AllocationBase", "AllocationProtect", "RegionSize",
            "State", "Protect", "Type")}

    def mapped_filename(self, handle, address: int) -> str:
        buffer = ctypes.create_unicode_buffer(MAX_PATH_CHARS)
        count = self.dll.K32GetMappedFileNameW(handle, address, buffer, MAX_PATH_CHARS)
        if count == 0:
            self.failure("K32GetMappedFileNameW")
        if count >= MAX_PATH_CHARS:
            raise CollectionError("K32GetMappedFileNameW", "buffer_limit_reached")
        return buffer[:count]


def matches_expected(identity: dict) -> bool:
    return (identity["pid"] == TARGET_PID
            and ntpath.normcase(identity["image"]) == ntpath.normcase(EXPECTED_IMAGE)
            and identity["creation_local_second"] == EXPECTED_CREATION_LOCAL
            and identity["exit_code"] == STILL_ACTIVE)


def protection(value: int) -> dict:
    names = {
        0x01: "PAGE_NOACCESS", 0x02: "PAGE_READONLY", 0x04: "PAGE_READWRITE",
        0x08: "PAGE_WRITECOPY", 0x10: "PAGE_EXECUTE", 0x20: "PAGE_EXECUTE_READ",
        0x40: "PAGE_EXECUTE_READWRITE", 0x80: "PAGE_EXECUTE_WRITECOPY",
        0x100: "PAGE_GUARD", 0x200: "PAGE_NOCACHE", 0x400: "PAGE_WRITECOMBINE",
        0x40000000: "PAGE_TARGETS_INVALID_OR_NO_UPDATE",
    }
    flags = [name for bit, name in names.items() if value & bit]
    unknown = value & ~sum(names)
    if unknown:
        flags.append("UNKNOWN_" + hex(unknown))
    return {"value": hex(value), "flags": flags}


def describe_region(address: int, raw: dict) -> dict:
    base, size, state = raw["BaseAddress"], raw["RegionSize"], raw["State"]
    if not (0 <= base <= address < base + size <= 1 << 64):
        raise CollectionError("VirtualQueryEx", "returned_region_does_not_cover_address")
    free = state == MEM_FREE
    return {
        "address": hex(address), "base_address": hex(base), "region_size": size,
        "allocation_base": None if free else hex(raw["AllocationBase"]),
        "allocation_protection": None if free else protection(raw["AllocationProtect"]),
        "state": {"value": hex(state), "name": {
            MEM_COMMIT: "MEM_COMMIT", MEM_RESERVE: "MEM_RESERVE", MEM_FREE: "MEM_FREE",
        }.get(state, "UNKNOWN")},
        "protection": None if state in (MEM_FREE, MEM_RESERVE) else protection(raw["Protect"]),
        "type": None if free else {"value": hex(raw["Type"]), "name": {
            MEM_PRIVATE: "MEM_PRIVATE", MEM_MAPPED: "MEM_MAPPED", MEM_IMAGE: "MEM_IMAGE",
        }.get(raw["Type"], "UNKNOWN")},
        "mapped_file": {"status": "not_applicable", "path": None},
    }


def new_report() -> dict:
    return {
        "schema": 1, "collected_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": sys.platform,
        "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
        "target": {"pid": TARGET_PID, "image": EXPECTED_IMAGE,
                   "creation_local_second": EXPECTED_CREATION_LOCAL,
                   "creation_time_guard": "Local wall-clock second as reported by Windows; "
                       "a changed local timezone can cause a safe mismatch."},
        "access_mask": hex(PROCESS_QUERY_INFORMATION),
        "requested_addresses": [hex(address) for address in ADDRESSES],
        "limitations": [
            "Current metadata only; not an atomic snapshot or proof of capture-time mappings.",
            "PID, image and local creation second reduce PID-reuse risk; they do not authenticate code.",
            "Private or unnamed mappings alone do not establish malicious code.",
            "No process memory bytes, command line, environment, database or credentials are read.",
        ],
        "status": "incomplete", "identity_before": None, "identity_after": None,
        "regions": [], "errors": [],
    }


def collect_metadata(api_factory=NativeAPI) -> dict:
    report = new_report()
    handle = None
    api = None
    try:
        api = api_factory()
        handle = api.open_process()
        before = api.identity(handle)
        report["identity_before"] = before
        if not matches_expected(before):
            raise CollectionError("identity_before", "captured_process_identity_not_matched")
        for address in ADDRESSES:
            try:
                raw = api.query_region(handle, address)
                region = describe_region(address, raw)
                if raw["State"] != MEM_FREE and raw["Type"] in (MEM_IMAGE, MEM_MAPPED):
                    try:
                        path = api.mapped_filename(handle, address)
                        region["mapped_file"] = {"status": "available", "path": path}
                    except CollectionError as exc:
                        region["mapped_file"] = {"status": "unavailable", "path": None,
                                                 "error": exc.details}
                        report["errors"].append({"address": hex(address), **exc.details})
                report["regions"].append(region)
            except CollectionError as exc:
                report["regions"].append({"address": hex(address), "error": exc.details})
                report["errors"].append({"address": hex(address), **exc.details})
        after = api.identity(handle)
        report["identity_after"] = after
        if not matches_expected(after) or before["creation_filetime"] != after["creation_filetime"]:
            raise CollectionError("identity_after", "process_identity_or_running_state_changed")
        if not report["errors"]:
            report["status"] = "complete"
    except CollectionError as exc:
        report["errors"].append(exc.details)
    except KeyboardInterrupt:
        report["errors"].append({"operation": "collector", "reason": "interrupted",
                                 "winerror": None})
    except Exception as exc:
        # Keep an unexpected error report without printing potentially sensitive exception text.
        report["errors"].append({"operation": "collector", "reason": "unexpected_exception",
                                 "error_type": type(exc).__name__, "winerror": None})
    finally:
        if handle is not None and api is not None:
            try:
                api.close_handle(handle)
            except Exception as exc:
                details = exc.details if isinstance(exc, CollectionError) else {
                    "operation": "CloseHandle", "reason": "unexpected_exception",
                    "error_type": type(exc).__name__, "winerror": None}
                report["errors"].append(details)
                report["status"] = "incomplete"
    return report


def run_collection(parent: Path, api_factory=NativeAPI) -> int:
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = parent / ("caller-regions-" + stamp + "-" + uuid.uuid4().hex + ".json")
    # Exclusive creation never replaces an older report, even on a name collision.
    with report_path.open("x", encoding="utf-8", newline="\n") as stream:
        report = collect_metadata(api_factory)
        json.dump(report, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(f"Report saved: {report_path}", flush=True)
    print(f"Address metadata: {report['status']}; queried rows={len(report['regions'])}; "
          f"errors={len(report['errors'])}.", flush=True)
    print("Current mapping metadata only. MongoDB and the target process were not modified.", flush=True)
    if report["status"] != "complete":
        for error in report["errors"]:
            print(f"CHECK: {error['operation']}; {error['reason']}; "
                  f"winerror={error.get('winerror')}", flush=True)
        print("Send the report; do not substitute another PID or rerun database initialization.", flush=True)
        return 2 if any(error["operation"] == "platform" for error in report["errors"]) else 1
    print("WINDOWS CALLER METADATA COLLECTED", flush=True)
    return 0


def main() -> int:
    if len(sys.argv) != 1:
        print("ERROR: This fixed-target diagnostic takes no arguments.", file=sys.stderr)
        return 2
    try:
        return run_collection(Path(__file__).resolve().parents[1] / "diagnostics")
    except OSError as exc:
        print("REPORT WRITE ERROR: " + json.dumps({
            "error_type": type(exc).__name__, "errno": exc.errno,
            "winerror": getattr(exc, "winerror", None)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
