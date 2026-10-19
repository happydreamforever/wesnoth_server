"""Capture a bounded file-sharing reproduction without opening MongoDB's data.

Run while Process Monitor records diagnostics/mongo-file-probe-* paths from all
processes. This is a generic filesystem probe, not a database or repair test.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def run_probe(parent: Path, iterations: int = 20, delay: float = 0.05) -> int:
    if not 1 <= iterations <= 100 or not 0 <= delay <= 1:
        raise ValueError("Probe bounds exceeded")
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="mongo-file-probe-", dir=parent))
    report = scratch / "events.jsonl"
    source = scratch / "WiredTiger.turtle.set"
    target = scratch / "WiredTiger.turtle"
    print(f"Probe PID: {os.getpid()}", flush=True)
    print(f"Scratch folder: {scratch}", flush=True)
    print(f"Report: {report}", flush=True)
    print("MongoDB stays stopped; the existing runtime is not accessed.", flush=True)

    with report.open("x", encoding="utf-8", newline="\n") as log:
        def emit(event: str, **fields):
            log.write(json.dumps({"event": event, "utc": datetime.now(timezone.utc).isoformat(),
                                  "pid": os.getpid(), **fields}) + "\n")
            log.flush()

        emit("START", scratch=str(scratch), iterations=iterations,
             operation="create/write/flush/fsync/close/os.replace", platform=sys.platform)
        for iteration in range(1, iterations + 1):
            operation = "create"
            try:
                # xb never overwrites a leftover source, and all paths belong to
                # the new unique scratch directory. The target is our own file.
                with source.open("xb") as stream:
                    operation = "write"
                    stream.write(f"Wesnoth file-sharing probe {iteration}\n".encode("ascii"))
                    operation = "flush"
                    stream.flush()
                    operation = "fsync"
                    os.fsync(stream.fileno())
                    operation = "close"
                operation = "replace"
                os.replace(source, target)
            except OSError as exc:
                details = {"iteration": iteration, "operation": operation,
                           "error_type": type(exc).__name__, "errno": exc.errno,
                           "winerror": getattr(exc, "winerror", None)}
                emit("FAIL", **details)
                print("FILE PROBE FAILED: " + json.dumps(details), flush=True)
                print("Stopped at the first error; scratch files were preserved.", flush=True)
                return 1
            emit("PASS", iteration=iteration)
            if iteration < iterations:
                time.sleep(delay)
        emit("COMPLETE", iterations=iterations,
             limitation="Generic file probe only; MongoDB conflict may not reproduce here.")
    print(f"FILE PROBE COMPLETED: {iterations} replacements; scratch files preserved.", flush=True)
    print("This does not prove MongoDB startup is fixed. Return the trace and report.", flush=True)
    return 0


def main() -> int:
    if sys.platform != "win32":
        print("ERROR: Run this diagnostic with native Windows Python.", file=sys.stderr)
        return 2
    try:
        return run_probe(Path(__file__).resolve().parents[1] / "diagnostics")
    except OSError as exc:
        print("PROBE COLLECTION ERROR: " + json.dumps({
            "error_type": type(exc).__name__, "errno": exc.errno,
            "winerror": getattr(exc, "winerror", None)}), file=sys.stderr)
        print("Any created scratch files were preserved; send this output.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
