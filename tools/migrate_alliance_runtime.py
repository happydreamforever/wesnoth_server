#!/usr/bin/env python3
"""Explicit offline schema 3->4 upgrade of the existing runtime-v2.

Always preserve a verified cold copy first. Never initialize, replace or reset
accounts, storage, identity, completed runs or replay files. Public errors are
fixed codes; the private journal and backup remain on this machine.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo.errors import PyMongoError
from alliance.deployment import _check_mongod, _client, _credentials, _uri, _write_new
from alliance.runtime_lock import runtime_lock
from alliance.schema import migrate_schema_2_to_3, migrate_schema_3_to_4
from tools.alliance_maintenance import (backup, validate_runtime, reserved_ports, battle_storage_lock,
    inventory, read_small, digest, MaintenanceError, local_path)


def migrate(runtime, destination, mongod, *, target_schema=4):
    if target_schema not in (3, 4):
        raise MaintenanceError('unsupported_migration_target')
    transition = '2-to-3' if target_schema == 3 else '3-to-4'
    migrate_database = migrate_schema_2_to_3 if target_schema == 3 else migrate_schema_3_to_4
    runtime = validate_runtime(runtime); destination = local_path(destination)
    journal = runtime / ('schema-' + transition + '.json')
    _check_mongod(mongod)
    started_journal = runtime / ('schema-' + transition + '.started.json')
    if journal.exists():
        receipt = json.loads(read_small(journal))
        if receipt.get('format') != 1 or receipt.get('backup') != str(destination):
            raise MaintenanceError('migration_resume_backup_mismatch')
    else:
        if destination.exists():
            # A crash after backup verification but before journal publication
            # resumes only when the full cold runtime still matches that copy.
            prior = json.loads(read_small(destination / 'manifest.json', 8 * 1024 * 1024))
            if (destination / 'INCOMPLETE').exists() or prior.get('files') != inventory(runtime):
                raise MaintenanceError('migration_backup_destination_exists')
        else:
            backup(runtime, destination)
        receipt = {'format': 1, 'backup': str(destination), 'manifest_sha256': digest(destination / 'manifest.json')['sha256']}
        _write_new(journal, json.dumps(receipt, sort_keys=True) + '\n')
    raw = read_small(destination / 'manifest.json', 8 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != receipt['manifest_sha256'] or (destination / 'INCOMPLETE').exists():
        raise MaintenanceError('migration_backup_manifest_changed')
    manifest = json.loads(raw)
    if inventory(destination / 'runtime') != manifest.get('files'):
        raise MaintenanceError('migration_backup_changed')
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise MaintenanceError('invalid_manifest_path')
        if digest(destination / 'runtime' / relative) != expected:
            raise MaintenanceError('migration_backup_changed')
    with runtime_lock(runtime), reserved_ports() as ports, battle_storage_lock(runtime):
        # First attempt proves the exact cold backup before launching the owned
        # process. Resumes may contain a partially migrated database by design.
        current_files = inventory(runtime)
        if started_journal.exists():
            if json.loads(read_small(started_journal)) != receipt:
                raise MaintenanceError('migration_started_receipt_mismatch')
        else:
            if current_files != manifest['files']:
                raise MaintenanceError('migration_runtime_changed_after_backup')
            _write_new(started_journal, json.dumps(receipt, sort_keys=True) + '\n')
        credentials = _credentials(runtime)
        ports[27018].close()
        process = subprocess.Popen([str(mongod), '--config', str(runtime / 'mongo.json')],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with _client(_uri('wesnoth_operator', credentials['database_admin_password'], 'admin')) as client:
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    if process.poll() is not None: raise MaintenanceError('migration_database_exited')
                    try:
                        opts = client.admin.command('getCmdLineOpts')['parsed']
                        if client.admin.command('serverStatus')['pid'] != process.pid or Path(opts['storage']['dbPath']).resolve() != runtime / 'data':
                            raise MaintenanceError('migration_database_identity_mismatch')
                        if client.admin.command('hello').get('isWritablePrimary'): break
                    except PyMongoError: time.sleep(.25)
                else: raise MaintenanceError('migration_database_start_timeout')
                result = migrate_database(client.wesnoth_game, receipt['manifest_sha256'])
        finally:
            if process.poll() is None:
                with _client(_uri('wesnoth_operator', credentials['database_admin_password'], 'admin')) as client:
                    opts = client.admin.command('getCmdLineOpts')['parsed']
                    if client.admin.command('serverStatus')['pid'] != process.pid or Path(opts['storage']['dbPath']).resolve() != runtime / 'data':
                        raise MaintenanceError('migration_database_identity_mismatch')
                    try: client.admin.command('shutdown', timeoutSecs=10)
                    except PyMongoError: pass
                try: process.wait(timeout=30)
                except subprocess.TimeoutExpired: raise MaintenanceError('migration_shutdown_pending')
        if process.returncode != 0: raise MaintenanceError('migration_shutdown_failed')
    return {k: result[k] for k in ('schema_version', 'status')}


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--backup',type=Path,required=True);p.add_argument('--mongod',type=Path,required=True);p.add_argument('--target-schema',type=int,choices=(3,4),default=4);a=p.parse_args()
    try:
        result=migrate(a.runtime,a.backup,a.mongod,target_schema=a.target_schema)
        print(json.dumps(result,sort_keys=True));print(f'ALLIANCE SCHEMA {a.target_schema} MIGRATION COMPLETE')
        return 0
    except Exception as error:
        code=str(error) if isinstance(error,MaintenanceError) else 'migration_failed_preserve_backup_and_journal'
        print('ERROR: '+code);return 1
if __name__=='__main__':raise SystemExit(main())
