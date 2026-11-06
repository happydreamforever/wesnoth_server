"""Read-only validation of explicitly selected development runtime and identity."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.config import ConfigurationError, LocalMongo, Settings
from tools.alliance_maintenance import validate_runtime, MaintenanceError
from tools.alliance_transport import verify_identity, TransportError


def check(runtime, identity, address, port, name, replica_set):
    expected = LocalMongo(port, name, replica_set)
    if not Path(runtime).exists():
        raise ConfigurationError("The selected runtime is absent. Restore a verified private backup or explicitly initialize a new development runtime.")
    selected = validate_runtime(runtime)
    if Settings.load(selected).database != expected:
        raise ConfigurationError("The .env MongoDB settings differ from the saved runtime. Existing configuration and data were preserved; select the matching settings or a separate new runtime.")
    verify_identity(identity, address, 15001)
    print("WINDOWS DEVELOPMENT CONFIGURATION VERIFIED")
    print("Saved local database endpoint and pinned server identity match the selected .env settings.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--server-ip', required=True)
    parser.add_argument('--mongo-port', type=int, required=True)
    parser.add_argument('--mongo-database', required=True)
    parser.add_argument('--mongo-replica-set', required=True)
    args = parser.parse_args()
    try:
        check(args.runtime, args.identity, args.server_ip, args.mongo_port,
              args.mongo_database, args.mongo_replica_set)
        return 0
    except (ConfigurationError, MaintenanceError, TransportError):
        print('ERROR: Development settings do not match a verified runtime and identity. Check the selected paths, MongoDB settings and server IP; existing files were preserved.', file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print('ERROR: Development configuration verification stopped; no private configuration contents were printed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
