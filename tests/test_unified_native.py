"""Actual TLS account bridge and native lobby against production Flask/MongoDB.

The enclosing runner owns a disposable loopback MongoDB replica set. Run in a
network-disabled container; this test does not render the Android game.
"""
import contextlib
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from uuid import uuid4
from pymongo import MongoClient
from werkzeug.serving import make_server,WSGIRequestHandler
from alliance.auth import bootstrap_auth_schema,AuthService,hash_password
from alliance.domain import AllianceService
from alliance.heroes import load_catalog,scaled_stat
from alliance.schema import bootstrap_schema
from alliance.web import create_app
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('identity',ROOT/'tools/alliance_transport.py');IDENTITY=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(IDENTITY)

def exact(sock,n):
    out=b''
    while len(out)<n:
        data=sock.recv(n-len(out))
        if not data:raise EOFError('Peer closed')
        out+=data
    return out

def wml(tag,attrs=None,children=''):
    return '['+tag+']\n'+''.join(k+'='+json.dumps(str(v))+'\n' for k,v in sorted((attrs or {}).items()))+children+'[/'+tag+']\n'

class Peer:
    def __init__(self,port,profile):
        self.port,self.profile=port,profile
        raw=socket.create_connection(('127.0.0.1',port),timeout=4);raw.sendall(struct.pack('!I',1))
        if exact(raw,4)!=b'\0'*4:raise AssertionError('TLS refused')
        self.sock=ssl.create_default_context(cadata=profile['certificate_pem']).wrap_socket(raw,server_hostname='127.0.0.1')
    def close(self):self.sock.close()
    def send(self,text):
        data=gzip.compress(text.encode());self.sock.sendall(struct.pack('!I',len(data))+data)
    def receive(self):
        size=struct.unpack('!I',exact(self.sock,4))[0]
        if size>4194304:raise AssertionError('Unbounded frame')
        return gzip.decompress(exact(self.sock,size)).decode()
    def until(self,tag):
        for _ in range(40):
            value=self.receive()
            if '['+tag+']' in value:return value
            if '[error]' in value or 'was refused' in value:raise AssertionError(value)
        raise AssertionError('Missing '+tag)
    def rpc(self,op,body,token=None,version=3):
        self.close();self.__init__(self.port,self.profile)
        value={'v':version,'id':uuid4().hex,'op':op,'body':body}
        if token:value['token']=token
        self.send(json.dumps(value));return json.loads(self.receive())

class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):pass

