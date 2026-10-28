"""New company transactions against disposable MongoDB; no runtime is accessed."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import unittest
from uuid import uuid4
import test_unified_product as fixture
from alliance.company import BASICS, TROOPS, BRACKETS, hero_points, advance_native
from alliance.domain import DomainError
from alliance.world import bootstrap_world_schema
from alliance.heroes import spent_experience

class BalanceTests(unittest.TestCase):
    def test_brackets_and_native_advancement(self):
        self.assertEqual(len(BASICS),6)
        self.assertEqual(advance_native('Spearman',0,42,{}),('Swordsman',0,['Swordsman']))
        self.assertEqual(advance_native('Mage',0,48,{'Mage':'Red Mage'}),('Red Mage',0,['Red Mage']))
        self.assertEqual(advance_native('Great Mage',199,1000,{})[:2],('Great Mage',199))
        self.assertEqual([BRACKETS[x]['budget'] for x in ('scout','veteran','champion')],[120,240,420])

@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'),'Requires disposable local replica set')
class CompanyTests(unittest.TestCase):
    setUpClass=classmethod(fixture.UnifiedProduct.setUpClass.__func__)
    tearDownClass=classmethod(fixture.UnifiedProduct.tearDownClass.__func__)
    tearDown=fixture.UnifiedProduct.tearDown
    player=fixture.UnifiedProduct.player
    seed=fixture.UnifiedProduct.seed
    code=fixture.UnifiedProduct.code
    def setUp(self):
        fixture.UnifiedProduct.setUp(self);bootstrap_world_schema(self.db)
        form=next(f for f in self.catalog['forms'] if f['native_level']==1 and f['source_type']=='Spearman')
        self.hero=form['hero_id'];self.form=form['id']
    def command(self,actor,op,**data):
        if op.startswith('company_') and op!='company_initialize':data.setdefault('expected_revision',self.db.companies.find_one({'_id':actor})['revision'])
        data.setdefault('command_id',str(uuid4()))
        return self.domain.world_command(actor,op,data)['data']
    def company(self):
        a=self.player(True);self.command(a,'company_initialize');snap=self.domain.world_query(a,'company',{})['data']
        self.command(a,'company_select',hero_id=self.hero,form_id=self.form,soldier_ids=[s['id'] for s in snap['soldiers'][:4]],bracket='scout')
        return a
    def expedition(self,actor):
        return self.command(actor,'company_expedition',mission_id='company_border_patrol')['battle']['id']
    def load(self,run,worker='test_worker_123'):
        desc=self.domain.world_worker_acquire(worker);self.assertEqual(desc['run_id'],run)
        self.domain.world_worker_loaded(run,worker,desc['generation'],'a'*64)
        for actor in desc['required_humans']:
            self.domain.world_human_join(actor,run);result=self.domain.world_human_loaded(actor,run,desc['generation'],'a'*64)
        self.assertEqual(result['state'],'running')
        return desc
    def evidence(self,desc,winner=None,dead=None,earned=0):
        units=[]
        for unit in desc['units']:
            typ,xp=(unit['unit_type'],0)
            amount=earned if unit['kind']=='soldier' else 0
            if unit['kind']=='soldier':typ,xp,_=advance_native(unit['unit_type'],unit['xp'],amount,unit['advancement_preferences'])
            units.append({'instance_id':unit['instance_id'],'earned_xp':amount,'final_type':typ,'final_xp':xp,
                'dead':unit['instance_id']==dead,'deployed':True})
        return {'scenario_sha256':'a'*64,'replay_sha256':'b'*64,'ledger_sha256':'c'*64,'command_chain_sha256':'d'*64,
            'event_count':len(units),'terminal':'victory','outcome':'win','winner_team_id':winner or desc['sides'][0]['team_id'],
            'units':units,'sync_valid':True,'combat_verified':True,'completed_rounds':2}
    def test_no_hero_no_starter_and_six_once(self):
        a=self.player();self.code('hero_required',lambda:self.command(a,'company_initialize'))
        self.seed(a);self.command(a,'company_initialize');self.command(a,'company_initialize')
        rows=list(self.db.company_soldiers.find({'owner_id':a}));self.assertEqual(len(rows),6);self.assertEqual({r['unit_type'] for r in rows},set(BASICS))
        self.assertEqual(self.db.account_heroes.count_documents({'account_id':a}),1)
    def test_idempotency_actor_binding_and_status(self):
        a=self.company();p={'command_id':str(uuid4()),'expected_revision':1,'unit_type':'Mage'}
        one=self.domain.world_command(a,'company_recruit',p);two=self.domain.world_command(a,'company_recruit',p)
        self.assertEqual(one,two);self.assertEqual(self.db.company_soldiers.count_documents({'owner_id':a}),7)
        self.code('command_conflict',lambda:self.domain.world_command(a,'company_recruit',{**p,'unit_type':'Bowman'}))
        self.assertTrue(self.domain.world_query(a,'command_status',{'command_id':p['command_id']})['data']['found'])
        b=self.player();self.assertFalse(self.domain.world_query(b,'command_status',{'command_id':p['command_id']})['data']['found'])
    def test_capacity_and_stale_edits(self):
        a=self.company()
        for i in range(6):self.command(a,'company_recruit',unit_type='Spearman')
        self.code('capacity',lambda:self.command(a,'company_recruit',unit_type='Mage'))
        self.code('stale_revision',lambda:self.command(a,'company_rest',expected_revision=0))
    def test_concurrent_recruits_same_revision_only_one(self):
        a=self.company();rev=self.db.companies.find_one({'_id':a})['revision']
        def recruit(_):
            try:self.command(a,'company_recruit',expected_revision=rev,unit_type='Mage');return 'ok'
            except DomainError as error:return error.code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(recruit,range(2)))
        self.assertEqual(sorted(results),['ok','stale_revision']);self.assertEqual(self.db.company_soldiers.count_documents({'owner_id':a}),7)
    def test_bracket_caps_do_not_change_stored_xp(self):
        a=self.company();self.db.account_heroes.update_one({'account_id':a},{'$set':{'total_experience':spent_experience(300)}})
        company=self.db.companies.find_one({'_id':a});selection=deepcopy(company['warband']);selection['soldier_ids']=[]
        force=self.domain._company_force(a,selection);self.assertEqual(force['units'][0]['effective_level'],5)
        self.assertEqual(force['units'][0]['stored_level'],300);self.assertEqual(self.db.account_heroes.find_one({'account_id':a})['total_experience'],spent_experience(300))
    def test_expedition_settlement_rest_storyxp_and_duplicate(self):
        a=self.company();run=self.expedition(a);desc=self.load(run)
        # Concurrent authored campaign increment is not erased by deployment snapshot.
        self.db.account_heroes.update_one({'account_id':a},{'$inc':{'total_experience':27,'revision':1}})
        hero=desc['units'][0]['instance_id'];evidence=self.evidence(desc,dead=hero,earned=5)
        receipt=self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],evidence)
        self.assertEqual(self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],evidence),receipt)
        self.assertEqual(self.db.account_heroes.find_one({'account_id':a})['total_experience'],47)
        self.assertEqual(len(receipt['soldier_rewards']),len(desc['units'])-1)
        self.assertTrue(all(r['owner_id']==a and r['earned_xp']==5 and r['final_xp']==5 and r['before_type']==r['after_type'] and r['recover_at_round'] is None for r in receipt['soldier_rewards']))
        self.assertEqual(self.db.network_battle_reservations.count_documents({}),0)
        self.assertEqual(self.db.company_wounds.find_one()['kind'],'rest_wounded')
        self.command(a,'company_rest');self.assertEqual(self.db.company_wounds.count_documents({}),0)
        self.assertTrue(all(s['xp']==5 for s in self.db.company_soldiers.find({'owner_id':a,'_id':{'$in':self.db.companies.find_one({'_id':a})['warband']['soldier_ids']}})))
    def test_invalid_ledger_rolls_back_and_player_cannot_submit(self):
        a=self.company();run=self.expedition(a);desc=self.load(run);proof=self.evidence(desc)
        proof['units'][1]['final_type']='Great Mage'
        self.code('invalid_evidence',lambda:self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],proof))
        self.assertEqual(self.db.world_settlements.count_documents({}),0);self.assertEqual(self.db.account_heroes.find_one({'account_id':a})['total_experience'],0)
        self.code('invalid_input',lambda:self.domain.world_command(a,'worker_finish',{'command_id':str(uuid4())}))
    def test_mismatched_scenario_disputes(self):
        a=self.company();run=self.expedition(a);desc=self.domain.world_worker_acquire('test_worker_123')
        self.domain.world_worker_loaded(run,'test_worker_123',desc['generation'],'a'*64)
        result=self.domain.world_human_loaded(a,run,desc['generation'],'f'*64)
        self.assertEqual(result['state'],'disputed');self.assertEqual(self.db.world_settlements.count_documents({}),0)
    def test_native_reservation_blocks_parallel_individual(self):
        a=self.company();run=self.expedition(a)
        self.code('busy',lambda:self.domain.network_prepare(str(uuid4()),str(uuid4()),[a,self.player(True)]))
        self.code('busy',lambda:self.command(a,'company_select',hero_id=self.hero,form_id=self.form,soldier_ids=[],bracket='scout'))

    def test_concurrent_duplicate_native_terminal_credits_once(self):
        a=self.company();run=self.expedition(a);desc=self.load(run);proof=self.evidence(desc,earned=6)
        def finish(_):return self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],proof)
        with ThreadPoolExecutor(2) as pool:receipts=list(pool.map(finish,range(2)))
        self.assertEqual(receipts[0],receipts[1]);self.assertEqual(self.db.world_settlements.count_documents({}),1)
        self.assertEqual(self.db.account_heroes.find_one({'account_id':a})['total_experience'],20)
