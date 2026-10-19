"""Small, explicit local operator CLI. Secrets are never accepted as arguments."""
import argparse
from pathlib import Path
import sys
import subprocess

from pymongo.errors import PyMongoError

from .config import ConfigurationError
from .auth import AuthError
from .domain import DomainError
from .deployment import initialize, run_database, check_database, serve


def main():
    parser = argparse.ArgumentParser(description="Offline Alliance persistence and admin service")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--mongod", type=Path)
    parser.add_argument("command", choices=("init", "database", "serve", "check"))
    args = parser.parse_args()
    try:
        if args.command in ("init", "database"):
            if args.mongod is None:
                parser.error("--mongod is required for init/database")
            (initialize if args.command == "init" else run_database)(args.runtime, args.mongod)
        else:
            (serve if args.command == "serve" else check_database)(args.runtime)
    except (ConfigurationError, AuthError, DomainError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    except PyMongoError as exc:
        # PyMongo exception strings can include addresses, user names or config.
        print(f"ERROR: Local database operation failed ({type(exc).__name__}). Preserve the runtime and check its database window.", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: Local filesystem or process operation failed ({type(exc).__name__}). Preserve the runtime and report this error.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped. Existing runtime data preserved.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
