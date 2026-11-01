"""Explicit Court reset into runtime-v3, retaining the verified private cold archive."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.alliance_fresh_start import fresh_start, report_initialization_error
from tools import alliance_maintenance as maintenance
from alliance.deployment import InitializationError, _initialization_reason


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-runtime', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--mongod', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = fresh_start(args.previous_runtime, args.backup, args.runtime, args.mongod, product='court')
    except InitializationError as error:
        report_initialization_error(error)
        return 1
    except maintenance.MaintenanceError as error:
        print('COURT FRESH START STOPPED: ' + str(error))
        print('Keep the private backup and both runtime directories. No previous game was deleted.')
        return 1
    except (Exception, KeyboardInterrupt) as error:
        report_initialization_error(InitializationError('court-fresh-start', _initialization_reason(error)))
        return 1
    print('COURT FRESH GAME VERIFIED')
    print(json.dumps(result, sort_keys=True))
    print('Use runtime-v3 for all five services. Create new player accounts; previous game data stays in the private archive.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
