"""Worker authority and durable evidence rejection tests; no fake combat claim."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
from uuid import uuid4
from alliance.world_worker import WorldWorkerSupervisor, canonical, sha, validate_evidence
from alliance.world_execution import WorldRoom, WorldPeer, download_world
from alliance.battle_wire import Node, WireError


class WorkerAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.actor,self.run,self.generation=[str(uuid4()) for _ in range(3)]
        self.descriptor={'run_id':self.run,'generation':self.generation,'required_humans':[self.actor],
            'sides':[{'side':1,'team_id':'a','controller':'human','account_id':self.actor,
                'hero':{'instance_id':'h'},'soldiers':[]},
                {'side':2,'team_id':'b','controller':'worker','account_id':None,'hero':None,'soldiers':[]}]}
        self.daemon=SimpleNamespace(storage=self.root,domain=SimpleNamespace())
        self.supervisor=WorldWorkerSupervisor(self.daemon,self.root)
    def tearDown(self):self.temp.cleanup()

    def test_machine_ticket_is_run_scoped_single_use_and_generation_bound(self):
        ticket=self.supervisor.capability(self.run,self.generation,'machine-1234')
        with self.assertRaises(ValueError):self.supervisor.consume(ticket,str(uuid4()))
        self.assertEqual(self.supervisor.consume(ticket,self.run)['generation'],self.generation)
        with self.assertRaises(ValueError):self.supervisor.consume(ticket,self.run)

    def test_worker_spawn_failure_releases_ticket_and_closes_log(self):
        async def run():
            self.daemon.domain.world_worker_pause=Mock()
            logs=[]
            async def spawn(*args,**kwargs):
                logs.append(kwargs['stdout']);raise OSError('test missing executable')
            with patch('alliance.world_worker.asyncio.create_subprocess_exec',spawn):
                await self.supervisor.launch(self.descriptor,'machine-1234')
            self.assertFalse(self.supervisor.children);self.assertFalse(self.supervisor.tickets)
            self.assertTrue(logs[0].closed)
            self.daemon.domain.world_worker_pause.assert_called_once_with(
                self.run,'machine-1234',self.generation,'worker_interrupted')
        asyncio.run(run())

    def test_private_stdin_failure_stops_child_and_releases_ticket(self):
        async def run():
            self.daemon.domain.world_worker_pause=Mock()
            self.daemon.domain.world_worker_lease=Mock(return_value={'state':'preparing'})
            child=SimpleNamespace(returncode=None,stdin=SimpleNamespace(
                write=Mock(),drain=AsyncMock(side_effect=BrokenPipeError()),close=Mock()))
            child.terminate=Mock()
            async def stopped():child.returncode=1;return 1
            child.wait=AsyncMock(side_effect=stopped)
            with patch('alliance.world_worker.asyncio.create_subprocess_exec',AsyncMock(return_value=child)):
                await self.supervisor.launch(self.descriptor,'machine-1234')
            child.terminate.assert_called_once();child.wait.assert_awaited_once()
            self.assertFalse(self.supervisor.children);self.assertFalse(self.supervisor.tickets)
            self.daemon.domain.world_worker_pause.assert_called_once_with(
                self.run,'machine-1234',self.generation,'worker_interrupted')
        asyncio.run(run())

    def test_finished_worker_invalid_proof_requires_review_not_restart(self):
        async def run():
            self.daemon.domain.world_worker_pause=Mock()
            child=SimpleNamespace(returncode=0,stdin=SimpleNamespace(
                write=Mock(),drain=AsyncMock(),close=Mock()))
            async def stopped():
                self.supervisor.rooms[self.run].terminal_cursor={'count':1,'sha256':'a'*64}
                return 0
            child.wait=AsyncMock(side_effect=stopped)
            with patch('alliance.world_worker.asyncio.create_subprocess_exec',AsyncMock(return_value=child)):
                await self.supervisor.launch(self.descriptor,'machine-1234')
            self.assertEqual(self.supervisor.rooms[self.run].pause_reason,'native_evidence_conflict')
            self.daemon.domain.world_worker_pause.assert_called_once_with(
                self.run,'machine-1234',self.generation,'native_evidence_conflict')
            self.assertFalse(self.supervisor.children);self.assertFalse(self.supervisor.tickets)
            with patch('alliance.world_worker.asyncio.create_subprocess_exec',AsyncMock()) as spawn:
                with self.assertRaises(ValueError):
                    await self.supervisor.launch(self.descriptor,'machine-5678')
                spawn.assert_not_awaited()
        asyncio.run(run())

    def test_retained_terminal_without_proof_requires_review(self):
        async def run():
            self.daemon.domain.world_worker_pause=Mock()
            directory=self.supervisor.root/self.run/self.generation;directory.mkdir(parents=True)
            room=WorldRoom(self.supervisor,self.descriptor,directory)
            room.terminal_cursor={'count':0,'sha256':'0'*64};room.persist()
            with patch('alliance.world_worker.asyncio.create_subprocess_exec',AsyncMock()) as spawn:
                with self.assertRaises(ValueError):
                    await self.supervisor.launch(self.descriptor,'machine-1234')
                spawn.assert_not_awaited()
            self.daemon.domain.world_worker_pause.assert_called_once_with(
                self.run,'machine-1234',self.generation,'native_evidence_conflict')
        asyncio.run(run())

    def test_persisted_chain_detects_deleted_or_reordered_event(self):
        room=WorldRoom(self.supervisor,self.descriptor,self.root)
        packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('end_turn',{'next_player_number':'2'})])])])
        room.append(packet)
        packet.children[0].children[0].attrs['from_side']='2'
        packet.children[0].children[0].children[0].attrs['next_player_number']='1'
        room.append(packet)
        loaded=WorldRoom(self.supervisor,self.descriptor,self.root)
        self.assertEqual((loaded.count,loaded.turn,loaded.current_side),(2,2,1))
        path=self.root/'commands.jsonl';lines=path.read_bytes().splitlines();path.write_bytes(lines[1]+b'\n')
        with self.assertRaises(WireError):WorldRoom(self.supervisor,self.descriptor,self.root)

    def test_human_cannot_send_worker_terminal_or_ai_side_commands(self):
        async def run():
            room=WorldRoom(self.supervisor,self.descriptor,self.root);room.started=True
            room.available.set()
            async def authorize(peer):pass
            room.authorize=authorize
            peer=WorldPeer(None,None,self.actor,'x'*43);peer.loaded=True;peer.sides=[1]
            worker=SimpleNamespace(loaded=True);room.peers['worker']=worker
            with self.assertRaises(WireError):
                await room.command(peer,Node(children=[Node('world_native_terminal',{'scenario_sha256':'a'*64})]))
            with self.assertRaises(WireError):
                await room.command(peer,Node(children=[Node('turn',children=[Node('command',{'from_side':'2'},[Node('end_turn')])])]))
            self.assertEqual(room.count,0)
        asyncio.run(run())

    def test_end_turn_cannot_skip_enemy_or_repeat_the_own_side(self):
        async def run():
            room=WorldRoom(self.supervisor,self.descriptor,self.root);room.started=True
            room.available.set();room.authorize=AsyncMock()
            peer=WorldPeer(None,None,self.actor,'x'*43);peer.loaded=True;peer.sides=[1]
            room.peers['worker']=SimpleNamespace(loaded=True,send=AsyncMock())
            for target in ('1','3','99','-1'):
                packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},
                    [Node('end_turn',{'next_player_number':target})])])])
                with self.assertRaises(WireError):await room.command(peer,packet)
            self.assertEqual((room.count,room.current_side),(0,1))
            packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},
                [Node('end_turn',{'next_player_number':'2'})])])])
            await room.command(peer,packet)
            self.assertEqual((room.count,room.current_side),(1,2))
        asyncio.run(run())

    def proof(self):
        row={'sequence':0,'run_id':self.run,'generation':self.generation,'previous':'0'*64,
             'instance_id':'h','kind':'deployed','unit_type':'Fighter','amount':0}
        row['sha256']=sha(canonical(row));ledger=[row]
        proof={'format':1,'run_id':self.run,'generation':self.generation,'scenario_sha256':'a'*64,
            'replay_sha256':sha(b'replay'),'ledger_sha256':sha(canonical(ledger)),'ledger':ledger,
            'event_count':1,'terminal':'leaders_defeated','outcome':'win','winner_team_id':'a',
            'units':[{'instance_id':'h','earned_xp':0,'final_type':'Fighter','final_xp':0,'dead':False,'deployed':True}],
            'sync_valid':True,'native_end':'victory','command_chain_sha256':'b'*64,'command_count':20,
            'combat_verified':True,'completed_rounds':2}
        (self.root/'evidence.json').write_bytes(canonical(proof));(self.root/'replay.gz').write_bytes(b'replay')
        return proof

    def test_missing_replay_and_forged_ledger_never_reach_domain_summary(self):
        proof=self.proof();cursor={'sha256':'b'*64,'count':20,'completed_rounds':2}
        self.assertEqual(validate_evidence(self.root,self.descriptor,cursor,'a'*64)['outcome'],'win')
        proof['units'][0]['earned_xp']=999
        (self.root/'evidence.json').write_bytes(canonical(proof))
        with self.assertRaises(ValueError):validate_evidence(self.root,self.descriptor,cursor,'a'*64)
        self.proof();(self.root/'replay.gz').unlink()
        with self.assertRaises(ValueError):validate_evidence(self.root,self.descriptor,cursor,'a'*64)

    def test_truncated_native_cursor_or_wrong_generation_is_rejected(self):
        self.proof()
        with self.assertRaises(ValueError):validate_evidence(self.root,self.descriptor,{'sha256':'b'*64,'count':19,'completed_rounds':2},'a'*64)
        descriptor=copy.deepcopy(self.descriptor);descriptor['generation']=str(uuid4())
        with self.assertRaises(ValueError):validate_evidence(self.root,descriptor,{'sha256':'b'*64,'count':20,'completed_rounds':2},'a'*64)

    def test_observer_terminal_requires_a_scoped_witness_without_ai_sides(self):
        proof=self.proof();proof['native_end']='observer_end'
        (self.root/'evidence.json').write_bytes(canonical(proof))
        cursor={'sha256':'b'*64,'count':20,'completed_rounds':2}
        with self.assertRaises(ValueError):validate_evidence(self.root,self.descriptor,cursor,'a'*64)
        descriptor=copy.deepcopy(self.descriptor)
        descriptor['sides'][1]['controller']='human'
        self.assertEqual(validate_evidence(self.root,descriptor,cursor,'a'*64)['outcome'],'win')

    def test_missing_tail_cannot_be_mistaken_for_complete_history(self):
        room=WorldRoom(self.supervisor,self.descriptor,self.root)
        packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('move')])])])
        room.append(packet);room.append(packet)
        path=self.root/'commands.jsonl';path.write_bytes(path.read_bytes().splitlines()[0]+b'\n')
        with self.assertRaises(WireError):WorldRoom(self.supervisor,self.descriptor,self.root)

    def test_total_history_bound_rejects_before_writing(self):
        room=WorldRoom(self.supervisor,self.descriptor,self.root)
        room.history_bytes=128*1024*1024
        packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('move')])])])
        with self.assertRaises(WireError):room.append(packet)
        self.assertEqual(room.count,0)
        self.assertFalse((self.root/'commands.jsonl').exists())

    def test_commands_wait_until_same_human_has_loaded_again(self):
        async def run():
            room=WorldRoom(self.supervisor,self.descriptor,self.root);room.started=True
            room.authorize=AsyncMock()
            peer=WorldPeer(None,None,self.actor,'x'*43);peer.loaded=True;peer.sides=[1]
            room.peers['worker']=SimpleNamespace(loaded=True,send=AsyncMock())
            packet=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[Node('end_turn')])])])
            task=asyncio.create_task(room.command(peer,packet))
            await asyncio.sleep(.01);self.assertFalse(task.done());self.assertEqual(room.count,0)
            room.peers[self.actor]=peer;room.update_availability()
            await asyncio.wait_for(task,1);self.assertEqual((room.count,room.current_side),(1,2))
        asyncio.run(run())

    def test_authorized_completed_replay_survives_daemon_restart(self):
        async def run():
            directory=self.supervisor.root/self.run/self.generation;directory.mkdir(parents=True)
            room=WorldRoom(self.supervisor,self.descriptor,directory)
            attempt=directory/'worker-retained';attempt.mkdir();recording=attempt/'replay.gz';recording.write_bytes(b'bounded replay')
            room.completed_replay=recording;room.completed=True;room.persist()
            self.daemon.domain=SimpleNamespace(world_replay_authorize=lambda *args:{'generation':self.generation,'replay_sha256':sha(b'bounded replay')})
            self.daemon.auth=SimpleNamespace(validate_token=lambda *args:{'_id':self.actor})
            packets=[]
            async def capture(writer,packet):packets.append(packet)
            async def request(*args):return Node(children=[Node('world_replay_get',{'offset':'0'})])
            with patch('alliance.world_execution.send',capture),patch('alliance.world_execution.receive',request):
                await download_world(self.supervisor,None,None,self.actor,'x'*43,self.run)
            self.assertEqual([p.children[0].name for p in packets],['world_replay_info','world_replay_data'])
            recording.write_bytes(b'changed replay')
            with self.assertRaises(WireError):await download_world(self.supervisor,None,None,self.actor,'x'*43,self.run)
        asyncio.run(run())

if __name__=='__main__':unittest.main()
