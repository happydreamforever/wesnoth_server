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
    def rpc(self,op,body,token=None,version=2):
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
        start(ROOT/'build/unified-bridge-vps/alliance-account-bridge',['--runtime',str(cls.runtime),'--identity',str(cls.identity)],'ALLIANCE ACCOUNT BRIDGE READY')
        config=cls.root/'server.cfg'
        config.write_text('\n'.join(k+'='+json.dumps(str(v)) for k,v in {
            'alliance_auth':'yes','tls_enabled':'yes','alliance_runtime':cls.runtime,'alliance_catalog':ROOT/'alliance/hero_catalog.json',
            'tls_fullchain':cls.identity/'server-cert.pem','tls_private_key':cls.identity/'server-key.pem',
            'versions_accepted':'1.19.26','connections_allowed':30,'save_replays':'no'}.items()))
        start(ROOT/'build/unified-server-vps/bin/wesnothd',['--config',str(config),'--port','15000','--log-info=server'],'opened fifo')
        cls.counter=0
    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.processes):
            p.terminate()
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in cls.logs:
            log.flush();log.seek(0);(ROOT/'build'/('unified-native-'+Path(log.name).name)).write_text(log.read());log.close()
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
        p=self.peer(15000);greeting=p.until('version');self.assertIn('alliance_protocol="2"',greeting);self.assertIn('implementation_release="1192617"',greeting)
        p.send(wml('version',{'version':'1.19.26'}));p.until('mustlogin')
        p.send(wml('login',{'username':account['username'],'alliance_ticket':ticket['data']['ticket']}));p.until('join_lobby');p.until('gamelist')
        return p,ticket['data']['ticket']
    def test_account_empty_heroes_catalogue_training_and_unknown_schema(self):
        api,token,account=self.account(False)
        me=api.rpc('me',{},token);self.assertTrue(me['ok']);self.assertEqual(me['data']['account']['heroes'],[])
        catalog=api.rpc('hero_catalog',{},token);self.assertTrue(catalog['ok'],catalog);self.assertEqual(catalog['data']['catalog_sha256'],self.digest)
        training=api.rpc('progression_catalog',{},token);self.assertTrue(training['ok'],training);self.assertEqual(training['data']['profile']['heroes'],[])
        with self.assertRaises(EOFError):api.rpc('me',{},token,version=1)
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
    def level(self,account,selection=None):
        attrs={'side':1,'controller':'human','current_player':account['username'],'player_id':account['username'],'save_id':account['username'],'team_name':'one','allow_player':'yes'}
        leader=wml('leader',{'type':'Spearman'})
        if selection:
            attrs.update(alliance_account_id=account['id'],alliance_hero_id=selection['hero_id'],alliance_form_id=selection['form_id'],alliance_hero_level=selection['hero_level'],alliance_hero_revision=selection['hero_revision'])
            leader=self.leader(selection)
        side=wml('side',attrs,leader);side+=wml('side',{'side':2,'controller':'ai','team_name':'two','allow_player':'no'},wml('leader',{'type':'Orcish Grunt'}))
        return wml('multiplayer',{'mp_scenario':'test','mp_scenario_name':'Unified test','shuffle_sides':'no'})+wml('scenario',{'id':'test','map_data':'Gg,Gg,Gg\nGg,Gg,Gg\nGg,Gg,Gg'},side)
    def test_selected_owned_hero_ready_gate_frozen_game_no_xp(self):
        api,token,account=self.account();p,_=self.lobby(token,api,account)
        p.send(wml('create_game',{'name':'Unified test'}));context=p.until('alliance_game');game=re.search(r'id="([0-9a-f-]+)"',context)[1]
        selected=api.rpc('casual_select',{'game_id':game,'side':1,'hero_id':self.hero,'form_id':self.form['id']},token)
        self.assertTrue(selected['ok'],selected);selection=selected['data']['selection']
        p.send(self.level(account,selection));p.until('alliance_game')
        p.send(wml('start_game'));self.assertIn('accepted="no"',p.until('alliance_start'))
        p.send(wml('alliance_hero',{'ticket':selected['data']['selection_ticket']}));self.assertIn('ready="no"',p.until('alliance_selection'))
        p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));self.assertIn('ready="yes"',p.until('alliance_selection'))
        p.send(wml('start_game'));self.assertIn('accepted="yes"',p.until('alliance_start'))
        frozen=self.domain.casual_restore(game);self.assertEqual(frozen['players'][0]['selection'],selection)
        self.assertEqual(self.db.account_heroes.find_one({'account_id':account['id']})['total_experience'],20)
    def prepared(self, mutation=None):
        api,token,account=self.account();p,_=self.lobby(token,api,account)
        p.send(wml('create_game',{'name':'Guard test'}));game=re.search(r'id="([0-9a-f-]+)"',p.until('alliance_game'))[1]
        reply=api.rpc('casual_select',{'game_id':game,'side':1,'hero_id':self.hero,'form_id':self.form['id']},token)
        self.assertTrue(reply['ok'],reply);selected=reply['data'];level=self.level(account,selected['selection'])
        p.send(mutation(level) if mutation else level);p.until('alliance_game')
        p.send(wml('alliance_hero',{'ticket':selected['selection_ticket']}));p.until('alliance_selection')
        return api,token,account,p,game,selected,level

    def test_host_cannot_add_stats_or_extra_effect_modifiers(self):
        variants=[lambda s:s.replace('random_traits="no"','max_hitpoints="9999"\nrandom_traits="no"'),
                  lambda s:re.sub(r'(?m)^(damage="[0-9]+"\n)',r'\1increase_damage="99"\n',s),
                  lambda s:s.replace('set_total="'+str(scaled_stat(self.form['base_hitpoints'],2,2))+'"','set_total="99999"')]
        for mutate in variants:
            with self.subTest(kind=variants.index(mutate)):
                api,token,account,p,game,selected,level=self.prepared(mutate)
                p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));p.until('alliance_selection')
                p.send(wml('start_game'));self.assertIn('accepted="no"',p.until('alliance_start'))
                self.assertIsNone(self.db.casual_games.find_one({'_id':game}))
                p.close()

    def test_authored_leader_identity_preserved_without_relaxing_stats(self):
        identity = 'gender="female"\nid="story-protagonist"\nname="Authored protagonist"\n'
        api, token, account, peer, game, selected, level = self.prepared(
            lambda level: level.replace('random_traits="no"', identity + 'random_traits="no"', 1))
        peer.send(wml('alliance_ready', {'side': 1, 'ready': 'yes'})); peer.until('alliance_selection')
        peer.send(wml('start_game')); self.assertIn('accepted="yes"', peer.until('alliance_start'))
        peer.close()
        for identity in ('id="' + 'x' * 257 + '"\n', 'gender="random"\n', 'profile="unapproved"\n'):
            api, token, account, peer, game, selected, level = self.prepared(
                lambda level: level.replace('random_traits="no"', identity + 'random_traits="no"', 1))
            peer.send(wml('alliance_ready', {'side': 1, 'ready': 'yes'})); peer.until('alliance_selection')
            peer.send(wml('start_game')); self.assertIn('accepted="no"', peer.until('alliance_start'))
            self.assertIsNone(self.db.casual_games.find_one({'_id': game}))
            peer.close()

    def test_wrong_seat_and_reused_hero_ticket_rejected(self):
        api,token,account,p,game,selected,level=self.prepared()
        p.send(wml('alliance_ready',{'side':2,'ready':'yes'}));self.assertIn('was refused',p.until('message'))
        p.send(wml('alliance_hero',{'ticket':selected['selection_ticket']}));self.assertIn('was refused',p.until('message'))
        p.send(wml('start_game'));self.assertIn('accepted="no"',p.until('alliance_start'))

    def test_saved_resume_keeps_frozen_hero_after_growth_and_requires_ready(self):
        api,token,account,p,game,selected,level=self.prepared()
        p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));p.until('alliance_selection')
        p.send(wml('start_game'));self.assertIn('accepted="yes"',p.until('alliance_start'))
        p.send(wml('leave_game'));p.until('gamelist')
        admin=self.domain.bootstrap_admin('ResumeAdmin',hash_password('resume admin password'))['_id']
        self.domain.admin_correct_hero_experience(admin,account['id'],self.hero,100,'Resume fixture growth',1)
        p.send(wml('create_game',{'name':'Resume test'}));p.until('alliance_game')
        p.send('alliance_casual_game_id="'+game+'"\n'+level)
        restored=p.until('alliance_game');self.assertIn('resume="yes"',restored);self.assertIn('ready="no"',restored)
        self.assertIn('hero_level="2"',restored)
        p.send(wml('start_game'));self.assertIn('accepted="no"',p.until('alliance_start'))
        p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));p.until('alliance_selection')
        p.send(wml('start_game'));self.assertIn('accepted="yes"',p.until('alliance_start'))
        self.assertEqual(self.domain.casual_restore(game)['players'][0]['selection'],selected['selection'])
        self.assertEqual(self.domain.get_account(account['id'])['heroes'][0]['total_experience'],120)

    def test_next_scenario_preserves_snapshot_and_requires_fresh_ready(self):
        api,token,account,p,game,selected,level=self.prepared()
        p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));p.until('alliance_selection')
        p.send(wml('start_game'));self.assertIn('accepted="yes"',p.until('alliance_start'))
        p.send(wml('store_next_scenario',{'alliance_casual_game_id':game},level))
        context=p.until('alliance_game');self.assertIn('resume="yes"',context);self.assertIn('ready="no"',context)
        p.send(wml('start_game'));self.assertIn('accepted="no"',p.until('alliance_start'))
        p.send(wml('alliance_ready',{'side':1,'ready':'yes'}));p.until('alliance_selection')
        p.send(wml('start_game'));self.assertIn('accepted="yes"',p.until('alliance_start'))
        self.assertEqual(self.db.account_heroes.find_one({'account_id':account['id']})['total_experience'],20)
    def test_two_authenticated_human_sides_and_fixed_owner_guard(self):
        api1,token1,a1=self.account();api2,token2,a2=self.account()
        p1,_=self.lobby(token1,api1,a1);p2,_=self.lobby(token2,api2,a2)
        p1.send(wml('create_game',{'name':'Two humans'}));game=re.search(r'id="([0-9a-f-]+)"',p1.until('alliance_game'))[1]
        selections=[]
        for api,token,side in [(api1,token1,1),(api2,token2,2)]:
            value=api.rpc('casual_select',{'game_id':game,'side':side,'hero_id':self.hero,'form_id':self.form['id']},token)
            self.assertTrue(value['ok'],value);selections.append(value['data'])
        second=wml('side',{'side':2,'controller':'human','current_player':a2['username'],'player_id':a2['username'],
            'save_id':a2['username'],'team_name':'two','allow_player':'yes','alliance_account_id':a2['id'],
            'alliance_hero_id':self.hero,'alliance_form_id':self.form['id'],'alliance_hero_level':2,
            'alliance_hero_revision':selections[1]['selection']['hero_revision']},self.leader(selections[1]['selection']))
        level=self.level(a1,selections[0]['selection'])
        old=wml('side',{'side':2,'controller':'ai','team_name':'two','allow_player':'no'},wml('leader',{'type':'Orcish Grunt'}))
        self.assertIn(old,level);p1.send(level.replace(old,second));p1.until('alliance_game')
        numeric=None
        for _ in range(30):
            value=p2.receive()
            for node in re.findall(r'\[game\]\n(.*?)\[/game\]',value,re.S):
                if 'name="Two humans"' in node:numeric=re.search(r'^id="([0-9]+)"',node,re.M)[1]
            if numeric:break
        self.assertIsNotNone(numeric)
        p2.send(wml('join',{'id':numeric,'observe':'no'}));p2.until('scenario')
        p1.send(wml('alliance_hero',{'ticket':selections[0]['selection_ticket'],'side':1}));p1.until('alliance_selection')
        p2.send(wml('alliance_hero',{'ticket':selections[1]['selection_ticket'],'side':2}));p2.until('alliance_selection')
        p2.send(wml('alliance_ready',{'side':1,'ready':'yes'}));self.assertIn('was refused',p2.until('message'))
        for peer,side in [(p1,1),(p2,2)]:
            peer.send(wml('alliance_ready',{'side':side,'ready':'yes'}))
            for _ in range(30):
                value=peer.receive()
                if any(f'side="{side}"' in n and 'ready="yes"' in n for n in re.findall(r'\[alliance_selection\]\n(.*?)\[/alliance_selection\]',value,re.S)):break
            else:self.fail('Readiness acknowledgement missing')
        p1.send(wml('start_game'));self.assertIn('accepted="yes"',p1.until('alliance_start'));p2.until('start_game')
        frozen=self.domain.casual_restore(game)
        self.assertEqual({p['account_id'] for p in frozen['players']},{a1['id'],a2['id']})
        self.assertEqual(self.db.settlements.count_documents({'_id':game}),0)
