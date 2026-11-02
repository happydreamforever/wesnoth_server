"""Reinstallation smoke checks using a disposable local database only."""
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

assert sys.version_info[:3] == (3, 12, 10), sys.version
assert sys.maxsize > 2**32, '64-bit Python is required'
server = Path('/workspace/wesnoth_server')
sys.path[:0] = [str(server), str(server / 'tests')]
from pymongo import MongoClient

output = Path('/out')
pins = json.loads(Path('/migration/pins/linux-python312-wheels.json').read_text())
for pin in pins:
    actual = metadata.version(pin['name'])
    if actual != pin['version']:
        raise RuntimeError('Dependency version differs: ' + pin['name'])
result_record = {'purpose': 'New VPS environment smoke verification', 'python': sys.version,
                 'network': 'Docker network none; disposable loopback database',
                 'packages': {pin['name']: pin['version'] for pin in pins},
                 'scope': 'Focused startup, TLS relay and Court domain regression; not Android or native combat acceptance'}
# These suites intentionally replace the process-wide clock. Run them before
# creating any Mongo client, whose background monitors also use that clock.
unit_names = ['test_battle_startup', 'test_alliance_workflow_startup', 'test_alliance_workflow']
with (output / 'unit-tests.txt').open('w') as test_log:
    unit_result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(unit_names))
if not unit_result.wasSuccessful() or unit_result.skipped:
    result_record.update(suites=unit_names, tests=unit_result.testsRun,
                         failures=len(unit_result.failures), errors=len(unit_result.errors),
                         skips=len(unit_result.skipped), success=False)
    (output / 'result.json').write_text(json.dumps(result_record, indent=2) + '\n')
    raise SystemExit(1)
print('Startup and workflow unit checks passed; starting the disposable MongoDB tests.', flush=True)
with tempfile.TemporaryDirectory(prefix='migration-mongo-', dir='/tmp') as database_dir:
    with (output / 'mongodb-fixture.log').open('wb') as log:
        process = subprocess.Popen(['mongod', '--bind_ip', '127.0.0.1', '--port', '27019',
                                    '--replSet', 'migration_verification', '--dbpath', database_dir,
                                    '--wiredTigerCacheSizeGB', '0.25'], stdout=log, stderr=subprocess.STDOUT)
        client = MongoClient('mongodb://127.0.0.1:27019/?directConnection=true', serverSelectionTimeoutMS=200)
        try:
            for _ in range(100):
                try:
                    client.admin.command('ping')
                    break
                except Exception:
                    if process.poll() is not None:
                        raise RuntimeError('Disposable MongoDB exited; inspect mongodb-fixture.log') from None
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable MongoDB did not start')
            version = client.server_info()['version']
            if version != '8.0.32':
                raise RuntimeError('MongoDB version differs')
            result_record['mongodb'] = version
            client.admin.command('replSetInitiate', {'_id': 'migration_verification',
                'members': [{'_id': 0, 'host': '127.0.0.1:27019'}]})
            for _ in range(100):
                if client.admin.command('hello').get('isWritablePrimary'):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Disposable primary did not become ready')
            os.environ['ALLIANCE_TEST_MONGO_URI'] = 'mongodb://127.0.0.1:27019/?replicaSet=migration_verification'
            names = ['test_alliance_battle_daemon', 'test_court_battles', 'test_court_teams']
            suite = unittest.defaultTestLoader.loadTestsFromNames(names)
            with (output / 'tests.txt').open('w') as test_log:
                result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(suite)
            result_record.update(suites=unit_names + names, tests=unit_result.testsRun + result.testsRun, failures=len(result.failures),
                                 errors=len(result.errors), skips=len(result.skipped),
                                 success=result.wasSuccessful() and not result.skipped)
        finally:
            client.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
(output / 'result.json').write_text(json.dumps(result_record, indent=2) + '\n')
print(json.dumps(result_record, indent=2))
raise SystemExit(0 if result_record.get('success') else 1)