@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'),'Requires disposable MongoDB')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=MongoClient(os.environ['ALLIANCE_TEST_MONGO_URI'],tz_aware=True)
        cls.name='alliance_test_'+uuid4().hex;cls.db=cls.client[cls.name];bootstrap_schema(cls.db);bootstrap_auth_schema(cls.db)
        cls.domain=AllianceService(cls.db);cls.catalog,cls.digest=load_catalog();cls.campaign=next(c for c in cls.catalog['campaigns'] if c['aliases']);cls.alias=cls.campaign['aliases'][0];cls.hero=cls.alias['hero_id'];cls.form=next(f for f in cls.catalog['forms'] if f['id']==cls.alias['forms'][0]['form_id'])
        cls.tmp=tempfile.TemporaryDirectory(prefix='unified-native-');cls.root=Path(cls.tmp.name);cls.runtime=cls.root/'runtime';cls.runtime.mkdir()
        cls.secret=secrets.token_urlsafe(32)
        settings=SimpleNamespace(host='127.0.0.1',port=18765,bridge_secret=cls.secret,secret_key=secrets.token_urlsafe(32))
        cls.app=create_app(settings,cls.db);cls.http=make_server('127.0.0.1',18765,cls.app,threaded=True,request_handler=QuietHandler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        (cls.runtime/'config.json').write_text(json.dumps({'format':1,'purpose':'wesnoth-alliance-local','service':vars(settings)}))
        cls.identity=cls.root/'identity'
        with contextlib.redirect_stdout(io.StringIO()):cls.profile,_=IDENTITY.prepare_identity(cls.identity,'127.0.0.1',15001,Path('/usr/bin/openssl'))
        cls.logs=[];cls.processes=[]
        def start(binary,args,marker):
            log=open(cls.root/(binary.name+'.log'),'w+');cls.logs.append(log)
            process=subprocess.Popen([str(binary),*args],cwd=cls.root,stdout=log,stderr=subprocess.STDOUT);cls.processes.append(process)
            for _ in range(200):
                log.flush();log.seek(0);text=log.read()
                if marker in text:return
                if process.poll() is not None:raise AssertionError(text)
                time.sleep(.03)
            raise AssertionError('Startup timed out: '+text)
        start(Path(os.environ.get('ALLIANCE_TEST_BRIDGE_BINARY', ROOT/'build/unified-bridge-vps/alliance-account-bridge')),['--runtime',str(cls.runtime),'--identity',str(cls.identity)],'ALLIANCE ACCOUNT BRIDGE READY')
        config=cls.root/'server.cfg'
        config.write_text('\n'.join(k+'='+json.dumps(str(v)) for k,v in {
            'alliance_auth':'yes','tls_enabled':'yes','alliance_runtime':cls.runtime,'alliance_catalog':ROOT/'alliance/hero_catalog.json',
            'tls_fullchain':cls.identity/'server-cert.pem','tls_private_key':cls.identity/'server-key.pem',
            'versions_accepted':'1.19.26','connections_allowed':30,'save_replays':'no'}.items()))
        start(Path(os.environ.get('ALLIANCE_TEST_SERVER_BINARY', ROOT/'build/unified-server-vps/bin/wesnothd')),['--config',str(config),'--port','15000','--log-info=server'],'opened fifo')
        cls.counter=0
    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.processes):
            p.terminate()
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in cls.logs:
            log.flush();log.seek(0);(Path(os.environ.get('ALLIANCE_TEST_LOG_ROOT',ROOT/'build'))/('unified-native-'+Path(log.name).name)).write_text(log.read());log.close()
        cls.http.shutdown();cls.thread.join(3);cls.http.server_close();cls.client.drop_database(cls.name);cls.client.close();cls.tmp.cleanup()
    def setUp(self):self.peers=[]
    def tearDown(self):
        for p in self.peers:p.close()
        time.sleep(.03)
    def peer(self,port=15001):
        p=Peer(port,self.profile);self.peers.append(p);return p
    def account(self,owned=True):
        type(self).counter+=1;name='Native_'+str(self.counter);password='native test password '+str(self.counter)
        p=self.peer();r=p.rpc('register',{'username':name,'password':password});self.assertTrue(r['ok'],r)
        account=r['data']['account'];self.assertEqual(account['heroes'],[])
        login=p.rpc('login',{'username':name,'password':password});self.assertTrue(login['ok'],login)
        token=login['data']['token']
        if owned:
            begun=p.rpc('story_begin',{'campaign_id':self.campaign['id'],'catalog_version':self.catalog['version'],'catalog_sha256':self.digest},token)
            self.assertTrue(begun['ok'],begun);run=begun['data']
            report=p.rpc('story_checkpoint',{'run_id':run['run_id'],'checkpoint_id':str(uuid4()),'sequence':0,
                'scenario_id':self.campaign['first_scenario'],'next_scenario_id':'','outcome':'win','nonce':run['nonce'],
                'replay_sha256':'a'*64,'heroes':[{'hero_id':self.hero,'unit_id':self.alias['unit_id'],'form_id':self.form['id'],
                'unlocked_forms':[self.form['id']],'earned_experience':0}]},token)
            self.assertTrue(report['ok'],report)
        return p,token,login['data']['account']
    def lobby(self,token,api,account):
        ticket=api.rpc('casual_ticket',{},token);self.assertTrue(ticket['ok'],ticket)
        p=self.peer(15000);greeting=p.until('version');self.assertIn('alliance_protocol="3"',greeting);self.assertIn('implementation_release="1192621"',greeting)
        p.send(wml('version',{'version':'1.19.26'}));p.until('mustlogin')
        p.send(wml('login',{'username':account['username'],'alliance_ticket':ticket['data']['ticket']}));p.until('join_lobby');p.until('gamelist')
        return p,ticket['data']['ticket']
    def test_account_empty_heroes_catalogue_training_and_unknown_schema(self):
        api,token,account=self.account(False)
        me=api.rpc('me',{},token);self.assertTrue(me['ok']);self.assertEqual(me['data']['account']['heroes'],[])
        catalog=api.rpc('hero_catalog',{},token);self.assertTrue(catalog['ok'],catalog);self.assertEqual(catalog['data']['catalog_sha256'],self.digest)
        training=api.rpc('progression_catalog',{},token);self.assertTrue(training['ok'],training);self.assertEqual(training['data']['profile']['heroes'],[])
        with self.assertRaises(EOFError):api.rpc('me',{},token,version=1)
    def test_flexible_plan_bridge_roundtrip_and_revision_fence(self):
        from alliance.flexible import DEFAULT_SETTINGS
        a=self.account();z=self.account()
        team_a=self.domain.create_team(a[2]['id'],'Plan '+str(self.counter)+' A')['_id']
        team_z=self.domain.create_team(z[2]['id'],'Plan '+str(self.counter)+' Z')['_id']
        slots=[dict(side=n,kind='open',account_id='',ai_faction='',ai_leader='') for n in range(1,5)]
        slots[3].update(kind='ai',ai_faction='Northerners',ai_leader='Orcish Warrior')
        published=a[0].rpc('publish_plan',{'team_id':team_a,'opponent_team_id':team_z,'map_id':'isars-cross','settings':DEFAULT_SETTINGS,'slots':slots},a[1])
        self.assertTrue(published['ok'],published);battle=published['data']['battle'];self.assertEqual(battle['format'],2)
        slots[2].update(kind='ai',ai_faction='Dunefolk',ai_leader='Dune Apothecary')
        response=z[0].rpc('edit_plan',{'battle_id':battle['id'],'revision':battle['revision'],'map_id':'isars-cross','settings':DEFAULT_SETTINGS,'slots':slots},z[1])
        self.assertTrue(response['ok'],response);battle=response['data']['battle']
        old=battle['revision']
        for side,seat in [(1,a),(2,z)]:
            for op,fields in [('join_plan',{'side':side}),('select_plan_hero',{'hero_id':self.hero,'form_id':self.form['id']})]:
                response=seat[0].rpc(op,{'battle_id':battle['id'],'revision':battle['revision'],**fields},seat[1])
                self.assertTrue(response['ok'],response);battle=response['data']['battle']
        stale=a[0].rpc('approve_plan',{'battle_id':battle['id'],'revision':old},a[1]);self.assertFalse(stale['ok']);self.assertEqual(stale['data']['code'],'stale_proposal')
        for op in ['approve_plan','ready_plan']:
            for seat in [a,z]:
                response=seat[0].rpc(op,{'battle_id':battle['id'],'revision':battle['revision'],**({'ready':True} if op=='ready_plan' else {})},seat[1])
                self.assertTrue(response['ok'],response);battle=response['data']['battle']
        self.assertEqual(battle['room_state'],'preparing');self.assertFalse(battle['ranked'])
        detail=a[0].rpc('battle_detail',{'battle_id':battle['id']},a[1]);self.assertTrue(detail['ok'],detail);self.assertEqual(detail['data']['battle'],battle)
        review=a[0].rpc('shared_review',{'run_id':battle['id']},a[1]);self.assertTrue(review['ok'],review);self.assertEqual(review['data']['required_reports'],2)

    def test_tls_only_and_ticket_required(self):
        raw=socket.create_connection(('127.0.0.1',15000),timeout=3);raw.sendall(b'\0'*4)
        self.assertEqual(raw.recv(4),b'');raw.close()
        p=self.peer(15000);p.until('version');p.send(wml('version',{'version':'1.19.26'}));p.until('mustlogin')
        p.send(wml('login',{'username':'PretendGuest'}));self.assertIn('[error]',p.receive())
    def test_same_account_ticket_once_and_native_lobby(self):
        api,token,account=self.account();p,ticket=self.lobby(token,api,account)
        p.close();time.sleep(.1)
        other=self.peer(15000);other.until('version');other.send(wml('version',{'version':'1.19.26'}));other.until('mustlogin')
        other.send(wml('login',{'username':account['username'],'alliance_ticket':ticket}));self.assertIn('[error]',other.receive())
    def leader(self,selection):
        f=self.form;level=selection['hero_level'];effects=wml('effect',{'apply_to':'hitpoints','set_total':scaled_stat(f['base_hitpoints'],level,2),'heal_full':'yes'})
        attacks=sorted({(a['name'],a['type'],a['range'],a['number'],a['damage']) for a in f['attacks']},key=lambda a:-a[4])
        for name,kind,range_,n,damage in attacks:effects+=wml('effect',{'apply_to':'attack','name':name,'type':kind,'range':range_,'number':n,'damage':damage,'set_damage':scaled_stat(damage,level,1)})
        variables=wml('variables',{'alliance_hero_id':self.hero,'alliance_form_id':f['id'],'alliance_hero_level':level})
        mods=wml('modifications',children=wml('object',{'id':'unified_hero_scaling','duration':'forever','silent':'yes'},effects))
        return wml('leader',{'type':f['unit_type'],'canrecruit':'yes','random_traits':'no'},variables+mods)

    def test_backend_capability_refuses_unmigrated_database(self):
        client=self.app.test_client();headers={'Authorization':'Bearer '+self.secret}
        self.assertEqual(client.get('/internal/v1/health',headers=headers).status_code,200)
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':2}})
        try:
            self.assertNotEqual(client.get('/internal/v1/health',headers=headers).status_code,200)
            self.assertNotEqual(client.post('/internal/v1/casual/capabilities',json={},headers=headers).status_code,200)
        finally:self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':3}})

    def test_authenticated_listener_refuses_standard_create(self):
        api,token,account=self.account();peer,_=self.lobby(token,api,account)
        peer.send(wml('create_game',{'name':'Retired Standard'}))
        peer.until('leave_game');peer.until('gamelist')
        self.assertEqual(self.db.network_battle_reservations.count_documents({'_id':account['id']}),0)
