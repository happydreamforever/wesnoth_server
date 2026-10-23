"""Read-only, bounded health check of the fixed local Alliance account service."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import queue
import re
import socket
import stat
import threading

MAX_BYTES = 32768
SOCKET_TIMEOUT = 6
WORKER_TIMEOUT = 6


class InvalidConfiguration(Exception):
    pass


def parse_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError()
            value[key] = item
        return value
    def constant(_):
        raise ValueError()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 8:
            raise ValueError()
        if isinstance(item, (dict, list)):
            pending.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))
    return value


def configuration_secret(runtime: Path) -> str:
    """Read only the selected ordinary configuration; never discover .env."""
    if not runtime.is_absolute() or ".." in runtime.parts:
        raise InvalidConfiguration()
    path = runtime / "config.json"
    try:
        for item in (path, *path.parents):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise InvalidConfiguration()
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
            raise InvalidConfiguration()
        with path.open("rb") as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES
                    or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)):
                raise InvalidConfiguration()
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidConfiguration()
        value = parse_json(raw)
        if not isinstance(value, dict) or type(value.get("format")) is not int or value["format"] != 1:
            raise InvalidConfiguration()
        if value.get("purpose") != "wesnoth-alliance-local" or not isinstance(value.get("service"), dict):
            raise InvalidConfiguration()
        service = value["service"]
        secret = service.get("bridge_secret")
        if (service.get("host") != "127.0.0.1" or type(service.get("port")) is not int
                or service["port"] != 18765 or not isinstance(secret, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{43,128}", secret) is None):
            raise InvalidConfiguration()
        return secret
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise InvalidConfiguration() from None


def result(outcome: str, *, error=None):
    return {
        "format": 1, "purpose": "wesnoth-alliance-backend-check",
        "status": "passed" if outcome == "healthy" else "failed",
        "endpoint": "127.0.0.1:18765", "method": "GET", "path": "/internal/v1/health",
        "outcome": outcome, "http_status": None, "network_error": error,
        "implementation_release": None,
        "checks": {"application_json": False, "status_ok": False,
                   "service_alliance": False, "api_v1": False},
    }


def request_health(secret: str):
    report = result("network_error")
    connection = http.client.HTTPConnection("127.0.0.1", 18765, timeout=SOCKET_TIMEOUT)
    try:
        # HTTPConnection uses a direct socket: no proxy, URL override or redirects.
        connection.request("GET", "/internal/v1/health", headers={
            "Authorization": "Bearer " + secret, "Connection": "close",
        })
        response = connection.getresponse()
        report["http_status"] = response.status
        if sum(len(name) + len(value) + 4 for name, value in response.getheaders()) > 8192:
            report["outcome"] = "response_headers_too_large"
            return report
        report["checks"]["application_json"] = response.getheader("Content-Type", "").startswith("application/json")
        if response.status != 200:
            report["outcome"] = "http_rejected"
            return report
        if not report["checks"]["application_json"]:
            report["outcome"] = "unexpected_content_type"
            return report
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            report["outcome"] = "response_too_large"
            return report
        try:
            value = parse_json(raw)
        except (ValueError, RecursionError):
            report["outcome"] = "invalid_json"
            return report
        if isinstance(value, dict):
            report["checks"]["status_ok"] = value.get("status") == "ok"
            report["checks"]["service_alliance"] = value.get("service") == "alliance"
            report["checks"]["api_v1"] = type(value.get("api_version")) is int and value["api_version"] == 1
            # Optional public metadata only. This generic diagnostic remains
            # compatible with older API1 services; release policy belongs to
            # the versioned workflow launcher, not its health verdict.
            release = value.get("implementation_release")
            if type(release) is int and 1 <= release <= 2147483647:
                report["implementation_release"] = release
        report["outcome"] = "healthy" if all(report["checks"].values()) else "unexpected_health"
        report["status"] = "passed" if report["outcome"] == "healthy" else "failed"
        return report
    except (socket.timeout, TimeoutError):
        return result("timeout", error="timeout")
    except ConnectionRefusedError:
        return result("network_error", error="connection_refused")
    except ConnectionResetError:
        return result("network_error", error="connection_reset")
    except ConnectionAbortedError:
        return result("network_error", error="connection_aborted")
    except http.client.HTTPException:
        return result("network_error", error="protocol_error")
    except OSError:
        return result("network_error", error="io_error")
    finally:
        connection.close()


def collect(runtime: Path):
    try:
        secret = configuration_secret(runtime)
    except InvalidConfiguration:
        return result("invalid_configuration")
    outcomes = queue.SimpleQueue()

    def worker():
        try:
            outcomes.put(request_health(secret))
        except Exception:
            # No exception text: it can contain request or response material.
            outcomes.put(result("network_error", error="unexpected_error"))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(WORKER_TIMEOUT)
    if thread.is_alive():
        return result("timeout", error="total_deadline")
    return outcomes.get_nowait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Reserve the unique report before making any authenticated request.
        with args.report.open("x", encoding="ascii", newline="\n") as output:
            report = collect(args.runtime)
            json.dump(report, output, indent=2, ensure_ascii=True)
            output.write("\n")
    except (OSError, ValueError):
        print("ALLIANCE BACKEND CHECK FAILED: report unavailable; existing files preserved.")
        return 1
    print("outcome=" + report["outcome"] + "; http_status=" + str(report["http_status"]))
    print("; ".join(name + "=" + str(value) for name, value in report["checks"].items()))
    print("network_error=" + str(report["network_error"]))
    print("ALLIANCE BACKEND CHECK " + ("PASSED" if report["status"] == "passed" else "FAILED"))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
