"""Actual pinned TLS + disposable MongoDB shared-room lifecycle checks.

The test peers speak the real bounded wire protocol. They are not Wesnoth combat
engines, so these tests do not claim simulation or Android acceptance.
"""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_alliance_domain as fixtures
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.battle_daemon import BattleDaemon, tls_context
from alliance.battle_wire import Node, WireError, message, receive, send
from tools.alliance_transport import prepare_identity, tls_client_context


class Client:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    async def send(self, node):
        await send(self.writer, node)

    async def read(self, name):
        root = await receive(self.reader, 5)
        return root.one(name)

    async def close(self):
        self.writer.close()
        try: await self.writer.wait_closed()
        except (OSError, ssl.SSLError): pass


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI') and shutil.which('openssl'),
                     'Requires disposable loopback MongoDB and local OpenSSL.')
class BattleDaemonTests(unittest.IsolatedAsyncioTestCase):
    player = fixtures.MongoDomainTests.player
    teams = fixtures.MongoDomainTests.teams
    battle = fixtures.MongoDomainTests.battle

    @classmethod
    def setUpClass(cls):
        fixtures.MongoDomainTests.setUpClass.__func__(cls)
        cls.cert_temp = tempfile.TemporaryDirectory(prefix='alliance-daemon-tls-')
        cls.identity = Path(cls.cert_temp.name)/'identity'
        cls.profile, _ = prepare_identity(cls.identity, '127.0.0.1', 15001, Path(shutil.which('openssl')))
        cls.server_context, _ = tls_context(cls.identity)
        cls.client_context = tls_client_context(cls.profile)
        cls.password = 'Disposable-player-password-123'
        cls.password_hash = hash_password(cls.password)

    @classmethod
    def tearDownClass(cls):
        cls.cert_temp.cleanup()
        fixtures.MongoDomainTests.tearDownClass.__func__(cls)

    async def asyncSetUp(self):
        fixtures.MongoDomainTests.setUp(self)
        bootstrap_auth_schema(self.db)
        self.auth = AuthService(self.db)
        self.scratch = tempfile.TemporaryDirectory(prefix='alliance-daemon-room-')
        self.storage = Path(self.scratch.name)/'battles'
        self.peers = []
        self.handlers = set()
        self.settlement = None
        await self.start_server()

    async def start_server(self):
        self.daemon = BattleDaemon(self.db,self.storage,self.server_context)
        async def handler(reader,writer):
            task=asyncio.current_task();self.handlers.add(task)
            try: await self.daemon.handle(reader,writer)
            finally:self.handlers.discard(task)
        self.server = await asyncio.start_server(handler,'127.0.0.1',0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop_server(self):
        if self.settlement:
            self.settlement.cancel()
            await asyncio.gather(self.settlement,return_exceptions=True)
            self.settlement=None
        for peer in self.peers:await peer.close()
        self.peers=[]
        self.server.close();await self.server.wait_closed()
        if self.handlers:
            await asyncio.wait_for(asyncio.gather(*list(self.handlers)),10)

    async def asyncTearDown(self):
        await self.stop_server()
        self.scratch.cleanup()
        fixtures.MongoDomainTests.tearDown(self)

    def plan(self,size=2):
        run,teams,members=self.battle(size=size,start=False)
        self.db.accounts.update_many({}, {'$set':{'password_hash':self.password_hash}})
        tokens={actor:self.auth.authenticate(self.service.get_account(actor)['username'],self.password,'player')['token']
                for actor in sum(members,[])}
        return run['_id'],teams,members,tokens

    async def connect(self,run,token,intent='play'):
        reader,writer=await asyncio.open_connection('127.0.0.1',self.port)
        peer=Client(reader,writer);self.peers.append(peer)
        writer.write(b'\0\0\0\1');await writer.drain()
        self.assertEqual(await reader.readexactly(4),b'\0\0\0\0')
        await writer.start_tls(self.client_context,server_hostname='127.0.0.1')
        self.assertEqual(hashlib.sha256(writer.get_extra_info('ssl_object').getpeercert(binary_form=True)).hexdigest(),
                         self.profile['certificate_sha256'])
        await peer.send(message('alliance_join',run_id=run,token=token,intent=intent))
        return peer

    async def joined(self,run,actor,token,intent='play'):
        peer=await self.connect(run,token,intent)
        descriptor=await peer.read('alliance_room')
        self.assertEqual(json.loads(descriptor.attrs['descriptor'])['id'],run)
        return peer,descriptor

    async def running(self,size=2):
        run,teams,members,tokens=self.plan(size)
        peers={}
        for actor in sum(members,[]):
            peer,descriptor=await self.joined(run,actor,tokens[actor]);peers[actor]=peer
        ordered=list(peers.values())
        for peer in ordered[:-1]:
            await peer.send(message('alliance_loaded',scenario_sha256='f'*64));await peer.read('alliance_waiting')
        await ordered[-1].send(message('alliance_loaded',scenario_sha256='f'*64))
        for peer in ordered:await peer.read('alliance_start')
        self.assertEqual(self.service.get_run(run)['state'],'running')
        return run,teams,members,tokens,peers

    async def until(self,predicate):
        for _ in range(100):
            if predicate():return
            await asyncio.sleep(.05)
        self.fail('Expected bounded state transition did not complete.')

    async def test_four_six_eight_fixed_seats_and_no_start_before_all_loaded(self):
        for size in (2,3,4):
            with self.subTest(size=size):
                run,teams,members,tokens,peers=await self.running(size)
                room=self.daemon.rooms[run]
                self.assertEqual({p.side for p in room.peers.values()},set(range(1,size*2+1)))
                self.assertEqual(self.db.accounts.count_documents({'active_run_id':run}),size*2)
                for peer in peers.values():await peer.close()
                self.service.shared_cancel(run,room.generation,'Fixture finished without game rewards')
                # Team names are unique; make the following fixture independent.
                for team in teams:self.db.teams.update_one({'_id':team},{'$set':{'name_key':str(uuid4())}})

    async def test_revoked_waiting_session_cannot_cross_loaded_barrier(self):
        run,teams,members,tokens=self.plan()
        peers=[]
        for actor in sum(members,[]):peers.append((await self.joined(run,actor,tokens[actor]))[0])
        for peer in peers[:-1]:
            await peer.send(message('alliance_loaded',scenario_sha256='f'*64));await peer.read('alliance_waiting')
        self.auth.revoke_token(tokens[members[0][0]])
        await peers[-1].send(message('alliance_loaded',scenario_sha256='f'*64))
        await peers[-1].read('leave_game')
        self.assertEqual(self.service.get_run(run)['state'],'draft')
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)

    async def test_duplicate_seat_and_spoof_turn_do_not_change_history(self):
        run,teams,members,tokens,peers=await self.running()
        duplicate=await self.connect(run,tokens[members[0][0]])
        await duplicate.read('leave_game')
        room=self.daemon.rooms[run];before=room.chain
        wrong=peers[members[1][0]]
        await wrong.send(Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('end_turn')])])]))
        await wrong.read('leave_game')
        self.assertEqual(room.chain,before)
        self.assertEqual(room.current_side,1)

    async def test_mismatched_loaded_hash_and_false_dependent_turn_cannot_start_or_advance(self):
        run,teams,members,tokens=self.plan();actors=sum(members,[])
        first,_=await self.joined(run,actors[0],tokens[actors[0]])
        second,_=await self.joined(run,actors[1],tokens[actors[1]])
        await first.send(message('alliance_loaded',scenario_sha256='f'*64));await first.read('alliance_waiting')
        await second.send(message('alliance_loaded',scenario_sha256='a'*64));await second.read('leave_game')
        self.assertEqual(self.service.get_run(run)['state'],'draft')
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)
        self.service.shared_cancel(run,self.daemon.rooms[run].generation,'Fixture preparation cancelled')
        await first.close();await second.close()
        peers={}
        for actor in actors:peers[actor]=(await self.joined(run,actor,tokens[actor]))[0]
        for peer in list(peers.values())[:-1]:
            await peer.send(message('alliance_loaded',scenario_sha256='f'*64));await peer.read('alliance_waiting')
        await list(peers.values())[-1].send(message('alliance_loaded',scenario_sha256='f'*64))
        for peer in peers.values():await peer.read('alliance_start')
        wrong=peers[members[1][0]]
        await wrong.send(Node(children=[Node('turn',children=[Node('command',{'from_side':'2','dependent':'yes'},
            [Node('end_turn',{'next_player_number':'3'})])])]))
        await wrong.read('leave_game');self.assertEqual(self.daemon.rooms[run].current_side,1)

    async def test_complete_round_tracks_stock_size_plus_one_and_reconnect_turn(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run]
        actors={peer.side:actor for actor,peer in room.peers.items()}
        for side in range(1,5):
            actor=actors[side]
            await peers[actor].send(Node(children=[Node('turn',children=[Node('command',{'from_side':str(side)},
                [Node('end_turn',{'next_player_number':str(side+1)})])])]))
            for other,peer in peers.items():
                if other!=actor:await peer.read('turn')
        self.assertEqual((room.current_side,room.current_turn),(1,2))
        await peers[actors[1]].close();await self.until(lambda:actors[1] not in room.peers)
        reconnect,descriptor=await self.joined(run,actors[1],tokens[actors[1]])
        self.assertEqual((descriptor.attrs['current_side'],descriptor.attrs['current_turn']),('1','2'))

    async def test_debug_and_controller_mutations_rejected_before_recording(self):
        run,teams,members,tokens,peers=await self.running();actor=members[0][0];room=self.daemon.rooms[run]
        for tag in ('debug_lua','change_controller_wml'):
            peer=peers[actor]
            await peer.send(Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node(tag)])])]))
            await peer.read('leave_game');await self.until(lambda:actor not in room.peers)
            self.assertEqual(room.chain,'0'*64)
            peers[actor]=(await self.joined(run,actor,tokens[actor]))[0]
            await peers[actor].send(message('alliance_loaded',scenario_sha256='f'*64));await peers[actor].read('alliance_start')

    async def test_event_write_failure_freezes_all_peers_without_settlement(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run]
        with patch('alliance.battle_daemon.os.fsync',side_effect=OSError('Fixture write failure')):
            await peers[members[0][0]].send(message('message',message='Fixture chat'))
            await self.until(lambda:room.failed)
        self.assertEqual(room.chain,'0'*64)
        self.assertEqual(self.service.get_run(run)['state'],'running')
        self.assertEqual(self.db.settlements.count_documents({}),0)

    async def test_warm_and_cold_reconnect_replay_exact_history_and_fence_tampering(self):
        run,teams,members,tokens,peers=await self.running()
        first=members[0][0];turn=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},
            [Node('end_turn',{'next_player_number':'2'})])])])
        await peers[first].send(turn)
        for actor,peer in peers.items():
            if actor!=first:await peer.read('turn')
        await peers[first].send(message('message',message='Retained chat is not replay input'))
        for peer in peers.values():await peer.read('message')
        actor=members[1][1];await peers[actor].close()
        await self.until(lambda:actor not in self.daemon.rooms[run].peers)
        warm,descriptor=await self.joined(run,actor,tokens[actor]);self.assertEqual(descriptor.attrs['reconnect'],'yes')
        await warm.send(message('alliance_loaded',scenario_sha256='f'*64));await warm.read('turn');await warm.read('alliance_start')
        chain=self.daemon.rooms[run].chain
        await self.stop_server();await self.start_server();await self.daemon.recover_running()
        self.assertEqual(self.daemon.rooms[run].chain,chain);self.assertEqual(self.daemon.rooms[run].current_side,2)
        cold,descriptor=await self.joined(run,actor,tokens[actor]);self.assertEqual(descriptor.attrs['reconnect'],'yes')
        await cold.send(message('alliance_loaded',scenario_sha256='f'*64));await cold.read('turn');await cold.read('alliance_start')
        await self.stop_server()
        event=self.storage/run/'events.jsonl';event.write_text(event.read_text().replace('end_turn','bad_turn'))
        await self.start_server()
        with self.assertRaises(ValueError):await self.daemon.recover_running()
        self.assertEqual(self.service.get_run(run)['state'],'running')

    async def test_expired_preparation_is_retained_and_renewed_without_reservations(self):
        run,teams,members,tokens=self.plan();actor=members[0][0]
        old,_=await self.joined(run,actor,tokens[actor]);generation=self.daemon.rooms[run].generation
        self.db.game_runs.update_one({'_id':run},{'$set':{'shared_room.expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}})
        fresh,_=await self.joined(run,actor,tokens[actor])
        self.assertNotEqual(self.daemon.rooms[run].generation,generation)
        self.assertEqual(len(list(self.storage.glob(run+'-before-*'))),1)
        self.assertEqual(self.service.get_run(run)['state'],'draft')
        self.assertEqual(self.db.accounts.count_documents({'active_run_id':{'$ne':None}}),0)

    async def test_retained_marker_loads_obey_the_same_room_cap(self):
        first,teams,members,tokens,peers=await self.running()
        first_actor=members[0][0]
        for team in teams:self.db.teams.update_one({'_id':team},{'$set':{'name_key':str(uuid4())}})
        second,teams,members,tokens=self.plan();second_actor=members[0][0]
        await self.joined(second,second_actor,tokens[second_actor])
        await self.stop_server();await self.start_server()
        with patch('alliance.battle_daemon.MAX_ROOMS',1):
            await self.daemon.room(first_actor,first)
            with self.assertRaises(WireError):await self.daemon.room(second_actor,second)
        self.assertEqual(set(self.daemon.rooms),{first})
        self.assertTrue((self.storage/second/'room.json').is_file())

    async def upload(self,peer,run,winner,content):
        digest=hashlib.sha256(content).hexdigest()
        await peer.send(message('alliance_replay_begin',bytes=len(content),sha256=digest));await peer.read('alliance_replay_ready')
        for offset in range(0,len(content),24000):
            await peer.send(message('alliance_replay_chunk',offset=offset,data=base64.b64encode(content[offset:offset+24000]).decode()))
            await peer.read('alliance_replay_ready')
        await peer.send(message('alliance_result',winner_team_id=winner,draw='no',replay_sha256=digest))
        return await peer.read('alliance_result_saved')

    async def settled(self,content):
        run,teams,members,tokens,peers=await self.running()
        for peer in peers.values():await self.upload(peer,run,teams[0],content)
        review=self.service.shared_result_review(members[0][0],run)
        for captain in (members[0][0],members[1][0]):self.service.shared_confirm_result(captain,run,review['candidate_digest'])
        self.settlement=asyncio.create_task(self.daemon.settle_ready())
        await self.until(lambda:self.service.get_run(run)['state']=='completed')
        return run,teams,members,tokens,peers

    async def test_completed_replay_download_is_exact_bounded_read_only_and_membership_independent(self):
        content=b'Recorded fixture replay\n'*2500
        run,teams,members,tokens,peers=await self.settled(content)
        actor=members[0][1];self.service.leave_team(actor)
        before={name:list(self.db[name].find({}).sort('_id',1)) for name in
                ('accounts','teams','game_runs','settlements','admin_audit','auth_sessions')}
        download=await self.connect(run,tokens[actor],'replay_download')
        info=await download.read('alliance_replay_info')
        self.assertEqual(info.attrs,{'run_id':run,'account_id':actor,'bytes':str(len(content)),
            'sha256':hashlib.sha256(content).hexdigest(),'format':'wesnoth-replay-v1'})
        received=b''
        while len(received)<len(content):
            await download.send(message('alliance_replay_get',offset=len(received)))
            chunk=await download.read('alliance_replay_data')
            self.assertEqual(int(chunk.attrs['offset']),len(received))
            part=base64.b64decode(chunk.attrs['data'],validate=True);self.assertLessEqual(len(part),24000)
            received+=part
        self.assertEqual(received,content)
        self.assertEqual(before,{name:list(self.db[name].find({}).sort('_id',1)) for name in before})
        bad=await self.connect(run,tokens[actor],'replay_download');await bad.read('alliance_replay_info')
        await bad.send(message('alliance_replay_get',offset=1));await bad.read('leave_game')
        outsider=self.player();self.db.accounts.update_one({'_id':outsider},{'$set':{'password_hash':self.password_hash}})
        outsider_token=self.auth.authenticate(self.service.get_account(outsider)['username'],self.password,'player')['token']
        forbidden=await self.connect(run,outsider_token,'replay_download');await forbidden.read('leave_game')

    async def test_replay_download_requires_completed_state_current_session_and_intact_file(self):
        content=b'Private recorded fixture\n'*2500
        run,teams,members,tokens,peers=await self.settled(content);actor=members[0][1]
        peer=await self.connect(run,tokens[actor],'replay_download');await peer.read('alliance_replay_info')
        await peer.send(message('alliance_replay_get',offset=0));await peer.read('alliance_replay_data')
        self.auth.revoke_token(tokens[actor])
        await peer.send(message('alliance_replay_get',offset=24000));await peer.read('leave_game')
        other=members[1][1];path=self.storage/run/(other+'-'+hashlib.sha256(content).hexdigest()+'.replay')
        path.write_bytes(b'Altered recording')
        damaged=await self.connect(run,tokens[other],'replay_download');await damaged.read('leave_game')
        for team in teams:self.db.teams.update_one({'_id':team},{'$set':{'name_key':str(uuid4())}})
        draft,teams,members,tokens=self.plan();actor=members[0][0]
        denied=await self.connect(draft,tokens[actor],'replay_download');await denied.read('leave_game')

    async def test_uploaded_results_restart_recovery_captain_agreement_and_once_rewards(self):
        run,teams,members,tokens,peers=await self.running()
        for actor,peer in peers.items():await self.upload(peer,run,teams[0],('Fixture recording '+actor).encode())
        self.assertEqual(self.db.settlements.count_documents({}),0)
        # Simulate process loss after committed END report but before the local
        # marker update: the exact uploaded file and DB digest must recover it.
        marker=self.storage/run/'room.json';record=json.loads(marker.read_text());record['replays']={}
        marker.write_text(json.dumps(record))
        await self.stop_server();await self.start_server()
        review=self.service.shared_result_review(members[0][0],run)
        for captain in (members[0][0],members[1][0]):self.service.shared_confirm_result(captain,run,review['candidate_digest'])
        self.settlement=asyncio.create_task(self.daemon.settle_ready())
        await self.until(lambda:self.service.get_run(run)['state']=='completed')
        self.assertEqual(self.db.settlements.count_documents({}),1)
        self.assertEqual(self.service.get_account(members[0][0])['leader']['total_experience'],20)
        self.assertEqual(len(self.daemon.rooms[run].record['replays']),4)
        saved=marker.read_text()
        for token in tokens.values():self.assertNotIn(token,saved)
        actor=members[0][1]
        self.service.leave_team(actor)
        retry,_=await self.joined(run,actor,tokens[actor],intent='result_retry')
        answer=await self.upload(retry,run,teams[0],('Fixture recording '+actor).encode())
        self.assertEqual(answer.attrs['state'],'settled')
        self.assertEqual(self.db.settlements.count_documents({}),1)
        await retry.send(message('alliance_loaded',scenario_sha256='f'*64));await retry.read('leave_game')
        forbidden=await self.connect(run,tokens[actor]);await forbidden.read('leave_game')

    async def test_pending_result_upload_before_loaded_and_bad_hash_retains_running_run(self):
        run,teams,members,tokens,peers=await self.running();actor=members[0][0]
        await peers[actor].close();await self.until(lambda:actor not in self.daemon.rooms[run].peers)
        retry,_=await self.joined(run,actor,tokens[actor],intent='result_retry')
        await self.upload(retry,run,teams[0],b'Durable pending replay fixture')
        self.assertFalse(self.daemon.rooms[run].peers[actor].loaded)
        self.assertEqual(self.service.shared_result_review(actor,run)['reports_received'],1)
        bad=peers[members[1][0]]
        await bad.send(message('alliance_replay_begin',bytes=3,sha256='a'*64));await bad.read('alliance_replay_ready')
        await bad.send(message('alliance_replay_chunk',offset=0,data=base64.b64encode(b'bad').decode()));await bad.read('alliance_replay_ready')
        await bad.send(message('alliance_result',winner_team_id=teams[0],draw='no',replay_sha256='a'*64))
        await bad.read('leave_game')
        self.assertEqual(self.service.shared_result_review(actor,run)['reports_received'],1)
        self.assertEqual(self.service.get_run(run)['state'],'running')
        self.assertEqual(self.db.settlements.count_documents({}),0)

    async def test_real_engine_termination_advisory_is_not_a_result_and_allows_upload(self):
        run,teams,members,tokens,peers=await self.running();actor=members[0][0];room=self.daemon.rooms[run]
        before=room.chain
        for result in ('victory','defeat'):
            await peers[actor].send(message('info',type='termination',condition='game over',result=result))
        await self.upload(peers[actor],run,teams[0],b'Actual controller END ordering fixture')
        self.assertEqual(room.chain,before)
        self.assertEqual(self.service.shared_result_review(actor,run)['reports_received'],1)
        self.assertEqual(self.db.settlements.count_documents({}),0)
        bad=peers[members[1][0]]
        await bad.send(message('info',type='termination',condition='game over',result='victory',experience=999))
        await bad.read('leave_game')
        self.assertEqual(self.service.shared_result_review(actor,run)['reports_received'],1)

    def captain_packet(self,side,action):
        return Node(children=[Node('turn',children=[Node('command',{'from_side':str(side)},[
            Node('custom_command',{'name':'alliance_captain_v1'},[Node('data',{'action':action})]),Node('checkup')])])])

    async def test_captain_feature_gate_rejects_without_mutating(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run]
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',False):
            await peers[members[0][0]].send(self.captain_packet(1,'surrender'))
            await peers[members[0][0]].read('leave_game')
        self.assertNotIn('terminal',self.service.get_run(run)['shared_room'])
        self.assertEqual(room.chain,'0'*64)

    async def test_ordered_captain_command_crash_recovery_replays_exactly_once(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run];actor=members[0][0]
        packet=self.captain_packet(1,'surrender')
        packet.children[0].children.insert(0,Node('command',{'from_side':'1'},[Node('move',{'x':'1,2','y':'1,1'})]))
        def fail_before_append(node):
            room.freeze()
            raise RuntimeError('Fixture crash after database commit before event append')
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',True),patch.object(room,'append',side_effect=fail_before_append):
            await peers[actor].send(packet)
            await self.until(lambda:room.failed)
        stored=self.service.get_run(run)['shared_room']
        self.assertEqual(stored['terminal']['winner_team_id'],teams[1])
        self.assertEqual(room.chain,'0'*64)
        await self.stop_server();await self.start_server();await self.daemon.recover_running()
        recovered=self.daemon.rooms[run]
        self.assertEqual(len(recovered.history),1)
        self.assertEqual(recovered.chain,stored['terminal']['command_id'])
        await self.daemon.recover_running();self.assertEqual(len(recovered.history),1)
        self.assertEqual(self.db.settlements.count_documents({}),0)
        peer,_=await self.joined(run,actor,tokens[actor])
        await peer.send(message('alliance_loaded',scenario_sha256='f'*64))
        replay=await peer.read('turn');await peer.read('alliance_start')
        self.assertEqual(replay.children[0].children[0].name,'move')
        self.assertEqual(replay.children[-1].children[0].attrs['name'],'alliance_captain_v1')

    async def test_buffered_same_turn_moves_precede_final_captain_decision(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run];actor=members[0][0]
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',True):
            for action in ('offer_draw','withdraw_draw'):
                packet=self.captain_packet(1,action)
                packet.children[0].children[:0]=[
                    Node('command',{'from_side':'1'},[Node('move',{'x':'1,2','y':'1,1'})]),
                    Node('command',{'from_side':'1'},[Node('recruit',{'type':'Spearman','x':'2','y':'2'})])]
                await peers[actor].send(packet)
                for other in sum(members,[]):
                    if other!=actor:
                        relayed=await peers[other].read('turn')
                        self.assertEqual([command.children[0].name for command in relayed.children],['move','recruit','custom_command'])
                self.assertEqual(room.current_side,1)
        record=self.service.get_run(run)['shared_room']
        self.assertEqual(record['draw_offers'],[])
        self.assertEqual(len(record['captain_commands']),2)
        self.assertEqual(len(room.history),2)
        self.assertEqual(self.db.settlements.count_documents({}),0)

    async def test_captain_packet_rejects_cross_turn_nonfinal_and_spoofed_prefixes(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run];actor=members[0][0]
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',True):
            for mode in ('nonfinal','multiple','end_turn','other_side','debug'):
                packet=self.captain_packet(1,'offer_draw');commands=packet.children[0].children
                if mode=='nonfinal':commands.append(Node('command',{'from_side':'1'},[Node('move')]))
                elif mode=='multiple':commands[:0]=self.captain_packet(1,'withdraw_draw').children[0].children
                else:
                    child=Node('end_turn',{'next_player_number':'2'}) if mode=='end_turn' else Node('debug_lua' if mode=='debug' else 'move')
                    commands.insert(0,Node('command',{'from_side':'2' if mode=='other_side' else '1'},[child]))
                await peers[actor].send(packet);await peers[actor].read('leave_game')
                await self.until(lambda:actor not in room.peers)
                self.assertEqual(room.chain,'0'*64)
                self.assertNotIn('captain_commands',self.service.get_run(run)['shared_room'])
                peers[actor],_=await self.joined(run,actor,tokens[actor])
                await peers[actor].send(message('alliance_loaded',scenario_sha256='f'*64))
                await peers[actor].read('alliance_start')

    async def test_captain_wire_rejects_out_of_turn_and_spoofed_payload_before_mutating(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run]
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',True):
            await peers[members[1][0]].send(self.captain_packet(2,'offer_draw'))
            await peers[members[1][0]].read('leave_game')
            packet=self.captain_packet(1,'surrender');packet.children[0].children[0].children[0].children[0].attrs['winner_team_id']=teams[0]
            await peers[members[0][0]].send(packet);await peers[members[0][0]].read('leave_game')
        self.assertNotIn('captain_commands',self.service.get_run(run)['shared_room'])
        self.assertEqual(room.chain,'0'*64)

    async def test_committed_captain_command_preflight_limit_freezes_before_later_events(self):
        run,teams,members,tokens,peers=await self.running();room=self.daemon.rooms[run];actor=members[0][0]
        with patch('alliance.battle_daemon.CAPTAIN_COMMANDS_ENABLED',True),patch('alliance.battle_daemon.MAX_HISTORY',1):
            await peers[actor].send(self.captain_packet(1,'surrender'))
            await self.until(lambda:room.failed)
        self.assertEqual(room.chain,'0'*64)
        self.assertIn('terminal',self.service.get_run(run)['shared_room'])
        await self.stop_server();await self.start_server();await self.daemon.recover_running()
        self.assertEqual(len(self.daemon.rooms[run].history),1)
        self.assertEqual(self.db.settlements.count_documents({}),0)


if __name__=='__main__':unittest.main()
