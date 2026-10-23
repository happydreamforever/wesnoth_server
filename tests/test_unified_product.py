"""Production v2 transactions in a newly owned local replica-set database.

ALLIANCE_TEST_MONGO_URI must name a disposable loopback replica set. No .env,
private game runtime or old user database is opened by this suite.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import sys
import unittest
from uuid import uuid4
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from bson.int64 import Int64
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService, DomainError, _now
from alliance.heroes import load_catalog, hero_progress, spent_experience, scaled_stat
from alliance.schema import bootstrap_schema
from alliance.rules import MISSIONS, MISSION_VERSION, RULESET_VERSION

class HeroMath(unittest.TestCase):
    def test_exact_thresholds_and_uncapped_growth(self):
        for level in [1,2,3,50,1000,1000000]:
            total=spent_experience(level)
            self.assertEqual(hero_progress(total)['hero_level'],level)
            self.assertEqual(hero_progress(total)['experience'],0)
            if level>1:self.assertEqual(hero_progress(total-1)['hero_level'],level-1)
            self.assertEqual(spent_experience(level+1)-total,5*level*level+15)
    def test_half_up_and_overflow(self):
        self.assertEqual(scaled_stat(25,2,2),26)
        self.assertEqual(scaled_stat(5,11,1),6)
        for value in [-1,True,1.2]:
            with self.assertRaises(ValueError):hero_progress(value)
    def test_bson_int64_progression_and_public_json_integers(self):
        for total in (0, 2147483648, 9223372036854775807):
            result = hero_progress(Int64(total))
            self.assertEqual(result, hero_progress(total))
            self.assertTrue(all(type(value) is int for value in result.values()))
            self.assertEqual(json.loads(json.dumps(result)), result)
        for total in (-1, 9223372036854775808):
            with self.assertRaises(ValueError): hero_progress(Int64(total))
    def test_catalogue_identities(self):
        c,d=load_catalog();self.assertEqual(len(d),64)
        self.assertGreater(len(c['heroes']),100);self.assertGreater(len(c['forms']),300)
        self.assertEqual(len({h['id'] for h in c['heroes']}),len(c['heroes']))
        self.assertEqual(len({f['id'] for f in c['forms']}),len(c['forms']))
        for form in c['forms']:
            self.assertIn(form['hero_id'],{h['id'] for h in c['heroes']})
            self.assertGreaterEqual(form['native_level'],0)
            self.assertLessEqual(form['native_level'],20)

@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'),'Requires disposable local replica set')
class UnifiedProduct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri=os.environ['ALLIANCE_TEST_MONGO_URI'];parsed=urlsplit(uri)
        if parsed.hostname not in ('localhost','127.0.0.1','::1') or ',' in parsed.netloc:raise RuntimeError('Loopback test MongoDB required')
        cls.client=MongoClient(uri,tz_aware=True,serverSelectionTimeoutMS=5000)
        if not cls.client.admin.command('hello').get('isWritablePrimary'):raise RuntimeError('Writable replica set required')
    @classmethod
    def tearDownClass(cls):cls.client.close()
    def setUp(self):
        self.name='alliance_test_'+uuid4().hex;self.db=self.client[self.name];bootstrap_schema(self.db);bootstrap_auth_schema(self.db)
        self.domain=AllianceService(self.db);self.i=0;self.catalog,self.digest=load_catalog()
        self.campaign=next(c for c in self.catalog['campaigns'] if c['aliases'])
        self.alias=self.campaign['aliases'][0];self.hero=self.alias['hero_id'];self.form=self.alias['forms'][0]['form_id']
    def tearDown(self):self.client.drop_database(self.name)
    def player(self,unlock=False):
        self.i+=1;a=self.domain.register('Player_'+str(self.i),hash_password('test player password '+str(self.i)))['_id']
        if unlock:self.seed(a)
        return a
    def seed(self,a,hero=None,forms=None,total=0):
        self.db.account_heroes.insert_one({'_id':str(uuid4()),'account_id':a,'hero_id':hero or self.hero,
            'forms':forms or [self.form], 'total_experience':total,'revision':0})
    def begin(self,a):return self.domain.story_begin(a,self.campaign['id'],self.catalog['version'],self.digest)
    def checkpoint(self,run,**overrides):
        result={'run_id':run['run_id'],'checkpoint_id':str(uuid4()),'sequence':0,
            'scenario_id':self.campaign['first_scenario'],'next_scenario_id':'','outcome':'win','nonce':run['nonce'],
            'replay_sha256':'a'*64,'heroes':[{'hero_id':self.hero,'unit_id':self.alias['unit_id'],'form_id':self.form,
                'unlocked_forms':[self.form],'earned_experience':7}]}
        result.update(overrides);return result
    def code(self,code,call):
        with self.assertRaises(DomainError) as c:call()
        self.assertEqual(c.exception.code,code)
    def test_signup_empty_collection_and_login_v2(self):
        a=self.player();profile=self.domain.get_account(a)
        self.assertEqual(profile['heroes'],[]);self.assertNotIn('leader',profile)
        login=AuthService(self.db).authenticate('Player_1','test player password 1','player')
        self.assertEqual(login['account']['heroes'],[])
        self.assertEqual(login['account']['database_generation'],profile['database_generation'])
    def test_stored_int64_hero_profile_training_and_team_rewards(self):
        ps, ts, run = self.battle()
        starting = 2147483648
        actor = ps[0][0]
        self.db.account_heroes.update_one({'account_id':actor,'hero_id':self.hero},
                                         {'$set':{'total_experience':Int64(starting)}})
        self.assertIsInstance(self.db.account_heroes.find_one({'account_id':actor})['total_experience'], Int64)
        profile = self.domain.get_account(actor)['heroes'][0]
        self.assertEqual(profile['total_experience'], starting)
        self.assertIs(type(profile['total_experience']), int)
        self.assertGreater(profile['hero_level'], 1000)
        training = self.domain.progression_start(actor, MISSIONS[0], self.hero, self.form)['run']
        self.assertEqual(training['hero_level'], profile['hero_level'])
        args = dict(run_id=training['id'],mission_id=MISSIONS[0],mission_version=MISSION_VERSION,
            nonce=training['nonce'],outcome='win',replay_sha256='c'*64,format='alliance-native-campaign-result-v1')
        result = self.domain.progression_finish(actor, **args)
        self.assertEqual(self.domain.progression_finish(actor, **args), result)
        for player in sum(ps, []): self.domain.directory_select_hero(player, run, self.hero, self.form)
        for player in sum(ps, []): self.domain.directory_battle_ready(player, run, True)
        for captain in (ps[0][0], ps[1][0]): self.domain.directory_approve_battle(captain, run)
        self.domain.start_battle(actor, run)
        result = self.domain.finish_battle(run, ts[0])
        self.assertEqual(self.domain.finish_battle(run, ts[0]), result)
        hero = self.domain.get_account(actor)['heroes'][0]
        self.assertEqual(hero['total_experience'], starting + 40)
        self.assertIs(type(hero['total_experience']), int)
        self.assertEqual(json.loads(json.dumps(hero)), hero)
    def test_victory_unlocks_and_exactly_once(self):
        a=self.player();run=self.begin(a);data=self.checkpoint(run)
        result=self.domain.story_checkpoint(a,data)
        self.assertEqual(result['rewards'],[{'hero_id':self.hero,'experience_awarded':27}])
        self.assertEqual(result['heroes'][0]['hero_level'],2)
        self.assertEqual(result['heroes'][0]['experience'],7)
        self.assertEqual(self.domain.story_checkpoint(a,data),result)
        self.assertEqual(self.db.account_heroes.find_one()['total_experience'],27)
        changed=deepcopy(data);changed['heroes'][0]['earned_experience']=8
        self.code('result_conflict',lambda:self.domain.story_checkpoint(a,changed))
    def test_defeat_zero_and_retry(self):
        a=self.player();run=self.begin(a);loss=self.checkpoint(run,outcome='loss')
        self.assertEqual(self.domain.story_checkpoint(a,loss)['heroes'],[])
        win=self.checkpoint(run,sequence=1)
        self.assertEqual(self.domain.story_checkpoint(a,win)['rewards'][0]['experience_awarded'],27)
    def test_owner_nonce_catalogue_and_sequence_guards(self):
        a=self.player();b=self.player();run=self.begin(a);data=self.checkpoint(run)
        self.code('forbidden',lambda:self.domain.story_checkpoint(b,data))
        self.code('invalid_result',lambda:self.domain.story_checkpoint(a,{**data,'nonce':'f'*64}))
        self.code('checkpoint_conflict',lambda:self.domain.story_checkpoint(a,{**data,'sequence':4}))
        self.code('catalog_mismatch',lambda:self.domain.story_begin(a,self.campaign['id'],self.catalog['version'],'0'*64))
        self.assertEqual(self.db.account_heroes.count_documents({}),0)
    def test_bad_hero_form_recruit_and_duplicate_rejected(self):
        a=self.player();run=self.begin(a);data=self.checkpoint(run)
        for changes in [{'hero_id':'regular-recruit'}, {'unit_id':'RandomSoldier'}, {'unlocked_forms':['forged']}, {'hero_id':[]}]:
            forged=deepcopy(data);forged['heroes'][0].update(changes)
            self.code('invalid_result',lambda:self.domain.story_checkpoint(a,forged))
        data['heroes']*=2;self.code('invalid_result',lambda:self.domain.story_checkpoint(a,data))
        self.assertEqual(self.db.account_heroes.count_documents({}),0)
    def test_concurrent_checkpoint_credits_once(self):
        a=self.player();data=self.checkpoint(self.begin(a))
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.domain.story_checkpoint(a,data),range(4)))
        self.assertEqual(results,[results[0]]*4);self.assertEqual(self.db.account_heroes.find_one()['total_experience'],27)
    def test_new_playthrough_earns_again_but_same_run_scenario_does_not(self):
        a=self.player();run=self.begin(a);data=self.checkpoint(run,next_scenario_id=self.campaign['first_scenario'])
        self.domain.story_checkpoint(a,data)
        repeated=self.checkpoint(run,sequence=1);result=self.domain.story_checkpoint(a,repeated)
        self.assertEqual(result['rewards'][0]['experience_awarded'],0)
        self.domain.story_checkpoint(a,self.checkpoint(self.begin(a)))
        self.assertEqual(self.db.account_heroes.find_one()['total_experience'],54)
    def test_checkpoint_waits_during_reserved_training(self):
        a=self.player(True);story=self.begin(a);training=self.domain.progression_start(a,MISSIONS[0],self.hero,self.form)['run']
        self.code('busy',lambda:self.domain.story_checkpoint(a,self.checkpoint(story)))
        self.domain.progression_cancel(a,training['id']);self.domain.story_checkpoint(a,self.checkpoint(story))
    def test_training_selected_hero_and_idempotent_reward(self):
        a=self.player(True);run=self.domain.progression_start(a,MISSIONS[0],self.hero,self.form)['run']
        self.assertEqual(run['hero_id'],self.hero);self.assertEqual(run['hero_level'],1)
        args=dict(run_id=run['id'],mission_id=MISSIONS[0],mission_version=MISSION_VERSION,nonce=run['nonce'],outcome='win',
            replay_sha256='c'*64,format='alliance-native-campaign-result-v1')
        result=self.domain.progression_finish(a,**args)
        self.assertEqual(result['experience_awarded'],20);self.assertEqual(result,self.domain.progression_finish(a,**args))
        self.assertTrue(self.domain.progression_catalog(a)['missions'][1]['unlocked'])
    def battle(self):
        players=[[self.player(True),self.player(True)],[self.player(True),self.player(True)]];teams=[]
        for i,ps in enumerate(players):
            team=self.domain.create_team(ps[0],'Team '+str(i),'area-1')['_id']
            self.domain.request_join(ps[1],team);self.domain.directory_approve_application(ps[0],team,ps[1]);teams.append(team)
        plan=self.domain.create_battle(players[0][0],teams[1],'isars-cross',dict(zip(teams,players)),native_plan=True)
        return players,teams,plan['id']
    def test_plan_requires_own_hero_and_choice_clears_consents(self):
        ps,ts,run=self.battle()
        self.code('hero_required',lambda:self.domain.directory_battle_ready(ps[0][0],run,True))
        for p in sum(ps,[]):self.domain.directory_select_hero(p,run,self.hero,self.form)
        for p in sum(ps,[]):self.domain.directory_battle_ready(p,run,True)
        for p in [ps[0][0],ps[1][0]]:self.domain.directory_approve_battle(p,run)
        other=next(f for f in self.catalog['forms'] if f['hero_id']!=self.hero)
        self.seed(ps[0][0],other['hero_id'],[other['id']])
        result=self.domain.directory_select_hero(ps[0][0],run,other['hero_id'],other['id'])
        self.assertFalse(any(t['approved'] for t in result['teams']))
        self.assertFalse(any(p['ready'] for t in result['teams'] for p in t['players']))
    def test_team_reward_selected_hero_only(self):
        ps,ts,run=self.battle()
        other=next(f for f in self.catalog['forms'] if f['hero_id']!=self.hero)
        self.seed(ps[0][0],other['hero_id'],[other['id']])
        for p in sum(ps,[]):self.domain.directory_select_hero(p,run,self.hero,self.form)
        for p in sum(ps,[]):self.domain.directory_battle_ready(p,run,True)
        for p in [ps[0][0],ps[1][0]]:self.domain.directory_approve_battle(p,run)
        self.domain.start_battle(ps[0][0],run)
        self.code('busy',lambda:self.domain.directory_select_hero(ps[0][0],run,other['hero_id'],other['id']))
        result=self.domain.finish_battle(run,ts[0]);self.assertEqual(result,self.domain.finish_battle(run,ts[0]))
        self.assertEqual(self.db.account_heroes.find_one({'account_id':ps[0][0],'hero_id':self.hero})['total_experience'],20)
        self.assertEqual(self.db.account_heroes.find_one({'account_id':ps[0][0],'hero_id':other['hero_id']})['total_experience'],0)
        self.assertEqual(self.domain.get_team(ps[0][0],ts[0])['experience'],100)
    def test_casual_tickets_owner_expiry_single_use_and_no_reward(self):
        a=self.player(True);b=self.player(True);game=str(uuid4());token=AuthService(self.db).authenticate('Player_1','test player password 1','player')['token'];ticket=self.domain.casual_ticket(a,token)
        before=self.db.account_heroes.find_one({'account_id':a})
        admitted=self.domain.casual_admit(ticket['ticket'],ticket['username']);self.assertEqual(admitted['account_id'],a)
        self.code('invalid_ticket',lambda:self.domain.casual_admit(ticket['ticket'],ticket['username']))
        selected=self.domain.casual_select(a,game,1,self.hero,self.form,token)
        self.code('invalid_ticket',lambda:self.domain.casual_consume_hero(selected['selection_ticket'],b,game,1))
        self.domain.casual_consume_hero(selected['selection_ticket'],a,game,1)
        self.code('invalid_ticket',lambda:self.domain.casual_consume_hero(selected['selection_ticket'],a,game,1))
        exp=self.domain.casual_ticket(a,token);self.db.casual_tickets.update_many({}, {'$set':{'expires_at':_now()-timedelta(seconds=1)}})
        self.code('invalid_ticket',lambda:self.domain.casual_admit(exp['ticket'],exp['username']))
        self.assertEqual(before,self.db.account_heroes.find_one({'account_id':a}))
    def test_casual_tickets_are_invalidated_by_logout(self):
        a=self.player(True);auth=AuthService(self.db)
        token=auth.authenticate('Player_1','test player password 1','player')['token']
        lobby=self.domain.casual_ticket(a,token)
        game=str(uuid4());hero=self.domain.casual_select(a,game,1,self.hero,self.form,token)
        auth.revoke_token(token)
        self.code('invalid_ticket',lambda:self.domain.casual_admit(lobby['ticket'],lobby['username']))
        self.code('invalid_ticket',lambda:self.domain.casual_consume_hero(hero['selection_ticket'],a,game,1))
        self.code('invalid_ticket',lambda:self.domain.casual_ticket(a,token))

    def test_casual_saved_snapshot_and_admin_correction(self):
        a=self.player(True);admin=self.domain.bootstrap_admin('Admin',hash_password('test admin password'))['_id'];game=str(uuid4())
        selection=self.domain._selection(a,self.hero,self.form)
        players=[{'account_id':a,'username':'Player_1','side':1,'selection':selection}]
        frozen=self.domain.casual_freeze(game,players)
        self.domain.admin_correct_hero_experience(admin,a,self.hero,99,'Test correction',0)
        self.assertEqual(self.domain.casual_restore(game),frozen)
        self.assertEqual(self.domain.casual_freeze(game,players),frozen)
        players[0]['selection']=self.domain._selection(a,self.hero,self.form)
        self.code('snapshot_conflict',lambda:self.domain.casual_freeze(game,players))
        self.assertEqual(self.db.admin_audit.count_documents({'action':'correct_hero_experience'}),1)
    def test_old_schema_refused_without_mutation(self):
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':1}})
        with self.assertRaises(RuntimeError):bootstrap_schema(self.db)
        self.assertEqual(self.db.schema_metadata.find_one({'_id':'alliance'})['version'],1)
if __name__=='__main__':unittest.main()
