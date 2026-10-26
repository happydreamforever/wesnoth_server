"""Real Mongo transactions for flexible Team plans; disposable loopback only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import os
import unittest
from uuid import uuid4
from test_unified_product import UnifiedProduct as Fixture
from alliance.domain import DomainError, _now
from alliance.flexible import DEFAULT_SETTINGS
from alliance.schema import migrate_schema_2_to_3

@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable replica set')
class FlexibleProduct(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    tearDownClass=classmethod(Fixture.tearDownClass.__func__)
    setUp=Fixture.setUp;tearDown=Fixture.tearDown;player=Fixture.player;seed=Fixture.seed;code=Fixture.code
    def teams(self):
        ps=[[self.player(True) for _ in range(2)] for _ in range(2)]
        ts=[]
        for i,players in enumerate(ps):
            t=self.domain.create_team(players[0], 'Team '+str(i))['_id'];ts.append(t)
            self.domain.request_join(players[1],t);self.domain.approve_member(players[0],t,players[1])
        return ps,ts
    def slots(self):
        return [dict(side=i,kind='open',account_id='',ai_faction='',ai_leader='') for i in range(1,5)]
    def read(self,actor,b):return self.domain.directory_battle_detail(actor,b['id'])
    def publish(self,ps,ts,custom=True):
        slots=self.slots()
        if custom:slots[3].update(kind='ai',ai_faction='Loyalists',ai_leader='Lieutenant')
        b=self.domain.directory_publish_plan(ps[0][0],ts[0],ts[1],'isars-cross',DEFAULT_SETTINGS,slots)
        if custom:
            slots[2].update(kind='ai',ai_faction='Rebels',ai_leader='Elvish Captain')
            b=self.domain.directory_edit_plan(ps[1][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,slots)
        return b
    def fill(self,ps,b,custom=True,offset=0):
        players=[ps[0][offset],ps[1][offset]] if custom else [ps[0][0],ps[1][0],ps[1][1],ps[0][1]]
        for side,p in enumerate(players,1):
            b=self.domain.directory_join_plan(p,b['id'],b['revision'],side)
            b=self.domain.directory_select_plan_hero(p,b['id'],b['revision'],self.hero,self.form)
        for captain in (ps[0][0],ps[1][0]):b=self.domain.directory_approve_plan(captain,b['id'],b['revision'])
        for p in players:b=self.domain.directory_ready_plan(p,b['id'],b['revision'],True)
        return b,players
    def start(self,b,players):
        self.domain.shared_start(b['id'],b['generation'],players,'a'*64)
    def finish(self,b,ps,ts,players):
        for p in players:self.domain.shared_report_result(p,b['id'],b['generation'],ts[0],False,'b'*64)
        review=self.domain.shared_result_review(players[0],b['id'])
        for captain in (ps[0][0],ps[1][0]):self.domain.shared_confirm_result(captain,b['id'],review['candidate_digest'])
        return self.domain.shared_finish(b['id'],b['generation'])
    def test_ai_leader_choices_are_pinned_to_faction(self):
        ps,ts=self.teams();slots=self.slots()
        slots[3].update(kind='ai',ai_faction='Dunefolk',ai_leader='Dune Apothecary')
        b=self.domain.directory_publish_plan(ps[0][0],ts[0],ts[1],'isars-cross',DEFAULT_SETTINGS,slots)
        self.assertEqual(b['teams'][0]['slots'][1]['ai_leader'],'Dune Apothecary')
        slots[3].update(ai_faction='Northerners',ai_leader='Orcish Slayer')
        b=self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,slots)
        slots[3]['ai_leader']='Elvish Hero'
        self.code('invalid_lineup',lambda:self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,slots))

    def test_incomplete_multiple_plans_permissions_and_claim_race(self):
        ps,ts=self.teams();b=self.publish(ps,ts)
        second=self.publish(ps,ts)
        self.assertNotEqual(b['id'],second['id']);self.assertEqual(b['room_state'],'')
        self.assertEqual(sum(len(t['players']) for t in b['teams']),0)
        self.code('forbidden',lambda:self.domain.directory_join_plan(ps[1][0],b['id'],b['revision'],1))
        def claim(p):
            try:return self.domain.directory_join_plan(p,b['id'],b['revision'],1)['id']
            except DomainError as e:return e.code
        with ThreadPoolExecutor(2) as pool:out=list(pool.map(claim,ps[0]))
        self.assertEqual(out.count(b['id']),1)
        self.assertEqual(len(self.read(ps[0][0],b)['teams'][0]['players']),1)
    def test_two_humans_ai_prepare_start_custom_rewards_and_history(self):
        ps,ts=self.teams();b,players=self.fill(ps,self.publish(ps,ts))
        self.assertEqual(b['room_state'],'preparing');self.assertFalse(b['ranked'])
        self.assertEqual(b['engine_host_account_id'],players[0])
        self.code('forbidden',lambda:self.domain.directory_leave_plan(ps[0][1],b['id'],b['revision']))
        self.assertEqual(self.read(players[0],b),b)
        own=self.domain.shared_admission(players[0],b['id'],b['generation'])
        self.assertEqual(own['controlled_sides'],[1,3,4])
        for p in players:self.assertEqual(self.db.accounts.find_one({'_id':p})['active_run_id'],b['id'])
        self.start(b,players);receipt=self.finish(b,ps,ts,players)
        self.assertEqual([r['experience'] for r in receipt['rewards']['players']],[20,10])
        self.assertEqual([r['rating_delta'] for r in receipt['rewards']['teams']],[0,0])
        observer=ps[0][1]
        self.assertIn(b['id'],[x['id'] for x in self.domain.directory_my_battles(observer)['battles']])
        self.assertEqual(self.domain.shared_replay_access(observer,b['id'])['account_id'],players[0])
        outsider=self.player();self.code('forbidden',lambda:self.domain.shared_replay_access(outsider,b['id']))
        self.assertEqual(self.domain.shared_finish(b['id'],b['generation']),receipt)
    def test_concurrent_team_games_distinct_players_and_settlements(self):
        ps,ts=self.teams();a,pa=self.fill(ps,self.publish(ps,ts),offset=0)
        b,pb=self.fill(ps,self.publish(ps,ts),offset=1)
        self.start(a,pa);self.start(b,pb)
        with ThreadPoolExecutor(2) as pool:receipts=list(pool.map(lambda args:self.finish(args[0],ps,ts,args[1]),[(a,pa),(b,pb)]))
        self.assertEqual(self.db.teams.find_one({'_id':ts[0]})['experience'],200)
        self.assertEqual(self.db.teams.find_one({'_id':ts[1]})['experience'],50)
        self.assertEqual(self.db.settlements.count_documents({}),2)
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)
    def test_concurrent_ranked_team_results_use_current_rating_once(self):
        ps,ts=self.teams()
        for team,players in zip(ts,ps):
            for _ in range(2):
                actor=self.player(True);players.append(actor)
                self.domain.request_join(actor,team);self.domain.approve_member(players[0],team,actor)
        a,pa=self.fill(ps,self.publish(ps,ts,False),False)
        b=self.publish(ps,ts,False);pb=[ps[0][2],ps[1][2],ps[1][3],ps[0][3]]
        for side,actor in enumerate(pb,1):
            b=self.domain.directory_join_plan(actor,b['id'],b['revision'],side)
            b=self.domain.directory_select_plan_hero(actor,b['id'],b['revision'],self.hero,self.form)
        for actor in (ps[0][0],ps[1][0]):b=self.domain.directory_approve_plan(actor,b['id'],b['revision'])
        for actor in pb:b=self.domain.directory_ready_plan(actor,b['id'],b['revision'],True)
        self.start(a,pa);self.start(b,pb)
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda args:self.finish(args[0],ps,ts,args[1]),[(a,pa),(b,pb)]))
        self.assertEqual([self.db.teams.find_one({'_id':team})['rating'] for team in ts],[1023,977])
        self.assertEqual(self.db.settlements.count_documents({}),2)
        self.assertEqual(self.db.network_battle_reservations.count_documents({}),0)

    def test_reserved_closed_and_material_edit_revoke(self):
        ps,ts=self.teams();b=self.publish(ps,ts)
        slots=self.slots();slots[0].update(kind='reserved',account_id=ps[0][0]);slots[3].update(kind='closed')
        slots[2].update(kind='closed')
        b=self.domain.directory_edit_plan(ps[1][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,[dict(row) if row['side'] != 3 else {**row,'kind':'closed','ai_faction':'','ai_leader':''} for team in b['teams'] for row in team['slots']])
        b=self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,slots)
        self.code('forbidden',lambda:self.domain.directory_join_plan(ps[0][1],b['id'],b['revision'],1))
        b,players=self.fill(ps,b)
        self.assertEqual(self.domain.shared_admission(players[0],b['id'],b['generation'])['controlled_sides'],[1])
        oldgen=b['generation'];settings={**DEFAULT_SETTINGS,'gold':200}
        b=self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',settings,slots)
        self.assertFalse(any(p['ready'] for t in b['teams'] for p in t['players']))
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)
        self.code('invalid_state',lambda:self.domain.shared_admission(players[0],b['id'],oldgen))
    def test_imbalanced_draft_does_not_prepare_or_reserve(self):
        ps,ts=self.teams();b=self.publish(ps,ts)
        slots=[dict(row) for team in b['teams'] for row in team['slots']]
        side=next(row for row in slots if row['side']==3);side.update(kind='closed',ai_faction='',ai_leader='')
        b=self.domain.directory_edit_plan(ps[1][0],b['id'],b['revision'],'isars-cross',DEFAULT_SETTINGS,slots)
        self.assertEqual(b['validity'],'unbalanced_sides')
        for side,actor in [(1,ps[0][0]),(2,ps[1][0])]:
            b=self.domain.directory_join_plan(actor,b['id'],b['revision'],side)
            b=self.domain.directory_select_plan_hero(actor,b['id'],b['revision'],self.hero,self.form)
        for actor in (ps[0][0],ps[1][0]):b=self.domain.directory_approve_plan(actor,b['id'],b['revision'])
        b=self.domain.directory_ready_plan(ps[0][0],b['id'],b['revision'],True)
        self.code('unbalanced_sides',lambda:self.domain.directory_ready_plan(ps[1][0],b['id'],b['revision'],True))
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':b['id']}),0)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id':b['id']}),0)
        self.assertEqual(self.read(ps[0][0],b)['room_state'],'')

    def test_daemon_abort_releases_preparation_and_fences_new_generation(self):
        ps,ts=self.teams();b,players=self.fill(ps,self.publish(ps,ts));old=b['generation']
        self.domain.shared_cancel(b['id'],old,'fixture preparation abort')
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':b['id']}),0)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id':b['id']}),0)
        for actor in players:b=self.domain.directory_ready_plan(actor,b['id'],b['revision'],True)
        self.assertEqual(b['room_state'],'preparing');self.assertNotEqual(b['generation'],old)
        self.code('room_conflict',lambda:self.domain.shared_cancel(b['id'],old,'stale abort'))
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id':b['id'],'generation':b['generation']}),2)

    def test_expiry_releases_only_its_players(self):
        ps,ts=self.teams();b,players=self.fill(ps,self.publish(ps,ts))
        self.db.game_runs.update_one({'_id':b['id']},{'$set':{'shared_room.expires_at':_now()-timedelta(seconds=1)}})
        self.assertEqual(self.domain.expire_preparations(),1)
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':b['id']}),0)
        self.assertEqual(self.read(players[0],b)['room_state'],'cancelled')
    def test_cross_mode_reservation_lease_fence(self):
        ps,ts=self.teams();b=self.publish(ps,ts)
        game,generation=str(uuid4()),str(uuid4())
        ids=[ps[0][0],ps[1][0]]
        self.domain.network_prepare(game,generation,ids)
        self.assertEqual(self.domain.network_prepare(game,generation,ids)['reserved'],2)
        self.assertEqual(self.domain.network_heartbeat(generation,[game])['renewed'],[game])
        # Preparation fails atomically while the same players occupy Individual.
        for side,actor in enumerate(ids,1):
            b=self.domain.directory_join_plan(actor,b['id'],b['revision'],side)
            b=self.domain.directory_select_plan_hero(actor,b['id'],b['revision'],self.hero,self.form)
        for actor in ids:b=self.domain.directory_approve_plan(actor,b['id'],b['revision'])
        b=self.domain.directory_ready_plan(ids[0],b['id'],b['revision'],True)
        self.code('busy',lambda:self.domain.directory_ready_plan(ids[1],b['id'],b['revision'],True))
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)
        self.db.network_battle_reservations.update_many({'run_id':game},{'$set':{'expires_at':_now()-timedelta(seconds=1)}})
        b=self.domain.directory_ready_plan(ids[1],b['id'],b['revision'],True)
        self.assertEqual(b['room_state'],'preparing')
        self.assertEqual(self.domain.network_heartbeat(generation,[game])['expired'],[game])
        self.domain.network_release(game,generation)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'kind':'team','run_id':b['id']}),2)
        self.code('busy',lambda:self.domain.network_prepare(game,generation,ids))

    def test_observer_access_is_current_membership_and_running_only(self):
        ps,ts=self.teams();b=self.publish(ps,ts)
        slots=[{k:v for k,v in row.items()} for team in b['teams'] for row in team['slots']]
        b=self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',{**DEFAULT_SETTINGS,'observers':True},slots)
        b,players=self.fill(ps,b)
        observer=ps[0][1]
        self.code('forbidden',lambda:self.domain.shared_observer_admission(observer,b['id'],b['generation']))
        self.start(b,players)
        admission=self.domain.shared_observer_admission(observer,b['id'],b['generation'])
        self.assertEqual(admission['controlled_sides'],[]);self.assertEqual(admission['assigned_side'],0)
        self.domain.leave_team(observer)
        self.code('forbidden',lambda:self.domain.shared_observer_admission(observer,b['id'],b['generation']))
        self.code('busy',lambda:self.domain.transfer_captain(ps[1][0],ts[1],ps[1][1]))

    def test_actual_tls_human_barrier_ai_ownership_and_observer_read_only(self):
        import asyncio, contextlib, io, json, tempfile
        from pathlib import Path
        from alliance.auth import AuthService
        from alliance.battle_daemon import BattleDaemon, tls_context
        from alliance.battle_wire import Node, message, receive, send
        from tools.alliance_transport import prepare_identity, tls_client_context
        ps,ts=self.teams();b=self.publish(ps,ts)
        slots=[dict(row) for team in b['teams'] for row in team['slots']]
        b=self.domain.directory_edit_plan(ps[0][0],b['id'],b['revision'],'isars-cross',{**DEFAULT_SETTINGS,'observers':True},slots)
        b,players=self.fill(ps,b)
        auth=AuthService(self.db)
        def token(actor):
            name=self.domain.get_account(actor)['username'];number=name.split('_')[1]
            return auth.authenticate(name,'test player password '+number,'player')['token']
        tokens={actor:token(actor) for actor in [*players,ps[0][1]]}
        with tempfile.TemporaryDirectory(prefix='flexible-tls-') as temp:
            root=Path(temp)
            with contextlib.redirect_stdout(io.StringIO()):profile,_=prepare_identity(root/'identity','127.0.0.1',15001,Path('/usr/bin/openssl'))
            context,_=tls_context(root/'identity');client_context=tls_client_context(profile)
            async def exercise():
                daemon=BattleDaemon(self.db,root/'battles',context);writers=[];tasks=set()
                async def handler(reader,writer):
                    task=asyncio.current_task();tasks.add(task)
                    try:await daemon.handle(reader,writer)
                    finally:tasks.discard(task)
                server=await asyncio.start_server(handler,'127.0.0.1',0)
                port=server.sockets[0].getsockname()[1]
                async def connect(actor,intent='play'):
                    reader,writer=await asyncio.open_connection('127.0.0.1',port);writers.append(writer)
                    writer.write(b'\0\0\0\1');await writer.drain();self.assertEqual(await reader.readexactly(4),b'\0'*4)
                    await writer.start_tls(client_context,server_hostname='127.0.0.1')
                    await send(writer,message('alliance_join',run_id=b['id'],token=tokens[actor],intent=intent))
                    room=(await receive(reader,5)).one('alliance_room')
                    return reader,writer,room
                try:
                    a=await connect(players[0]);z=await connect(players[1])
                    self.assertEqual(a[2].attrs['controlled_sides'],'1,3,4')
                    await send(a[1],message('alliance_loaded',scenario_sha256='a'*64))
                    waiting=(await receive(a[0],5)).one('alliance_waiting');self.assertEqual(waiting.attrs['required'],'2')
                    await send(z[1],message('alliance_loaded',scenario_sha256='a'*64))
                    (await receive(a[0],5)).one('alliance_start');(await receive(z[0],5)).one('alliance_start')
                    for side,next_side,sender,other in [(1,2,a,z),(2,3,z,a),(3,4,a,z),(4,1,a,z)]:
                        packet=Node(children=[Node('turn',children=[Node('command',{'from_side':str(side)},[Node('end_turn',{'next_player_number':str(next_side)})])])])
                        await send(sender[1],packet);(await receive(other[0],5)).one('turn')
                    observer=await connect(ps[0][1],'observe')
                    self.assertEqual(json.loads(observer[2].attrs['descriptor'])['state'],'running')
                    self.assertEqual(observer[2].attrs['side'],'0');self.assertEqual(observer[2].attrs['controlled_sides'],'')
                    await send(observer[1],message('alliance_loaded',scenario_sha256='a'*64))
                    for _ in range(4):(await receive(observer[0],5)).one('turn')
                    (await receive(observer[0],5)).one('alliance_start')
                    await send(observer[1],Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('end_turn')])])]))
                    (await receive(observer[0],5)).one('leave_game')
                    await send(a[1],Node(children=[Node('turn',children=[Node('command',{'from_side':'2'},[Node('end_turn')])])]))
                    (await receive(a[0],5)).one('leave_game')
                    self.assertEqual(self.db.settlements.count_documents({}),0)
                finally:
                    for writer in writers:writer.close()
                    await asyncio.gather(*(w.wait_closed() for w in writers),return_exceptions=True)
                    server.close();await server.wait_closed()
                    if tasks:await asyncio.wait_for(asyncio.gather(*tasks),10)
            asyncio.run(exercise())

    def test_closed_side_turn_order_and_retained_replay(self):
        import tempfile
        from pathlib import Path
        from alliance.battle_daemon import Room
        from alliance.battle_wire import Node, WireError
        record={'generation':str(uuid4()),'battle':{'format':2,'map':{'size':3},'teams':[{'players':[],'slots':[{'side':n,'kind':'closed' if n in (1,6) else 'ai'} for n in range(1,7)]}]}}
        with tempfile.TemporaryDirectory() as temporary:
            room=Room(None,'test',Path(temporary),record)
            self.assertEqual(room.current_side,2)
            for previous,next_raw,expected,turn in [(2,3,3,1),(3,4,4,1),(4,5,5,1),(5,6,2,2)]:
                self.assertEqual(room.current_side,previous)
                room.append(Node(children=[Node('turn',children=[Node('command',{'from_side':str(previous)},[Node('end_turn',{'next_player_number':str(next_raw)})])])]))
                self.assertEqual((room.current_side,room.current_turn),(expected,turn))
            restored=Room(None,'test',Path(temporary),record)
            self.assertEqual((restored.current_side,restored.current_turn),(2,2))
            with self.assertRaises(WireError):room.next_active_side(8)

    def test_ranked_full_human_default_and_migration_resume(self):
        ps,ts=self.teams();b,players=self.fill(ps,self.publish(ps,ts,False),False)
        self.assertTrue(b['ranked']);self.start(b,players);receipt=self.finish(b,ps,ts,players)
        self.assertEqual([r['rating_delta'] for r in receipt['rewards']['teams']],[12,-12])
        original=list(self.db.game_runs.find({}));generation=self.db.schema_metadata.find_one({'_id':'alliance'})['database_generation']
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':2}})
        self.db.drop_collection('network_battle_reservations')
        def stop(phase):
            if phase=='validators':raise RuntimeError('injected crash')
        with self.assertRaises(RuntimeError):migrate_schema_2_to_3(self.db,'a'*64,checkpoint=stop)
        self.assertEqual(self.db.schema_metadata.find_one({'_id':'alliance'})['version'],2)
        result=migrate_schema_2_to_3(self.db,'a'*64)
        self.assertEqual(result['database_generation'],generation);self.assertEqual(list(self.db.game_runs.find({})),original)
        self.assertEqual(migrate_schema_2_to_3(self.db,'a'*64)['status'],'already_complete')
        with self.assertRaises(RuntimeError):migrate_schema_2_to_3(self.db,'b'*64)
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'database_generation':str(uuid4())}})
        with self.assertRaisesRegex(RuntimeError,'identity'):migrate_schema_2_to_3(self.db,'a'*64)
del Fixture
if __name__=='__main__':unittest.main()
