"""Start a private scratch MongoDB replica set, run selected unittest suites, stop it."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from pymongo import MongoClient
with tempfile.TemporaryDirectory(prefix='wesnoth-v2-test-') as scratch:
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=open(Path(scratch)/'mongo.log','wb')
    process=subprocess.Popen(['mongod','--bind_ip','127.0.0.1','--port',str(port),'--replSet','wesnoth_test','--dbpath',scratch,'--quiet'],stdout=log,stderr=subprocess.STDOUT)
    try:
        client=MongoClient(f'mongodb://127.0.0.1:{port}/?directConnection=true',serverSelectionTimeoutMS=200)
        for _ in range(100):
            try:client.admin.command('ping');break
            except Exception:time.sleep(.1)
        client.admin.command('replSetInitiate',{'_id':'wesnoth_test','members':[{'_id':0,'host':f'127.0.0.1:{port}'}]})
        for _ in range(100):
            if client.admin.command('hello').get('isWritablePrimary'):break
            time.sleep(.1)
        env=dict(os.environ,ALLIANCE_TEST_MONGO_URI=f'mongodb://127.0.0.1:{port}/?replicaSet=wesnoth_test')
        code=0
        for pattern in sys.argv[1:] or ['test_unified_product.py']:
            result=subprocess.call([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'],env=env)
            code=max(code,result)
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
    sys.exit(code)
