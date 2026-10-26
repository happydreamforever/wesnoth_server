"""Start a new owned MongoDB and real shared-engine fixture for offline tests.

Use a network-disabled container with the verification MongoDB/Python tools:
  python tests/start_shared_engine_fixture.py --size 3 --root /out/new-fixture
Write an empty <root>/fixture/stop file to stop and retain test evidence.
The helper drops only its random alliance_test_shared_engine_* database and
stops only the mongod child it created. No game runtime is selected.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from pymongo import MongoClient

parser = argparse.ArgumentParser()
parser.add_argument('--flexible', action='store_true')
parser.add_argument('--observers', action='store_true')
parser.add_argument('--turns', type=int, default=-1)
parser.add_argument('--size', type=int, choices=(2, 3, 4), required=True)
parser.add_argument('--root', type=Path)
args = parser.parse_args()
root = args.root or Path('/out/multiseat-' + str(args.size) + '-live')
if not root.is_absolute() or root.exists():
    raise RuntimeError('A new absolute fixture root is required')
os.umask(0o077)
root.mkdir(); (root / 'db').mkdir()
mongo = subprocess.Popen(['/usr/local/bin/mongod', '--dbpath', str(root / 'db'), '--port', '27019', '--bind_ip', '127.0.0.1', '--replSet', 'shared_fixture', '--wiredTigerCacheSizeGB', '0.25', '--oplogSize', '32', '--logpath', str(root / 'mongodb.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
client = MongoClient('mongodb://127.0.0.1:27019/?directConnection=true', serverSelectionTimeoutMS=500)
try:
    for _ in range(100):
        if mongo.poll() is not None: raise RuntimeError('Owned fixture database exited')
        try:
            client.admin.command('ping')
            info = client.admin.command('serverStatus')
            options = client.admin.command('getCmdLineOpts')['parsed']
            if (info.get('pid') != mongo.pid or
                    Path(options['storage']['dbPath']).resolve() != (root / 'db').resolve() or
                    options['net']['port'] != 27019):
                raise RuntimeError('Port27019 is not the owned fixture database')
            break
        except RuntimeError: raise
        except Exception: time.sleep(.1)
    else: raise RuntimeError('Fixture database start timed out')
    client.admin.command('replSetInitiate', {'_id': 'shared_fixture', 'members': [{'_id': 0, 'host': '127.0.0.1:27019'}]})
    for _ in range(100):
        if client.admin.command('hello').get('isWritablePrimary'): break
        time.sleep(.1)
    else: raise RuntimeError('Fixture primary timed out')
    env = os.environ.copy()
    env['ALLIANCE_TEST_MONGO_URI'] = 'mongodb://127.0.0.1:27019/?replicaSet=shared_fixture'
    subprocess.run([sys.executable, str(Path(__file__).with_name('shared_engine_fixture.py')), '--size', str(args.size), '--root', str(root / 'fixture'), '--turns', str(args.turns), *(['--flexible'] if args.flexible else []), *(['--observers'] if args.observers else [])], env=env, check=True)
finally:
    client.close()
    if mongo.poll() is None:
        mongo.terminate(); mongo.wait(timeout=30)
    (root / 'mongo-exit.json').write_text(json.dumps({'code': mongo.returncode}))
