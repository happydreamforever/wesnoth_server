"""World routes use player identity; host commitments stay behind admin CSRF."""
import json
from uuid import uuid4
from test_alliance_web import AllianceWebTests as Fixture
from alliance.world import WORLD_SCHEMAS

class WorldWeb(Fixture):
    def setUp(self):
        super().setUp()
        for name in WORLD_SCHEMAS:self.db[name].delete_many({})

    def test_player_query_and_admin_namespace_are_separate(self):
        headers=self.player_headers()
        reply=self.client.post('/internal/v1/world/query',headers=headers,json={'operation':'company','payload':{}})
        self.assertEqual(reply.status_code,200,reply.get_data(as_text=True))
        self.assertEqual(reply.json['actor_id'],self.player['_id'])
        self.assertEqual(reply.json['version'],1)
        self.assertNotIn('password',reply.get_data(as_text=True))
        self.assertEqual(self.client.get('/world').status_code,302)
        for operation in ('bootstrap','phase','advance','worker_settle','enroll_team'):
            response=self.client.post('/internal/v1/world/command',headers=headers,
                json={'operation':operation,'payload':{'command_id':str(uuid4())}})
            self.assertEqual(response.status_code,409)
        self.assertIsNone(self.db.world_states.find_one({}))
        self.assertEqual(self.db.world_command_receipts.count_documents({}),0)

    def test_duplicate_unknown_actor_and_unbounded_body_rejected(self):
        headers={**self.player_headers(),'Content-Type':'application/json'}
        samples=['{"operation":"company","operation":"snapshot","payload":{}}',
                 '{"operation":"company","payload":{},"actor_id":"'+self.admin['_id']+'"}',
                 '{"operation":"company","payload":{"x":NaN}}',
                 '{"operation":"company","payload":{"x":'+('['*20)+'0'+(']'*20)+'}}']
        for raw in samples:
            response=self.client.post('/internal/v1/world/query',headers=headers,data=raw)
            self.assertEqual(response.status_code,400,response.get_data(as_text=True))
        self.assertEqual(self.client.post('/internal/v1/world/query',headers={**headers,'Origin':'http://127.0.0.1:18765'},json={'operation':'company','payload':{}}).status_code,403)
        self.assertEqual(self.client.post('/internal/v1/world/query',headers=self.bridge,json={'operation':'company','payload':{}}).status_code,401)

    def test_host_form_requires_review_csrf_and_records_bootstrap_once(self):
        other=self.domain.register('OtherCaptain',self.password_hash)
        teams=[self.domain.create_team(self.player['_id'],'First Founders')['_id'],self.domain.create_team(other['_id'],'Second Founders')['_id']]
        self.login_admin()
        form={'command_id':str(uuid4()),'operation':'bootstrap','team_one':teams[0],'team_two':teams[1],'confirmation':'confirmed'}
        self.assertEqual(self.client.post('/world/command',data=form).status_code,400)
        form['csrf_token']=self.csrf('/world')
        self.assertEqual(self.client.post('/world/command',data=form).status_code,302)
        self.assertEqual(self.db.world_castles.count_documents({}),6)
        self.assertEqual(self.db.world_states.count_documents({}),1)
        self.assertEqual(self.client.post('/world/command',data=form).status_code,302)
        self.assertEqual(self.db.world_castles.count_documents({}),6)
        page=self.client.get('/world')
        self.assertEqual(page.status_code,200)
        self.assertIn('First Founders',page.get_data(as_text=True))
        self.assertNotIn(self.password_hash,page.get_data(as_text=True))
        form['command_id']=str(uuid4())
        self.assertEqual(self.client.post('/world/command',data=form).status_code,409)

for _name in dir(Fixture):
    if _name.startswith('test_') and _name not in WorldWeb.__dict__:setattr(WorldWeb,_name,None)
del Fixture
