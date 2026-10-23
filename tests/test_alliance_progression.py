"""Native progression and operator controls on disposable MongoDB only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from datetime import timedelta
import os
import re
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_alliance_domain as fixtures
from alliance import rules
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService, DomainError
from alliance.web import create_app


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set.')
class ProgressionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.MongoDomainTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.MongoDomainTests.tearDownClass.__func__)
    setUp = fixtures.MongoDomainTests.setUp
    tearDown = fixtures.MongoDomainTests.tearDown
    player = fixtures.MongoDomainTests.player
    admin = fixtures.MongoDomainTests.admin
    teams = fixtures.MongoDomainTests.teams
    battle = fixtures.MongoDomainTests.battle
    assertDomain = fixtures.MongoDomainTests.assertDomain

    def finish(self, actor, run, **changes):
        args = dict(run_id=run['id'], mission_id=run['mission_id'], mission_version=run['mission_version'],
                    nonce=run['nonce'], outcome='win', replay_sha256='a' * 64,
                    format='alliance-native-campaign-result-v1')
        args.update(changes)
        return self.service.progression_finish(actor, **args)

    def snapshot(self):
        return {name: list(self.db[name].find({}).sort('_id', 1)) for name in
                ('accounts', 'teams', 'areas', 'game_runs', 'settlements', 'admin_audit')}

    def test_catalog_read_only_unlock_and_private_projection(self):
        actor = self.player()
        before = self.snapshot()
        result = self.service.progression_catalog(actor)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([m['unlocked'] for m in result['missions']], [True, False, False])
        self.assertIsNone(result['active_run'])
        self.assertNotIn('password_hash', json.dumps(result))
        self.assertEqual(set(result['profile']), {'id','username','starter_id','unit_type','level',
                                                'experience','total_experience','advancement_choices'})

    def test_bound_run_completion_and_duplicate_reward(self):
        actor = self.player()
        run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
        self.assertRegex(run['nonce'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.service.progression_catalog(actor)['active_run'], run)
        self.assertEqual(self.service.progression_status(actor, run['id'])['run'], run)
        self.assertEqual(self.service.progression_history(actor)['runs'][0]['nonce'], '')
        result = self.finish(actor, run)
        self.assertEqual(result['experience_awarded'], 20)
        self.assertEqual(result['profile']['experience'], 20)
        self.assertEqual(result['run']['state'], 'completed')
        self.assertEqual(result['run']['nonce'], '')
        again = self.finish(actor, run)
        self.assertEqual(again, result)
        self.assertEqual(self.db.settlements.count_documents({}), 1)
        self.assertEqual(self.service.progression_catalog(actor)['missions'][1]['unlocked'], True)
        self.assertDomain('result_conflict', self.finish, actor, run, replay_sha256='b'*64)
        self.assertDomain('result_conflict', self.finish, actor, run, outcome='loss')

    def test_wrong_owner_nonce_version_mission_and_result_cannot_award(self):
        actor, other = self.player(), self.player()
        run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
        before = self.snapshot()
        self.assertDomain('forbidden', self.finish, other, run)
        self.assertDomain('forbidden', self.service.progression_status, other, run['id'])
        self.assertDomain('forbidden', self.service.progression_cancel, other, run['id'])
        for field, value in [('nonce','b'*64), ('mission_version','wrong'), ('mission_id',rules.MISSIONS[1]),
                             ('format','practice'), ('outcome','draw'), ('replay_sha256','bad')]:
            self.assertDomain('invalid_result', self.finish, actor, run, **{field:value})
        self.assertEqual(self.snapshot(), before)

    def test_legacy_or_practice_run_has_no_native_completion_binding(self):
        actor = self.player()
        run = self.service.start_campaign(actor, rules.MISSIONS[0])
        projected = self.service.progression_status(actor, run['_id'])['run']
        self.assertEqual(projected['nonce'], '')
        self.assertDomain('invalid_result', self.finish, actor, projected,
                          nonce='a'*64, mission_version=rules.MISSION_VERSION)
        self.assertEqual(self.db.settlements.count_documents({}), 0)

    def test_loss_and_cancel_release_without_progress(self):
        actor = self.player()
        run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
        lost = self.finish(actor, run, outcome='loss')
        self.assertEqual(lost['profile']['total_experience'], 0)
        self.assertFalse(self.service.progression_catalog(actor)['missions'][1]['unlocked'])
        fresh = self.service.progression_start(actor, rules.MISSIONS[0])['run']
        cancelled = self.service.progression_cancel(actor, fresh['id'])
        self.assertEqual(cancelled['run']['state'], 'cancelled')
        self.assertEqual(self.service.progression_cancel(actor, fresh['id']), cancelled)
        self.assertDomain('invalid_state', self.finish, actor, fresh)
        self.assertIsNone(self.service.get_account(actor)['active_run_id'])

    def test_finish_is_atomic_and_races_award_once(self):
        actor = self.player()
        run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
        before = self.snapshot()
        with patch.object(self.service, '_record_settlement', side_effect=RuntimeError('fixture rollback')):
            with self.assertRaises(RuntimeError): self.finish(actor, run)
        self.assertEqual(self.snapshot(), before)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.finish(actor, run), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.service.get_account(actor)['leader']['total_experience'], 20)

    def test_history_bounded_and_no_nonce_or_other_player(self):
        actor, other = self.player(), self.player()
        for _ in range(22):
            run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
            self.service.progression_cancel(actor, run['id'])
        self.service.progression_start(other, rules.MISSIONS[0])
        history = self.service.progression_history(actor)
        self.assertEqual(len(history['runs']), 20)
        self.assertTrue(history['has_more'])
        self.assertTrue(all(row['account_id'] == actor and row['nonce'] == '' for row in history['runs']))

    def test_advancement_preserves_identity_and_requires_earned_choice(self):
        actor = self.player()
        for _ in range(3):
            run = self.service.progression_start(actor, rules.MISSIONS[0])['run']
            self.finish(actor, run)
        self.assertDomain('advancement_required', self.service.progression_start, actor, rules.MISSIONS[1])
        result = self.service.progression_advance(actor, 'Swordsman')['profile']
        self.assertEqual((result['id'], result['level'], result['experience'], result['total_experience']), (actor,2,18,60))
        self.assertDomain('invalid_advancement', self.service.progression_advance, actor, 'Royal Guard')

    def test_captain_orders_private_bounded_and_transfer(self):
        teams, members = self.teams()
        self.assertDomain('forbidden', self.service.post_team_order, members[0][1], teams[0], 'Go north')
        self.assertDomain('forbidden', self.service.team_orders, members[1][0], teams[0])
        for number in range(52):
            self.service.post_team_order(members[0][0], teams[0], f'Order {number}')
        response = self.service.team_orders(members[0][1], teams[0])
        orders = response['orders']
        self.assertEqual(len(orders), 10)
        self.assertTrue(response['has_more'])
        self.assertEqual(len(self.db.teams.find_one({'_id': teams[0]})['orders']), 50)
        self.assertEqual(orders[0]['text'], 'Order 51')
        self.assertEqual(orders[-1]['text'], 'Order 42')
        for _ in range(10):
            self.service.post_team_order(members[0][0], teams[0], '\U0001f600'*125)
        bounded=self.service.team_orders(members[0][1], teams[0])
        self.assertLess(len(json.dumps(bounded,ensure_ascii=True).encode()),32768)
        for text in ('\U0001f600'*126, 'abc\ud800', 'abc\x00'):
            self.assertDomain('invalid_input',self.service.post_team_order,members[0][0],teams[0],text)
        self.service.transfer_captain(members[0][0], teams[0], members[0][1])
        self.assertDomain('forbidden', self.service.post_team_order, members[0][0], teams[0], 'Old captain')
        self.service.post_team_order(members[0][1], teams[0], 'New captain')
        self.service.leave_team(members[0][0])
        self.assertDomain('forbidden', self.service.team_orders, members[0][0], teams[0])

    def test_area_edit_maps_disabled_stale_and_active_battle_guards(self):
        admin = self.admin()
        area = self.service.admin_create_area(admin, 'Test Area')
        updated = self.service.admin_edit_area(admin, area['_id'], 'Renamed Area', False, ['isars-cross'], 'Testing availability', 0)
        self.assertFalse(updated['enabled'])
        self.assertDomain('stale_area', self.service.admin_edit_area, admin, area['_id'], 'Renamed Area', True, ['isars-cross'], 'Old form', 0)
        self.assertDomain('not_found', self.service.create_team, self.player(), 'Disabled Team', area['_id'])
        for maps in ([], ['unknown'], ['isars-cross','isars-cross'], [{}]):
            self.assertDomain('invalid_input', self.service.admin_edit_area, admin, area['_id'], 'Test Area', True, maps, 'Invalid maps', 1)
        self.service.admin_edit_area(admin, area['_id'], 'Renamed Area', True, ['isars-cross'], 'Restore availability', 1)
        run, teams, members = self.battle()
        revision = self.db.areas.find_one({'_id':'area-1'}).get('revision',0)
        self.assertDomain('busy', self.service.admin_edit_area, admin, 'area-1', 'Area 1', False, ['isars-cross'], 'Active battle', revision)

    def test_correction_bounded_audited_stale_no_type_or_team_changes(self):
        admin, actor = self.admin(), self.player()
        team = self.service.create_team(actor, 'Correction Team')
        account = self.service.get_account(actor)
        result = self.service.admin_correct_experience(admin, actor, 50, 'Verified missing award', account['revision'])
        self.assertEqual((result['unit_type'],result['experience'],result['total_experience']), ('Spearman',50,50))
        self.assertEqual(self.service.directory_my_team(actor)['id'], team['_id'])
        self.assertEqual(self.db.admin_audit.count_documents({'action':'correct_leader_experience'}), 1)
        self.assertDomain('stale_account', self.service.admin_correct_experience, admin, actor, 1, 'Old form', account['revision'])
        self.service.progression_advance(actor, 'Swordsman')
        revision = self.service.get_account(actor)['revision']
        self.assertDomain('invalid_correction', self.service.admin_correct_experience, admin, actor, -9, 'Spent experience', revision)
        for delta in (0,1001,-1001,True,1.5):
            self.assertDomain('invalid_input', self.service.admin_correct_experience, admin, actor, delta, 'Invalid correction', revision)

    def test_http_contract_auth_csrf_projection_and_templates(self):
        bootstrap_auth_schema(self.db)
        password='Fixture-only-password-123'
        hashed=hash_password(password)
        actor=self.service.register('NativePlayer',hashed)['_id']
        admin=self.service.bootstrap_admin('Operator',hashed)['_id']
        settings=SimpleNamespace(host='127.0.0.1',port=18765,secret_key=uuid4().hex,bridge_secret=uuid4().hex)
        app=create_app(settings,self.db);app.config['TESTING']=True;client=app.test_client()
        auth=AuthService(self.db)
        token=auth.authenticate('NativePlayer',password,'player')['token']
        headers={'Authorization':'Bearer '+settings.bridge_secret,'X-Player-Token':token}
        url='/internal/v1/progression/'
        self.assertEqual(client.post(url+'catalog',json={}).status_code,401)
        self.assertEqual(client.post(url+'catalog?extra=1',json={},headers=headers).status_code,400)
        self.assertEqual(client.post(url+'catalog',json={'xp':20},headers=headers).status_code,400)
        result=client.post(url+'start',json={'mission_id':rules.MISSIONS[0]},headers=headers)
        self.assertEqual(result.status_code,200)
        run=result.json['run'];self.assertTrue(run['nonce'])
        self.assertNotIn(run['nonce'],client.post(url+'history',json={},headers=headers).get_data(as_text=True))
        csrf=re.search(r'name="csrf_token" value="([^"]+)"',client.get('/login').get_data(as_text=True)).group(1)
        self.assertEqual(client.post('/login',data={'csrf_token':csrf,'username':'Operator','password':password}).status_code,302)
        for path in ('/areas','/areas/area-1/edit','/accounts/'+actor+'/experience'):
            response=client.get(path)
            self.assertEqual(response.status_code,200, response.get_data(as_text=True))
            self.assertNotIn(hashed,response.get_data(as_text=True))
            self.assertNotIn(run['nonce'],response.get_data(as_text=True))
        self.assertEqual(client.post('/areas/area-1/edit',data={}).status_code,400)
        self.assertTrue(client.get('/internal/v1/health',headers={'Authorization':'Bearer '+settings.bridge_secret}).json['campaign_content_ready'])

    def test_admin_forms_apply_once_and_reject_stale_or_extra_fields(self):
        bootstrap_auth_schema(self.db)
        password='Fixture-only-admin-password-123';hashed=hash_password(password)
        admin=self.service.bootstrap_admin('Operator',hashed)['_id'];actor=self.player()
        app=create_app(SimpleNamespace(host='127.0.0.1',port=18765,secret_key=uuid4().hex,bridge_secret=uuid4().hex),self.db)
        app.config['TESTING']=True;client=app.test_client()
        def token(path):
            return re.search(r'name="csrf_token" value="([^"]+)"',client.get(path).get_data(as_text=True)).group(1)
        client.post('/login',data={'csrf_token':token('/login'),'username':'Operator','password':password})
        path='/accounts/'+actor+'/experience'
        form={'csrf_token':token(path),'revision':str(self.service.get_account(actor)['revision']),
              'delta':'42','reason':'Verified omitted mission awards'}
        before=self.snapshot()
        self.assertEqual(client.post(path,data={**form,'unit_type':'Royal Guard'}).status_code,400)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(client.post(path,data=form).status_code,302)
        self.assertEqual(self.service.get_account(actor)['leader']['experience'],42)
        self.assertEqual(client.post(path,data=form).status_code,409)
        path='/areas/area-1/edit'
        form={'csrf_token':token(path),'revision':str(self.db.areas.find_one({'_id':'area-1'}).get('revision',0)),
              'name':'Edited Area','enabled':'false','approved_maps':'isars-cross','reason':'Approved scheduled closure'}
        self.assertEqual(client.post(path,data=form).status_code,302)
        self.assertEqual(client.post(path,data=form).status_code,409)
        self.assertFalse(self.db.areas.find_one({'_id':'area-1'})['enabled'])
        self.assertEqual(self.db.admin_audit.count_documents({'actor_id':admin,
                         'action':{'$in':['correct_leader_experience','edit_area']}}),2)

    def shared(self, start=True):
        run, teams, members = self.battle(start=False)
        generation = str(uuid4())
        self.service.shared_prepare(members[0][0], run['_id'], generation)
        if start:
            self.service.shared_start(run['_id'], generation, sum(members, []), 'f'*64)
        return run['_id'], teams, members, generation

    def reports(self, run, teams, members, generation, *, disputed=False, draw=False):
        for number, actor in enumerate(sum(members, [])):
            winner = None if draw else teams[1 if disputed and number == 0 else 0]
            review = self.service.shared_report_result(actor, run, generation, winner, draw, str(number)*64)
        return review

    def test_room_preparation_no_reservations_and_exact_admission(self):
        run, teams, members, generation = self.shared(start=False)
        for side, actor in zip((1,4,2,3), sum(members, [])):
            entry = self.service.shared_admission(actor, run, generation)
            self.assertEqual(entry['assigned_side'], side)
            self.assertEqual(entry['room_state'], 'preparing')
            self.assertIsNone(self.service.get_account(actor)['active_run_id'])
        self.assertDomain('forbidden', self.service.shared_admission, self.player(), run, generation)
        self.assertDomain('room_conflict', self.service.shared_prepare, members[0][0], run, str(uuid4()))
        self.assertDomain('invalid_input', self.service.shared_start, run, generation, members[0], 'f'*64)
        self.assertEqual(self.service.get_run(run)['state'], 'draft')

    def test_room_start_atomic_idempotent_and_generation_fenced(self):
        run, teams, members, generation = self.shared(start=False)
        before = self.snapshot()
        with patch.object(self.service, '_reserve_account', side_effect=RuntimeError('fixture start rollback')):
            with self.assertRaises(RuntimeError): self.service.shared_start(run,generation,sum(members,[]),'f'*64)
        self.assertEqual(self.snapshot(), before)
        result = self.service.shared_start(run,generation,sum(members,[]),'f'*64)
        self.assertEqual(result, self.service.shared_start(run,generation,sum(members,[]),'f'*64))
        for actor in sum(members, []): self.assertEqual(self.service.get_account(actor)['active_run_id'],run)
        self.assertDomain('room_conflict', self.service.shared_start, run,str(uuid4()),sum(members,[]),'f'*64)
        self.assertDomain('room_conflict', self.service.shared_start, run,generation,sum(members,[]),'a'*64)
        self.assertEqual(self.service.shared_admission(members[1][1],run,generation)['assigned_side'],3)

    def test_room_rechecks_withdrawal_and_expiry_never_releases_running(self):
        run, teams, members, generation = self.shared(start=False)
        self.service.set_ready(members[1][1],run,False)
        self.assertDomain('not_ready', self.service.shared_start, run,generation,sum(members,[]),'f'*64)
        self.service.set_ready(members[1][1],run,True)
        document=self.service.get_run(run)
        self.db.game_runs.update_one({'_id':run},{'$set':{'shared_room.expires_at':document['created_at']-timedelta(seconds=1)}})
        self.assertDomain('room_expired',self.service.shared_start,run,generation,sum(members,[]),'f'*64)
        self.assertDomain('room_expired',self.service.shared_prepare,members[0][0],run,generation)
        fresh=str(uuid4());self.service.shared_prepare(members[0][0],run,fresh)
        self.service.shared_start(run,fresh,sum(members,[]),'f'*64)
        self.db.game_runs.update_one({'_id':run},{'$set':{'shared_room.expires_at':document['created_at']-timedelta(days=1)}})
        self.assertEqual(self.service.shared_admission(members[0][0],run,fresh)['room_state'],'running')
        self.assertEqual(self.service.get_account(members[0][0])['active_run_id'],run)

    def test_room_start_race_rechecks_departed_member_before_reserving(self):
        run,teams,members,generation=self.shared(start=False)
        read,resume=threading.Event(),threading.Event();get_run=self.service._run
        def hold_run(*args,**kwargs):
            result=get_run(*args,**kwargs)
            if not read.is_set():
                read.set()
                if not resume.wait(10):raise RuntimeError('Race fixture did not resume')
            return result
        with patch.object(self.service,'_run',side_effect=hold_run),ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(self.service.shared_start,run,generation,sum(members,[]),'f'*64)
            try:
                self.assertTrue(read.wait(5));AllianceService(self.db).leave_team(members[1][1])
            finally:resume.set()
            with self.assertRaises(DomainError):pending.result(timeout=10)
        self.assertEqual(self.service.get_run(run)['state'],'draft')
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)
        self.assertEqual(self.db.teams.count_documents({'active_run_id':{'$ne':None}}),0)

    def test_room_abort_preserves_draft_but_running_abort_releases_without_xp(self):
        run,teams,members,generation=self.shared(start=False)
        result=self.service.shared_cancel(run,generation,'Preparation abandoned')
        self.assertEqual(result['state'],'draft')
        self.assertDomain('room_expired',self.service.shared_prepare,members[0][0],run,generation)
        new=str(uuid4());self.service.shared_prepare(members[0][0],run,new)
        self.service.shared_start(run,new,sum(members,[]),'f'*64)
        self.assertDomain('room_conflict',self.service.shared_cancel,run,generation,'Old room cannot cancel')
        self.service.shared_cancel(run,new,'Players abandoned game')
        self.assertEqual(self.service.get_run(run)['state'],'cancelled')
        for actor in sum(members,[]):
            account=self.service.get_account(actor)
            self.assertIsNone(account['active_run_id']);self.assertEqual(account['leader']['total_experience'],0)
        self.assertEqual(self.db.settlements.count_documents({}),0)

    def test_shared_reports_need_every_player_and_both_captains_before_rewards(self):
        run,teams,members,generation=self.shared()
        self.assertDomain('result_agreement_required',self.service.finish_battle,run,teams[0])
        self.assertDomain('result_agreement_required',self.service.shared_finish,run,generation)
        self.assertDomain('forbidden',self.service.shared_report_result,self.player(),run,generation,teams[0],False,'a'*64)
        review=self.reports(run,teams,members,generation)
        self.assertEqual(review['review_state'],'awaiting_captains')
        self.assertEqual(self.db.settlements.count_documents({}),0)
        self.assertDomain('forbidden',self.service.shared_confirm_result,members[0][1],run,review['candidate_digest'])
        self.assertDomain('result_conflict',self.service.shared_confirm_result,members[0][0],run,'a'*64)
        self.service.shared_confirm_result(members[0][0],run,review['candidate_digest'])
        self.assertDomain('result_agreement_required',self.service.shared_finish,run,generation)
        agreed=self.service.shared_confirm_result(members[1][0],run,review['candidate_digest'])
        self.assertEqual(agreed['review_state'],'agreed')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.service.shared_finish(run,generation),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.db.settlements.count_documents({}),1)
        self.assertEqual(self.service.get_account(members[0][0])['leader']['total_experience'],20)
        self.assertEqual(self.service.get_account(members[1][0])['leader']['total_experience'],10)
        self.assertEqual(self.service.get_team(members[0][0],teams[0])['rating'],1012)

    def test_disputed_reports_require_audited_operator_resolution(self):
        admin=self.admin();run,teams,members,generation=self.shared()
        self.assertDomain('result_agreement_required',self.service.admin_resolve_shared_result,
                          admin,run,teams[0],False,'Review incomplete',1)
        review=self.reports(run,teams,members,generation,disputed=True)
        self.assertEqual(review['review_state'],'disputed')
        self.assertDomain('result_agreement_required',self.service.shared_finish,run,generation)
        self.assertDomain('result_conflict',self.service.shared_report_result,members[0][0],run,generation,teams[0],False,'0'*64)
        self.assertDomain('result_conflict',self.service.admin_resolve_shared_result,admin,run,teams[0],False,'Old review',0)
        result=self.service.admin_resolve_shared_result(admin,run,teams[0],False,'Reviewed all retained recordings',review['revision'])
        self.assertEqual(result['result']['winner_team_id'],teams[0])
        self.assertEqual(self.db.admin_audit.count_documents({'action':'resolve_shared_result'}),1)
        self.assertEqual(self.service.shared_result_review(members[0][0],run)['review_state'],'settled')

    def test_draw_and_captains_outside_selected_lineup(self):
        teams,members=self.teams(size=3)
        lineups={team:players[1:] for team,players in zip(teams,members)}
        run=self.service.create_battle(members[0][0],teams[1],'isars-cross',lineups)['_id']
        self.service.approve_battle(members[1][0],run)
        selected=members[0][1:]+members[1][1:]
        for actor in selected:self.service.set_ready(actor,run)
        generation=str(uuid4());self.service.shared_prepare(selected[0],run,generation)
        self.assertDomain('forbidden',self.service.shared_admission,members[0][0],run,generation)
        self.service.shared_start(run,generation,selected,'f'*64)
        outside=self.service.progression_start(members[0][0],rules.MISSIONS[0])['run']
        self.assertEqual(self.service.shared_admission(selected[0],run,generation)['room_state'],'running')
        for actor in selected:review=self.service.shared_report_result(actor,run,generation,None,True,'a'*64)
        for captain in (members[0][0],members[1][0]):self.service.shared_confirm_result(captain,run,review['candidate_digest'])
        self.service.shared_finish(run,generation)
        for actor in selected:
            replay=self.service.shared_replay_access(actor,run)
            self.assertEqual(replay,{'run_id':run,'account_id':actor,'generation':generation,'sha256':'a'*64})
        side_one=min(self.service.get_run(run)['participants'],key=lambda item:item['side'])['account_id']
        for captain in (members[0][0],members[1][0]):
            self.assertEqual(self.service.shared_replay_access(captain,run)['account_id'],side_one)
        self.assertDomain('forbidden',self.service.shared_replay_access,self.player(),run)
        for actor in selected:self.assertEqual(self.service.get_account(actor)['leader']['total_experience'],10)
        for captain in (members[0][0],members[1][0]):self.assertEqual(self.service.get_account(captain)['leader']['total_experience'],0)
        self.assertEqual(self.service.get_account(members[0][0])['active_run_id'],outside['id'])


if __name__ == '__main__': unittest.main()
