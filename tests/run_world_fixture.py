"""Bounded disposable MongoDB fixture, retaining a log on unexpected failure."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from pymongo import MongoClient
root=Path(tempfile.mkdtemp(prefix='world-company-fixture-'))
process=subprocess.Popen(['mongod','--dbpath',str(root),'--bind_ip','127.0.0.1','--port','27019','--replSet','world_fixture',
 '--wiredTigerCacheSizeGB','0.25','--logpath',str(root/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
client=MongoClient('mongodb://127.0.0.1:27019/?directConnection=true',serverSelectionTimeoutMS=500)
try:
 for attempt in range(80):
  try:client.admin.command('ping');break
  except Exception:time.sleep(.1)
 else:raise RuntimeError('Disposable database did not start')
 client.admin.command('replSetInitiate',{'_id':'world_fixture','members':[{'_id':0,'host':'127.0.0.1:27019'}]})
 for attempt in range(100):
  if client.admin.command('hello').get('isWritablePrimary'):break
  time.sleep(.1)
 else:raise RuntimeError('Disposable database did not become primary')
 env=dict(os.environ,ALLIANCE_TEST_MONGO_URI='mongodb://127.0.0.1:27019/?replicaSet=world_fixture',PYTHONPATH='.:tests')
 result=subprocess.run([sys.executable,'-B','-m','unittest','-v',*(sys.argv[1:] or ['test_company_product','test_world_product'])],env=env)
 if result.returncode:print((root/'mongo.log').read_text()[-4000:])
 raise SystemExit(result.returncode)
finally:
 client.close()
 if process.poll() is None:process.terminate()
 process.wait(timeout=30)
