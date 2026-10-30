"""Operator HTTP flows against a disposable real MongoDB replica set."""
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlsplit

from pymongo import MongoClient
from werkzeug.datastructures import MultiDict

from alliance.auth import hash_password, bootstrap_auth_schema, AuthService
from alliance.domain import AllianceService
from alliance.schema import bootstrap_schema
from alliance.web import create_app
from alliance.admin_management import admin_record_revision


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable replica set')
class AdminConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri=os.environ['ALLIANCE_TEST_MONGO_URI']
        if urlsplit(uri).hostname!='127.0.0.1':raise RuntimeError('Only disposable loopback MongoDB allowed')
        cls.mongo=MongoClient(uri,tz_aware=True)
        cls.password='Fixture-admin-password-123'
        cls.hash=hash_password(cls.password)

    @classmethod
    def tearDownClass(cls):cls.mongo.close()

    def setUp(self):
        self.db=self.mongo['admin_console_test_'+uuid4().hex]
        bootstrap_schema(self.db);bootstrap_auth_schema(self.db)
        self.domain=AllianceService(self.db)
        self.admin=self.domain.bootstrap_admin('Operator',self.hash)
        self.player=self.domain.register('PlayerOne',self.hash)
        self.other=self.domain.register('PlayerTwo',self.hash)
        self.team=self.domain.create_team(self.player['_id'],'Test Team')
        self.settings=SimpleNamespace(host='127.0.0.1',port=18765,secret_key='test-cookie-'+uuid4().hex,bridge_secret='test-bridge-'+uuid4().hex)
        self.app=create_app(self.settings,self.db);self.app.config['TESTING']=True
        self.client=self.app.test_client()
        self.login()

    def tearDown(self):self.mongo.drop_database(self.db.name)

    def csrf(self,path='/'):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,(path,response.get_data(as_text=True)[:500]))
        return re.search(r'name="csrf_token" value="([^"]+)"',response.get_data(as_text=True)).group(1)

    def login(self):
        response=self.client.post('/login',data={'csrf_token':self.csrf('/login'),'username':'Operator','password':self.password})
        self.assertEqual(response.status_code,302)

    def form(self,revision,**fields):
        return {'csrf_token':self.csrf(),'revision':str(revision),'reason':'Operator reviewed this change','confirmation':'confirmed',**fields}

    def snapshot(self):
        # Auth validation can update its session bookkeeping. Compare game data.
        return {name:list(self.db[name].find({}).sort('_id',1)) for name in self.db.list_collection_names() if name not in ('auth_sessions','auth_attempts')}

    def export_render(self,path,response):
        destination=os.environ.get('ADMIN_RENDER_DIR')
        if not destination:return
        target=Path(destination)
        target.mkdir(parents=True,exist_ok=True)
        name=self._testMethodName+'-'+re.sub('[^A-Za-z0-9_-]','_',path)+'.html'
        (target/name).write_text(response.get_data(as_text=True))
        (target/'static').mkdir(exist_ok=True)
        (target/'static/admin.css').write_bytes((Path(__file__).resolve().parents[1]/'alliance/static/admin.css').read_bytes())

    def test_all_screens_read_only_and_secret_free(self):
        self.db.accounts.update_one({'_id':self.player['_id']},{'$set':{'unexpected_secret':'DO-NOT-RENDER'}})
        paths=['/','/accounts','/accounts/'+self.player['_id'],'/accounts/new','/teams','/teams/'+self.team['_id'],
               '/companies','/companies/'+self.player['_id'],'/rooms','/plans','/campaigns','/engagements','/operations','/areas','/world','/runs','/audit']
        paths += ['/manage/'+category for category in ('castles','defenses','wars','soldiers','heroes','history')]
        before=self.snapshot()
        for path in paths:
            with self.subTest(path=path):
                result=self.client.get(path)
                self.assertEqual(result.status_code,200,result.get_data(as_text=True)[:700])
                text=result.get_data(as_text=True)
                for secret in (self.hash,self.settings.bridge_secret,self.settings.secret_key,'DO-NOT-RENDER','password_hash'):
                    self.assertNotIn(secret,text)
                self.assertEqual(result.headers['Cache-Control'],'no-store')
                self.assertIn("default-src 'none'",result.headers['Content-Security-Policy'])
                self.assertIn('Emerald Court',text)
                self.export_render(path,result)
        self.assertEqual(before,self.snapshot())

    def test_queries_escape_regex_and_paginate(self):
        for i in range(27):self.domain.register('Paging%03d'%i,self.hash)
        first=self.client.get('/accounts?q=Paging').get_data(as_text=True)
        self.assertIn('rel="next"',first)
        self.assertEqual(first.count('Reset password'),25)
        second=self.client.get('/accounts?q=Paging&page=2').get_data(as_text=True)
        self.assertEqual(second.count('Reset password'),2)
        self.assertNotIn('rel="next"',second)
        literal=self.client.get('/accounts?q=.*').get_data(as_text=True)
        self.assertNotIn('PlayerOne',literal)
        for query in ('page=0','page=-1','page=10000','q=a&q=b','state=unknown','x[$ne]=x'):
            self.assertEqual(self.client.get('/accounts?'+query).status_code,400,query)

    def test_new_routes_require_local_admin_and_csrf(self):
        anonymous=self.app.test_client()
        for path in ('/rooms','/companies','/plans','/engagements','/operations','/manage/heroes','/accounts/new'):
            self.assertEqual(anonymous.get(path).status_code,302)
            self.assertEqual(self.client.get(path,environ_overrides={'REMOTE_ADDR':'192.168.1.2'}).status_code,403)
        response=self.client.post('/teams/'+self.team['_id']+'/manage',data={'operation':'rename','value':'Changed'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.db.teams.find_one({'_id':self.team['_id']})['name'],'Test Team')

    def test_team_edit_confirmation_stale_guard_and_audit(self):
        path='/teams/'+self.team['_id']+'/manage'
        form=self.form(self.team['revision'],operation='rename',value='Updated Team')
        missing=dict(form);missing.pop('confirmation')
        self.assertEqual(self.client.post(path,data=missing).status_code,400)
        duplicate=MultiDict(list(form.items())+[('value','Unexpected')])
        self.assertEqual(self.client.post(path,data=duplicate).status_code,400)
        self.assertEqual(self.client.post(path,data=form).status_code,302)
        self.assertEqual(self.db.teams.find_one({'_id':self.team['_id']})['name'],'Updated Team')
        self.assertEqual(self.client.post(path,data=form).status_code,409)
        self.assertEqual(self.db.admin_audit.count_documents({'target_id':self.team['_id']}),1)

    def test_revoke_sessions_keeps_password_and_progress(self):
        auth=AuthService(self.db)
        auth.authenticate('PlayerOne',self.password,'player')
        old=self.db.accounts.find_one({'_id':self.player['_id']})
        response=self.client.post('/accounts/'+self.player['_id']+'/sessions',data=self.form(old['revision']))
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.db.accounts.find_one({'_id':self.player['_id']})['password_hash'],old['password_hash'])
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id':self.player['_id'],'revoked':False}),0)

    def test_create_player_validation_and_no_password_reflection(self):
        token=self.csrf('/accounts/new')
        form={'csrf_token':token,'username':'NewPlayer','password':'New-fixture-password-123','password_confirmation':'wrong','reason':'Create requested player'}
        response=self.client.post('/accounts/new',data=form)
        self.assertEqual(response.status_code,409)
        self.assertNotIn(form['password'],response.get_data(as_text=True))
        self.assertNotIn('value="wrong"',response.get_data(as_text=True))
        form['password_confirmation']=form['password']
        response=self.client.post('/accounts/new',data=form)
        self.assertEqual(response.status_code,302)
        player=self.db.accounts.find_one({'username':'NewPlayer'})
        self.assertEqual(player['role'],'player')
        self.assertEqual(self.db.account_heroes.count_documents({'account_id':player['_id']}),0)
        self.assertIsNone(self.db.companies.find_one({'_id':player['_id']}))

    def test_legacy_run_render_and_cancel_stale_binding(self):
        from alliance.domain import _now
        run={'_id':str(uuid4()),'kind':'campaign','state':'running','ruleset_version':'fixture','participants':[{'account_id':self.player['_id']}],
             'created_at':_now(),'campaign_id':'fixture_story','next_checkpoint':1}
        self.db.game_runs.insert_one(run)
        self.assertEqual(self.client.get('/runs/'+run['_id']).status_code,200)
        form=self.form(admin_record_revision(run))
        self.db.game_runs.update_one({'_id':run['_id']},{'$inc':{'next_checkpoint':1}})
        self.assertEqual(self.client.post('/manage-cancel/run/'+run['_id'],data=form).status_code,409)
        current=self.db.game_runs.find_one({'_id':run['_id']})
        self.assertEqual(self.client.post('/manage-cancel/run/'+run['_id'],data=self.form(admin_record_revision(current))).status_code,302)
        self.assertEqual(self.db.game_runs.find_one({'_id':run['_id']})['state'],'cancelled')

    def test_unknown_collection_and_document_projection(self):
        for path in ('/manage/auth_sessions','/manage/casual_tickets','/manage/schema_metadata','/manage/heroes/missing'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertNotIn('not yet call this service',self.client.get('/').get_data(as_text=True))

    def test_populated_company_world_and_engagement_pages(self):
        from alliance.heroes import load_catalog
        catalog,_=load_catalog()
        hero=next(f for f in catalog['forms'] if f['source_type']=='Spearman' and f['native_level']==1)
        identity=self.player['_id']
        self.db.account_heroes.insert_one({'_id':str(uuid4()),'account_id':identity,'hero_id':hero['hero_id'],
            'forms':[hero['id']],'total_experience':64,'revision':0,'secret_canary':'NEVER-RENDER-HERO-PRIVATE'})
        self.domain.world_command(identity,'company_initialize',{'command_id':str(uuid4())})
        company=self.db.companies.find_one({'_id':identity})
        soldiers=list(self.db.company_soldiers.find({'owner_id':identity}))
        self.domain.world_command(identity,'company_select',{'command_id':str(uuid4()),'expected_revision':company['revision'],
            'hero_id':hero['hero_id'],'form_id':hero['id'],'soldier_ids':[soldiers[0]['_id']],'bracket':'scout'})
        battle=self.domain.world_command(identity,'company_expedition',{'command_id':str(uuid4()),
            'expected_revision':self.db.companies.find_one({'_id':identity})['revision'],'mission_id':'company_border_patrol'})['data']['battle']['id']
        opponent=self.domain.create_team(self.other['_id'],'Other Team')
        self.domain.world_admin_command(self.admin['_id'],'bootstrap',{'command_id':str(uuid4()),'team_ids':[self.team['_id'],opponent['_id']]})
        castle=self.db.world_castles.find_one({})['_id']
        paths=['/companies/'+identity,'/manage/soldiers/'+soldiers[0]['_id'],'/engagements','/manage/contracts/'+battle,
            '/world','/manage/castles','/manage/castles/'+castle,'/operations','/manage/heroes']
        before=self.snapshot()
        for path in paths:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200,response.get_data(as_text=True)[:400])
                self.assertNotIn('NEVER-RENDER-HERO-PRIVATE',response.get_data(as_text=True))
                self.export_render(path,response)
        self.assertEqual(before,self.snapshot())

    def test_room_browser_closure_requires_current_revision_and_confirmation(self):
        from alliance.admin_rooms import AdminRooms
        room={'id':str(uuid4()),'native_id':1,'revision':1,'name':'Room <script>unsafe</script>',
            'map_id':'isar','map_name':"Isar's Cross",'status':'waiting','capacity':2,'members':1,'ready':0,
            'gold':100,'base_income':2,'turns':-1,'fog':False,'shroud':False,'observers':True,
            'seats':[{'side':1,'account_id':self.player['_id'],'username':'PlayerOne','ready':False,'unit_type':'Spearman'},
                     {'side':2,'account_id':'','username':'','ready':False,'unit_type':''}]}
        generation=str(uuid4());service=AdminRooms(self.domain)
        service.publish({'generation':generation,'register':True,'rooms':[room]})
        path='/rooms/'+room['id']
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('<script>unsafe</script>',response.get_data(as_text=True))
        self.export_render(path,response)
        record=service.detail(room['id'])
        form=self.form(record['revision'],generation=generation)
        self.assertEqual(self.client.post(path+'/close',data={k:v for k,v in form.items() if k!='confirmation'}).status_code,400)
        self.assertEqual(self.client.post(path+'/close',data=form).status_code,302)
        self.assertEqual(service.detail(room['id'])['close_status'],'pending')
        self.assertEqual(service.detail(room['id'])['status'],'waiting')
        service.publish({'generation':generation,'register':False,'rooms':[]})
        self.assertIn('closed',self.client.get(path).get_data(as_text=True))


if __name__=='__main__':unittest.main()
