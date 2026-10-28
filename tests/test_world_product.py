"""Transactional host rounds, consent, territory and native evidence acceptance."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import os
import unittest
from uuid import uuid4
import test_company_product as company_fixture
from alliance.auth import hash_password
from alliance.domain import DomainError, _now
from alliance.flexible import DEFAULT_SETTINGS

@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'),'Requires disposable local replica set')
class WorldTests(unittest.TestCase):
    setUpClass=classmethod(company_fixture.CompanyTests.setUpClass.__func__)
    tearDownClass=classmethod(company_fixture.CompanyTests.tearDownClass.__func__)
    tearDown=company_fixture.CompanyTests.tearDown
    player=company_fixture.CompanyTests.player;seed=company_fixture.CompanyTests.seed;code=company_fixture.CompanyTests.code
    command=company_fixture.CompanyTests.command;company=company_fixture.CompanyTests.company
    load=company_fixture.CompanyTests.load;evidence=company_fixture.CompanyTests.evidence
    def setUp(self):
        company_fixture.CompanyTests.setUp(self)
        self.admin=self.domain.bootstrap_admin('Host',hash_password('private fixture password'))['_id']
        self.players=[self.company(),self.company()]
        self.teams=[self.domain.create_team(a,'Team_'+str(i))['_id'] for i,a in enumerate(self.players)]
        self.host('bootstrap',team_ids=self.teams)
        self.homes=[self.db.world_teams.find_one({'_id':tid}) for tid in self.teams]
        for a in self.players:self.command(a,'enroll')
    def host(self,op,**p):
        p.setdefault('command_id',str(uuid4()));return self.domain.world_admin_command(self.admin,op,p)['data']
    def phase(self):
        return self.host('phase',expected_phase=self.db.world_states.find_one() ['phase'])
    def finish_round(self):
        while self.db.world_states.find_one()['phase']!='settlement':self.phase()
        return self.host('advance')
    def neutral(self,index=0):
        cap=self.db.world_castles.find_one({'_id':self.homes[index]['capital_id']})
        return self.db.world_castles.find_one({'area_id':cap['area_id'],'kind':'supply'})
    def attack_neutral(self,index=0):
        a=self.players[index]
        run=self.command(a,'attack',origin_id=self.homes[index]['capital_id'],target_id=self.neutral(index)['_id'],bracket='scout')['battle']['id']
        self.command(a,'battle_ready',run_id=run,ready=True);self.command(a,'battle_approve',run_id=run)
        return run
    def test_bootstrap_once_and_host_authority(self):
        self.assertEqual(self.db.world_castles.count_documents({}),6);self.assertEqual(self.db.world_areas.count_documents({}),2)
        self.assertEqual([x['supply'] for x in self.db.world_teams.find({})],[20,20])
        self.code('already_initialized',lambda:self.host('bootstrap',team_ids=self.teams))
        self.code('forbidden',lambda:self.domain.world_admin_snapshot(self.players[0]))
        self.assertEqual(self.db.world_castles.count_documents({'owner_team_id':None}),2)
    def test_peaceful_round_no_income_and_nonce_idempotency(self):
        while self.db.world_states.find_one()['phase']!='settlement':self.phase()
        nonce=str(uuid4());first=self.host('advance',command_id=nonce);second=self.host('advance',command_id=nonce)
        self.assertEqual(first,second);self.assertEqual(self.db.world_states.find_one()['round'],2)
        self.assertFalse(first['receipt']['combat']);self.assertEqual([x['supply'] for x in self.db.world_teams.find({})],[20,20])
    def test_roadworks_once_cost_and_friendly_station(self):
        a=self.players[0];castle=self.homes[0]['capital_id'];self.command(a,'roadworks',castle_id=castle)
        self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[0]})['supply'],5)
        self.code('already_built',lambda:self.command(a,'roadworks',castle_id=castle))
        self.command(a,'station',castle_id=self.homes[0]['frontier_id'])
        self.code('round_limit',lambda:self.command(a,'station',castle_id=self.homes[0]['frontier_id']))
        self.phase();self.assertEqual(self.db.companies.find_one({'_id':a})['location'],self.homes[0]['frontier_id'])
    def test_neutral_capture_native_proof_once_and_world_wound_boundary(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        dead=desc['units'][0]['instance_id'];proof=self.evidence(desc,dead=dead,earned=4)
        receipt=self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],proof)
        self.assertEqual(receipt,self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],proof))
        self.assertEqual(self.neutral()['owner_team_id'],self.teams[0]);self.assertEqual(self.db.teams.find_one({'_id':self.teams[0]})['experience'],100)
        self.assertEqual(self.db.company_wounds.find_one()['kind'],'world_wounded')
        self.command(self.players[0],'company_rest');self.assertEqual(self.db.company_wounds.count_documents({}),1)
        self.phase();result=self.host('advance');self.assertEqual(result['receipt']['healed'],1)
        self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[0]})['supply'],25)
        self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[1]})['supply'],23)
    def test_disjoint_attacks_concurrent_settle_and_one_team_attack(self):
        runs=[self.attack_neutral(i) for i in range(2)]
        self.code('round_limit',lambda:self.command(self.players[0],'attack',origin_id=self.homes[0]['capital_id'],target_id=self.neutral()['_id'],bracket='scout'))
        self.phase();self.phase();self.phase();descs={}
        for i in range(2):
            desc=self.domain.world_worker_acquire('worker_'+str(i)+'_abcdefgh');descs[desc['run_id']]=(desc,'worker_'+str(i)+'_abcdefgh')
            self.domain.world_worker_loaded(desc['run_id'],descs[desc['run_id']][1],desc['generation'],'a'*64)
            for actor in desc['required_humans']:self.domain.world_human_loaded(actor,desc['run_id'],desc['generation'],'a'*64)
        def finish(run):
            desc,worker=descs[run];return self.domain.world_worker_finish(run,worker,desc['generation'],self.evidence(desc))
        with ThreadPoolExecutor(2) as pool:list(pool.map(finish,runs))
        self.assertEqual(self.db.world_settlements.count_documents({}),2)
        self.assertEqual(self.db.world_castle_reservations.count_documents({}),0)
    def test_missing_ready_prevents_host_commit_no_forfeit(self):
        a=self.players[0];run=self.command(a,'attack',origin_id=self.homes[0]['capital_id'],target_id=self.neutral()['_id'],bracket='scout')['battle']['id']
        self.phase();self.code('consent_required',self.phase)
        self.assertEqual(self.db.world_states.find_one()['phase'],'deployment');self.assertIsNone(self.neutral()['owner_team_id'])
        self.host('cancel',run_id=run,reason='Owner is unavailable');self.finish_round()
        self.assertEqual(self.db.world_states.find_one()['round'],2)
    def test_preparation_expiry_releases_without_capture(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.domain.world_worker_acquire('test_worker_123')
        self.db.world_contracts.update_one({'_id':run},{'$set':{'prepare_until':_now()-timedelta(seconds=1)}})
        self.assertIsNone(self.domain.world_worker_acquire('other_worker_123'))
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'cancelled');self.assertIsNone(self.neutral()['owner_team_id'])
        self.assertEqual(self.db.network_battle_reservations.count_documents({}),0)
    def test_standing_defense_survives_story_xp_and_withdraws(self):
        a=self.players[0];castle=self.homes[0]['capital_id'];offer=self.command(a,'defense_offer',castle_id=castle,bracket='scout')['defense']
        self.assertEqual(offer['status'],'active')
        self.db.account_heroes.update_one({'account_id':a},{'$inc':{'total_experience':27,'revision':1}})
        self.assertEqual(self.domain.world_query(a,'snapshot',{})['data']['defenses'][0]['status'],'active')
        self.code('busy',lambda:self.command(a,'company_expedition',mission_id='company_border_patrol'))
        self.command(a,'defense_withdraw',assignment_id=offer['id']);self.assertEqual(self.db.company_asset_locks.count_documents({}),0)
    def test_neutral_competing_castle_claim_has_one_winner(self):
        a=self.players[0];p={'origin_id':self.homes[0]['capital_id'],'target_id':self.neutral()['_id'],'bracket':'scout'}
        def attack(_):
            try:return self.command(a,'attack',**p)['battle']['id']
            except DomainError as error:return error.code
        with ThreadPoolExecutor(2) as pool:outcomes=list(pool.map(attack,range(2)))
        self.assertEqual(outcomes.count('round_limit'),1);self.assertEqual(self.db.world_castle_reservations.count_documents({}),1)
    def test_additional_team_gets_no_land_or_supply(self):
        a=self.company();team=self.domain.create_team(a,'LateTeam')['_id'];self.host('enroll_team',team_id=team,homeland_frontier_id=self.homes[0]['frontier_id'])
        self.command(a,'enroll');self.assertEqual(self.db.world_teams.find_one({'_id':team})['supply'],0)
        self.assertEqual(self.db.world_castles.count_documents({'owner_team_id':team}),0)
        self.assertEqual(self.db.companies.find_one({'_id':a})['location'],'camp:'+team)
    def test_hostile_attack_requires_war_and_approval(self):
        a,b=self.players
        self.command(a,'station',castle_id=self.homes[0]['frontier_id']);self.command(b,'station',castle_id=self.homes[1]['frontier_id']);self.finish_round()
        war=self.command(a,'war_propose',opponent_team_id=self.teams[1],target_ids=[self.homes[1]['frontier_id']],objective_area_id=None)['war']
        self.command(b,'war_approve',war_id=war['id'])
        offer=self.command(b,'defense_offer',castle_id=self.homes[1]['frontier_id'],bracket='scout')['defense']
        run=self.command(a,'attack',origin_id=self.homes[0]['frontier_id'],target_id=self.homes[1]['frontier_id'],bracket='scout',war_id=war['id'])['battle']['id']
        self.command(a,'battle_ready',run_id=run,ready=True);self.command(a,'battle_approve',run_id=run)
        # Approved war and standing captain-authorized army permit offline defense.
        self.phase();self.phase();self.phase()
        self.command(b,'defense_withdraw',assignment_id=offer['id'])
        self.assertEqual(self.db.world_defenses.find_one({'_id':offer['id']})['status'],'withdraw_pending')
        desc=self.load(run);self.assertEqual(desc['required_humans'],[a]);self.assertTrue(desc['worker_sides'])
        self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],self.evidence(desc))
        self.assertEqual(self.db.world_defenses.find_one({'_id':offer['id']})['status'],'withdrawn')
        self.assertEqual(self.db.world_castles.find_one({'_id':self.homes[1]['frontier_id']})['owner_team_id'],self.teams[0])
    def test_skirmish_conversion_fresh_consent_and_both_confirmations(self):
        a,b=self.players;slots=[dict(side=i,kind='open',account_id='',ai_faction='',ai_leader='') for i in range(1,5)]
        slots[3].update(kind='ai',ai_faction='Loyalists',ai_leader='Lieutenant')
        plan=self.domain.directory_publish_plan(a,self.teams[0],self.teams[1],'isars-cross',DEFAULT_SETTINGS,slots)
        slots[2].update(kind='ai',ai_faction='Rebels',ai_leader='Elvish Captain')
        plan=self.domain.directory_edit_plan(b,plan['id'],plan['revision'],'isars-cross',DEFAULT_SETTINGS,slots)
        run=self.command(a,'skirmish_create',plan_id=plan['id'])['battle']['id']
        self.assertEqual(self.db.game_runs.find_one({'_id':plan['id']})['state'],'cancelled')
        for actor,team in zip(self.players,self.teams):
            self.command(actor,'battle_join',run_id=run,team_id=team);self.command(actor,'battle_ready',run_id=run,ready=True)
        # Second join correctly invalidated the first owner's prior readiness.
        self.command(a,'battle_ready',run_id=run,ready=True)
        for actor in self.players:self.command(actor,'battle_approve',run_id=run)
        desc=self.load(run);self.assertEqual(len(desc['worker_sides']),2)
        self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],self.evidence(desc))
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'awaiting_confirmation');self.assertEqual(self.db.world_settlements.count_documents({}),0)
        self.command(a,'battle_confirm',run_id=run);self.assertEqual(self.db.world_settlements.count_documents({}),0)
        self.command(b,'battle_confirm',run_id=run);self.assertEqual(self.db.world_settlements.count_documents({}),1)
        self.assertEqual([t['rating'] for t in self.db.teams.find({})],[1000,1000])

    def test_old_training_same_hero_locked_other_hero_allowed(self):
        from alliance.rules import MISSIONS
        a=self.players[0];offer=self.command(a,'defense_offer',castle_id=self.homes[0]['capital_id'],bracket='scout')['defense']
        self.code('busy',lambda:self.domain.progression_start(a,MISSIONS[0],self.hero,self.form))
        other=next(f for f in self.catalog['forms'] if f['hero_id']!=self.hero and f['native_level']==1)
        self.seed(a,hero=other['hero_id'],forms=[other['id']])
        run=self.domain.progression_start(a,MISSIONS[0],other['hero_id'],other['id'])
        self.assertIsNotNone(run['run'])
        self.assertEqual(self.db.world_defenses.find_one({'_id':offer['id']})['status'],'active')

    def test_old_training_blocks_reverse_same_hero_pledge(self):
        from alliance.rules import MISSIONS
        a=self.players[0];self.domain.progression_start(a,MISSIONS[0],self.hero,self.form)
        self.code('busy',lambda:self.command(a,'defense_offer',castle_id=self.homes[0]['capital_id'],bracket='scout'))

    def test_outgrown_permission_requires_review_without_substitution(self):
        a=self.players[0];offer=self.command(a,'defense_offer',castle_id=self.homes[0]['capital_id'],bracket='scout')['defense']
        soldier=offer['selection']['soldier_ids'][0]
        self.db.company_soldiers.update_one({'_id':soldier},{'$set':{'unit_type':'Swordsman'},'$inc':{'revision':1}})
        row=self.domain.world_query(a,'snapshot',{})['data']['defenses'][0]
        self.assertEqual(row['status'],'needs_review');self.assertEqual(row['bracket'],'scout')
        saved=self.db.world_defenses.find_one({'_id':offer['id']});self.assertEqual(saved['status'],'active');self.assertEqual(saved['selection'],offer['selection'])

    def test_worker_restart_keeps_generation_and_requires_same_account_reload(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        self.domain.world_worker_pause(run,'test_worker_123',desc['generation'])
        self.db.world_contracts.update_one({'_id':run},{'$set':{'lease_until':_now()-timedelta(seconds=1)}})
        resumed=self.domain.world_worker_acquire('new_worker_123')
        self.assertEqual(resumed['generation'],desc['generation']);self.assertEqual(resumed['descriptor_sha256'],desc['descriptor_sha256']);self.assertEqual(resumed['state'],'paused')
        self.code('forbidden',lambda:self.domain.world_human_join(self.players[1],run))
        self.domain.world_worker_loaded(run,'new_worker_123',desc['generation'],'a'*64)
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'paused')
        self.domain.world_human_loaded(self.players[0],run,desc['generation'],'a'*64)
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'running')
        self.code('forbidden',lambda:self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],self.evidence(desc)))
        self.domain.world_worker_finish(run,'new_worker_123',desc['generation'],self.evidence(desc))

    def test_complete_native_proof_after_human_disconnect_still_settles(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        self.domain.world_human_disconnect(self.players[0],run,desc['generation'])
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'paused')
        result=self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],self.evidence(desc))
        self.assertEqual(result['captured_castle_id'],self.neutral()['_id'])

    def test_history_and_replay_authorization(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],self.evidence(desc))
        self.assertEqual(self.domain.world_replay_authorize(self.players[0],run)['replay_sha256'],'b'*64)
        self.code('forbidden',lambda:self.domain.world_replay_authorize(self.players[1],run))
        recruit=self.player(True)
        self.db.teams.update_one({'_id':self.teams[0]},{'$push':{'members':{'account_id':recruit,'joined_at':_now()}}})
        self.assertEqual(self.domain.world_replay_authorize(recruit,run)['run_id'],run)
        self.db.teams.update_one({'_id':self.teams[0]},{'$pull':{'members':{'account_id':recruit}}})
        self.code('forbidden',lambda:self.domain.world_replay_authorize(recruit,run))
        items=self.domain.world_query(self.players[0],'history',{'limit':1})['data']['items']
        self.assertEqual(items[0]['id'],run);self.assertNotIn('units',items[0]['armies'][0])

    def test_war_boundaries_no_unplayed_capture_or_early_defender_win(self):
        a,b=self.players;area=self.db.world_castles.find_one({'_id':self.homes[1]['capital_id']})['area_id']
        war=self.command(a,'war_propose',opponent_team_id=self.teams[1],target_ids=[self.homes[1]['capital_id']],objective_area_id=area)['war']
        self.command(b,'war_approve',war_id=war['id']);before=list(self.db.world_castles.find({}))
        self.finish_round();self.assertEqual(self.db.world_wars.find_one({'_id':war['id']})['state'],'active')
        self.finish_round();self.finish_round();saved=self.db.world_wars.find_one({'_id':war['id']})
        self.assertEqual(saved['state'],'completed');self.assertEqual(saved['result']['winner_team_id'],self.teams[1])
        self.assertEqual(saved['result']['title'],'World War Victor')
        title=self.db.world_teams.find_one({'_id':self.teams[1]})['last_title'];self.assertEqual(title['war_id'],war['id'])
        self.finish_round();self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[1]})['last_title'],title)
        self.assertEqual(list(self.db.world_castles.find({})),before);self.assertTrue(all(t['experience']==0 for t in self.db.teams.find({})))

    def test_governor_proposes_but_captain_spends(self):
        a=self.players[0];member=self.player(True);castle=self.homes[0]['capital_id']
        self.db.teams.update_one({'_id':self.teams[0]},{'$push':{'members':{'account_id':member,'joined_at':_now()}}})
        self.command(a,'governor',castle_id=castle,account_id=member)
        self.command(member,'roadworks_propose',castle_id=castle)
        self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[0]})['supply'],20)
        self.code('forbidden',lambda:self.command(member,'roadworks',castle_id=castle))
        self.command(a,'roadworks',castle_id=castle)
        self.assertIsNone(self.db.world_castles.find_one({'_id':castle})['roadworks_proposal'])

    def test_current_captain_must_renew_old_approval(self):
        run=self.attack_neutral();old=self.players[0];new=self.player(True)
        self.db.teams.update_one({'_id':self.teams[0]},{'$push':{'members':{'account_id':new,'joined_at':_now()}},'$set':{'captain_id':new}})
        self.phase();self.code('consent_required',self.phase)
        self.command(new,'battle_approve',run_id=run);self.phase()
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'queued')

    def test_financial_schema_rejects_invalid_treasury_and_missing_permission(self):
        from pymongo.errors import WriteError
        with self.assertRaises(WriteError):self.db.world_teams.update_one({'_id':self.teams[0]},{'$set':{'supply':41}})
        with self.assertRaises(WriteError):self.db.world_defenses.insert_one({'_id':str(uuid4())})
        self.assertEqual(self.db.world_teams.find_one({'_id':self.teams[0]})['supply'],20)

    def test_human_only_defense_needs_current_captain_approval(self):
        a,b=self.players
        self.command(a,'station',castle_id=self.homes[0]['frontier_id']);self.command(b,'station',castle_id=self.homes[1]['frontier_id']);self.finish_round()
        war=self.command(a,'war_propose',opponent_team_id=self.teams[1],target_ids=[self.homes[1]['frontier_id']],objective_area_id=None)['war']
        self.command(b,'war_approve',war_id=war['id'])
        run=self.command(a,'attack',origin_id=self.homes[0]['frontier_id'],target_id=self.homes[1]['frontier_id'],bracket='scout',war_id=war['id'])['battle']['id']
        self.command(b,'battle_join',run_id=run,team_id=self.teams[1])
        for player in self.players:self.command(player,'battle_ready',run_id=run,ready=True)
        self.command(a,'battle_approve',run_id=run);self.phase()
        self.code('consent_required',self.phase)
        self.command(b,'battle_approve',run_id=run);self.phase()
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'queued')

    def test_settled_world_wound_blocks_legacy_training(self):
        from alliance.rules import MISSIONS
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        proof=self.evidence(desc,dead=desc['units'][0]['instance_id'])
        self.domain.world_worker_finish(run,'test_worker_123',desc['generation'],proof)
        self.code('wounded',lambda:self.domain.progression_start(self.players[0],MISSIONS[0],self.hero,self.form))
        self.assertEqual(self.db.company_asset_locks.count_documents({}),0)

    def test_uncommitted_reserve_management_while_defense_pledged(self):
        a=self.players[0];offer=self.command(a,'defense_offer',castle_id=self.homes[0]['capital_id'],bracket='scout')['defense']
        selected=offer['selection']['soldier_ids'];reserve=self.db.company_soldiers.find_one({'owner_id':a,'_id':{'$nin':selected}})
        self.command(a,'company_recruit',unit_type='Mage')
        self.command(a,'company_preferences',soldier_id=reserve['_id'],preferences={})
        self.command(a,'company_retire',soldier_id=reserve['_id'])
        self.assertTrue(self.db.company_soldiers.find_one({'_id':reserve['_id']})['retired'])
        self.code('busy',lambda:self.command(a,'company_preferences',soldier_id=selected[0],preferences={}))
        self.code('busy',lambda:self.command(a,'company_retire',soldier_id=selected[0]))
        self.assertEqual(self.db.world_defenses.find_one({'_id':offer['id']})['selection'],offer['selection'])

    def test_team_change_reenrollment_preserves_history_and_grants_nothing(self):
        a,b=self.players;offer=self.command(a,'defense_offer',castle_id=self.homes[0]['capital_id'],bracket='scout')['defense']
        self.domain.leave_team(a);self.domain.request_join(a,self.teams[1]);self.domain.approve_member(b,self.teams[1],a)
        self.assertFalse(self.domain.world_query(a,'snapshot',{})['data']['enrolled'])
        self.code('busy',lambda:self.command(a,'enroll'))
        self.command(a,'defense_withdraw',assignment_id=offer['id'])
        before=list(self.db.world_castles.find({}));supplies=[x['supply'] for x in self.db.world_teams.find({})]
        result=self.command(a,'enroll')
        self.assertTrue(result['enrolled']);self.assertEqual(self.db.companies.find_one({'_id':a})['location'],self.homes[1]['capital_id'])
        self.assertEqual(self.db.world_enrollments.find_one({'_id':a})['homeland_frontier_id'],self.homes[1]['frontier_id'])
        self.assertEqual(self.db.world_enrollment_history.find_one({'owner_id':a})['team_id'],self.teams[0])
        self.assertEqual(before,list(self.db.world_castles.find({})));self.assertEqual(supplies,[x['supply'] for x in self.db.world_teams.find({})])

    def test_reenrollment_waits_after_current_round_order(self):
        a,b=self.players;self.command(a,'station',castle_id=self.homes[0]['frontier_id']);self.phase()
        self.domain.leave_team(a);self.domain.request_join(a,self.teams[1]);self.domain.approve_member(b,self.teams[1],a)
        self.code('round_limit',lambda:self.command(a,'enroll'))
        self.finish_round();self.command(a,'enroll')
        self.assertEqual(self.db.world_enrollments.find_one({'_id':a})['team_id'],self.teams[1])

    def test_one_relocation_then_one_deployment_engagement(self):
        a=self.players[0];recruit=self.company();self.domain.request_join(recruit,self.teams[0]);self.domain.approve_member(a,self.teams[0],recruit);self.command(recruit,'enroll')
        for actor in (a,recruit):self.command(actor,'station',castle_id=self.homes[0]['frontier_id'])
        self.code('round_limit',lambda:self.command(a,'attack',origin_id=self.homes[0]['capital_id'],target_id=self.neutral()['_id'],bracket='scout'))
        self.phase()
        run=self.command(a,'attack',origin_id=self.homes[0]['frontier_id'],target_id=self.neutral()['_id'],bracket='scout')['battle']['id']
        self.command(recruit,'battle_join',run_id=run,team_id=self.teams[0])
        for actor in (a,recruit):self.command(actor,'battle_ready',run_id=run,ready=True)
        self.command(a,'battle_approve',run_id=run);self.phase()
        frozen=self.db.world_contracts.find_one({'_id':run});self.assertEqual(frozen['origin_id'],self.homes[0]['frontier_id'])
        self.assertEqual(frozen['state'],'queued');self.assertEqual(self.db.world_round_participation.count_documents({}),2)
        self.assertEqual(self.db.world_orders.count_documents({'kind':'move','state':'applied'}),2)

    def test_published_attack_prevents_relocation_and_checks_frozen_origin(self):
        a=self.players[0];run=self.attack_neutral()
        self.code('round_limit',lambda:self.command(a,'station',castle_id=self.homes[0]['frontier_id']))
        self.phase();self.db.companies.update_one({'_id':a},{'$set':{'location':self.homes[0]['frontier_id']}})
        self.code('wrong_station',self.phase)
        self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'draft')

    def test_withdrawn_history_cannot_hide_active_standing_permission(self):
        a=self.players[0];castle=self.homes[0]['capital_id'];old=self.command(a,'defense_offer',castle_id=castle,bracket='scout')['defense']
        self.command(a,'defense_withdraw',assignment_id=old['id']);historical=self.db.world_defenses.find_one({'_id':old['id']})
        for i in range(36):
            row=deepcopy(historical);row['_id']='00000000-0000-4000-8000-'+str(i).zfill(12);self.db.world_defenses.insert_one(row)
        active=self.command(a,'defense_offer',castle_id=castle,bracket='scout')['defense']
        rows=self.domain.world_query(a,'snapshot',{})['data']['defenses']
        self.assertEqual([r['id'] for r in rows],[active['id']]);self.assertEqual(self.db.world_defenses.count_documents({'status':'withdrawn'}),37)

    def test_paused_unstarted_preparation_expires_on_heartbeat(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.domain.world_worker_acquire('test_worker_123')
        self.domain.world_human_disconnect(self.players[0],run,desc['generation'])
        self.db.world_contracts.update_one({'_id':run},{'$set':{'prepare_until':_now()-timedelta(seconds=1)}})
        result=self.domain.world_worker_lease(run,'test_worker_123',desc['generation'])
        self.assertEqual(result['state'],'cancelled');self.assertEqual(self.db.network_battle_reservations.count_documents({}),0)
        self.assertIsNone(self.neutral()['owner_team_id'])

    def test_paused_started_battle_does_not_expire_on_heartbeat(self):
        run=self.attack_neutral();self.phase();self.phase();self.phase();desc=self.load(run)
        self.domain.world_human_disconnect(self.players[0],run,desc['generation'])
        self.db.world_contracts.update_one({'_id':run},{'$set':{'prepare_until':_now()-timedelta(seconds=1)}})
        self.assertEqual(self.domain.world_worker_lease(run,'test_worker_123',desc['generation'])['state'],'paused')
        self.assertEqual(self.db.network_battle_reservations.count_documents({}),1)

    def test_join_affordance_requires_eligible_new_company(self):
        a=self.players[0];run=self.attack_neutral()
        self.assertFalse(self.domain.world_query(a,'battle',{'run_id':run})['data']['can_join'])
        member=self.company();self.domain.request_join(member,self.teams[0]);self.domain.approve_member(a,self.teams[0],member)
        self.assertFalse(self.domain.world_query(member,'battle',{'run_id':run})['data']['can_join'])
        self.command(member,'enroll')
        self.assertTrue(self.domain.world_query(member,'battle',{'run_id':run})['data']['can_join'])
        self.command(member,'battle_join',run_id=run,team_id=self.teams[0])
        self.assertFalse(self.domain.world_query(member,'battle',{'run_id':run})['data']['can_join'])

    def test_paused_unstarted_expiry_at_acquire_and_load(self):
        a=self.players[0]
        for trigger in ('acquire','load'):
            with self.subTest(trigger=trigger):
                run=self.command(a,'company_expedition',mission_id='company_border_patrol')['battle']['id']
                desc=self.domain.world_worker_acquire('test_worker_123')
                self.domain.world_human_disconnect(a,run,desc['generation'])
                self.db.world_contracts.update_one({'_id':run},{'$set':{'prepare_until':_now()-timedelta(seconds=1)}})
                if trigger=='acquire':self.assertIsNone(self.domain.world_worker_acquire('other_worker_123'))
                else:self.assertEqual(self.domain.world_human_loaded(a,run,desc['generation'],'a'*64)['state'],'cancelled')
                self.assertEqual(self.db.world_contracts.find_one({'_id':run})['state'],'cancelled')
                self.assertEqual(self.db.network_battle_reservations.count_documents({}),0)
