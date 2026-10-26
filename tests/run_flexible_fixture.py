"""Disposable in-container loopback database, never production credentials."""
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import time
from pymongo import MongoClient
root=Path(tempfile.mkdtemp(prefix='flexible-1192621-'))
process=subprocess.Popen(['mongod','--dbpath',str(root),'--bind_ip','127.0.0.1','--port','27019','--replSet','flexible_fixture','--logpath',str(root/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 client=MongoClient('mongodb://127.0.0.1:27019/?directConnection=true',serverSelectionTimeoutMS=500)
 for attempt in range(80):
  try:client.admin.command('ping');break
  except Exception:time.sleep(.1)
 else:raise RuntimeError('Disposable database did not start')
 client.admin.command('replSetInitiate',{'_id':'flexible_fixture','members':[{'_id':0,'host':'127.0.0.1:27019'}]})
 for attempt in range(100):
  if client.admin.command('hello').get('isWritablePrimary'):break
  time.sleep(.1)
 else:raise RuntimeError('Disposable replica set did not become primary')
 env=dict(os.environ,ALLIANCE_TEST_MONGO_URI='mongodb://127.0.0.1:27019/?replicaSet=flexible_fixture',PYTHONPATH='.:tests'+(os.pathsep+os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else ''))
 result=subprocess.run([sys.executable,'-B','-m','unittest','-v',*(sys.argv[1:] or ['test_flexible_product'])],env=env)
 raise SystemExit(result.returncode)
finally:
 process.terminate();process.wait(timeout=30)
