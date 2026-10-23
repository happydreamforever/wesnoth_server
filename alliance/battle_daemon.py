"""Authenticated fixed-seat Alliance relay for trusted offline players.

This process validates seat/turn ownership and records the actual shared wire
history. It does not independently simulate combat. Result agreement and fixed
rewards are enforced transactionally by AllianceService, never by local practice.
"""
from __future__ import annotations
import argparse
import base64
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
from uuid import uuid4

from pymongo import MongoClient
from .auth import AuthService, AuthError
from .config import Settings
from .domain import AllianceService, DomainError
from .deployment import owned_runtime
from .battle_wire import Node, WireError, message, receive, send, serialize, parse
from tools.alliance_transport import verify_identity

MAX_HISTORY = 128 * 1024 * 1024
MAX_REPLAY = 32 * 1024 * 1024
MAX_ROOMS = 128
# Synchronized surrender and mutual draw are exercised with actual native
# engines; the command still requires the recorded captain's current turn.
CAPTAIN_COMMANDS_ENABLED = True
ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Battle storage must not traverse links.')
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError('Battle storage must not use hard links.')
    return path


def write_json(path, value):
    path = safe_path(path)
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, sort_keys=True, separators=(',', ':'))
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        # Leave an interrupted write for diagnosis; never erase the old record.
        raise


def captain_action(root):
    """Recognize only the confirmed synchronized native captain command."""
    actions = [child for turn in root.children if turn.name == 'turn'
               for command in turn.children for child in command.children
               if child.name == 'custom_command' and child.attrs.get('name') == 'alliance_captain_v1']
    if not actions:
        return None
    if root.attrs or len(root.children) != 1 or root.children[0].name != 'turn':
        raise WireError('Invalid captain command packet.')
    turn = root.children[0]
    if (turn.attrs or not 1 <= len(turn.children) <= 512 or
            any(command.name != 'command' or not command.children for command in turn.children)):
        raise WireError('A captain action requires synchronized commands.')
    # Stock block_undo flushes any preceding move/recruit commands together with
    # the non-undoable captain decision. Bind the whole same-turn packet so its
    # exact ordered prefix is recovered if the database commit precedes fsync.
    command = turn.children[-1]
    if len(actions) != 1 or actions[0] not in command.children:
        raise WireError('The captain action must be the final synchronized command.')
    if any(child.name == 'end_turn' for earlier in turn.children[:-1] for child in earlier.children):
        raise WireError('A captain action cannot follow a turn change in the same packet.')
    if len(actions) != 1 or any(child is not actions[0] and not re.fullmatch(r'checkup[0-9]*', child.name) for child in command.children):
        raise WireError('A captain action cannot contain another game action.')
    action = actions[0]
    if action.attrs != {'name': 'alliance_captain_v1'} or len(action.children) != 1 or action.children[0].name != 'data':
        raise WireError('Invalid captain command data.')
    data = action.children[0]
    if set(data.attrs) != {'action'} or data.children or data.attrs['action'] not in ('surrender','offer_draw','withdraw_draw'):
        raise WireError('Invalid captain action.')
    if command.attrs.get('dependent') == 'yes':
        raise WireError('A captain action cannot be an out-of-turn choice.')
    return data.attrs['action']


@contextmanager
def process_lock(path):
    path = safe_path(path)
    stream = path.open('a+b')
    try:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


class Peer:
    def __init__(self, reader, writer, account, token, upload_only=False):
        self.reader, self.writer, self.account = reader, writer, account
        self.token = token
        self.upload = None
        self.side = 0
        self.loaded = False
        self.upload_only = upload_only
        self.lock = asyncio.Lock()

    async def send(self, node):
        async with self.lock:
            await send(self.writer, node)

    def close(self):
        self.writer.close()


class Room:
    def __init__(self, daemon, run_id, directory, record):
        self.daemon, self.run_id, self.directory, self.record = daemon, run_id, directory, record
        self.generation = record['generation']
        self.peers = {}
        self.lock = asyncio.Lock()
        self.history = []
        self.history_bytes = 0
        self.replay_bytes = 0
        self.replay_commands = 0
        self.current_side = 1
        self.current_turn = 1
        self.last_choice = -1
        self.choices = {}
        self.chain = '0'*64
        self.event_hashes = set()
        self.failed = False
        self.verified_replays = set()
        history = safe_path(directory/'events.jsonl')
        if history.exists():
            if history.stat().st_size > MAX_HISTORY:
                raise ValueError('Retained room history exceeds its bound.')
            with history.open(encoding='utf-8') as stream:
                for line in stream:
                    if len(line.encode()) > 3*1024*1024:
                        raise ValueError('Retained event exceeds its bound.')
                    event = json.loads(line)
                    digest = event.pop('sha256')
                    body = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
                    if event['previous'] != self.chain or hashlib.sha256(body).hexdigest() != digest:
                        raise ValueError('Retained room history is inconsistent.')
                    self.chain = digest
                    self.event_hashes.add(digest)
                    node = parse(event['wml'])
                    self.count_replay(node)
                    self.history.append(node)
                    self.history_bytes += len(line.encode())
                    self.track(node)

    def track(self, node):
        for turn in node.children:
            if turn.name != 'turn':
                continue
            for command in turn.children:
                for value in command.children:
                    if value.name == 'end_turn':
                        next_side = value.attrs.get('next_player_number')
                        next_side = int(next_side) if next_side is not None else 0
                        if next_side <= 0:
                            next_side = self.current_side + 1
                        if not 1 <= next_side <= self.size + 1:
                            raise WireError('Invalid next side.')
                        if next_side > self.size:
                            self.current_turn += 1
                        self.current_side = (next_side - 1) % self.size + 1
                    if value.name == 'random_seed':
                        self.last_choice = max(self.last_choice, int(value.attrs['request_id']))
                        self.choices[int(value.attrs['request_id'])] = node

    @property
    def size(self):
        return self.record['battle']['map']['size']*2

    def count_replay(self, node):
        turns = [child for child in node.children if child.name == 'turn']
        byte_count = len(serialize(node).encode('utf-8')) if turns else 0
        commands = sum(len(turn.children) for turn in turns)
        if self.replay_bytes + byte_count > MAX_REPLAY or self.replay_commands + commands > 100000:
            raise WireError('Shared replay limit reached. Preserve the run for review.')
        self.replay_bytes += byte_count
        self.replay_commands += commands

    def persist(self):
        try:
            write_json(self.directory/'room.json', self.record)
        except BaseException:
            self.freeze()
            raise

    def freeze(self):
        self.failed = True
        for peer in self.peers.values(): peer.close()

    def append(self, node):
        event = {'previous': self.chain, 'wml': serialize(node)}
        body = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
        digest = hashlib.sha256(body).hexdigest()
        event['sha256'] = digest
        line = json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n'
        if self.history_bytes+len(line.encode()) > MAX_HISTORY:
            raise WireError('Room history limit reached; preserve the run for review.')
        self.count_replay(node)
        try:
            with safe_path(self.directory/'events.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(line); stream.flush(); os.fsync(stream.fileno())
            self.chain = digest
            self.event_hashes.add(digest)
            self.history_bytes += len(line.encode())
            self.history.append(node)
            self.track(node)
        except BaseException:
            self.freeze()
            raise

    async def broadcast(self, node, exclude=None):
        # Separate writer locks retain frame boundaries. One failed peer does not
        # discard already persisted commands; that exact side can reconnect.
        peers = [peer for aid, peer in self.peers.items() if aid != exclude and peer.loaded]
        replies = await asyncio.gather(*(peer.send(node) for peer in peers), return_exceptions=True)
        for peer, reply in zip(peers, replies):
            if isinstance(reply, BaseException):
                peer.close()

    async def admit(self, peer):
        async with self.lock:
            if self.failed:
                raise WireError('Retained room writes require review before reconnecting.')
            aid = peer.account['_id']
            if aid in self.peers:
                raise WireError('This player already has a connected seat.')
            admission = self.daemon.domain.shared_evidence_admission if peer.upload_only else self.daemon.domain.shared_admission
            result = await asyncio.to_thread(admission, aid, self.run_id, self.generation)
            if result['battle']['id'] != self.run_id:
                raise WireError('Room identifier differs.')
            peer.side = result['assigned_side']
            self.peers[aid] = peer
            reconnect = result['room_state'] in ('running', 'completed')
            if reconnect and self.record['state'] != result['room_state']:
                self.record['state']=result['room_state']
                self.persist()
            await peer.send(message('alliance_room', descriptor=json.dumps(self.record['battle'], separators=(',', ':')),
                                    seed=self.record['seed'], side=peer.side, current_side=self.current_side,
                                    current_turn=self.current_turn, reconnect='yes' if reconnect else 'no'))
            return reconnect

    async def loaded(self, peer, digest):
        async with self.lock:
            if self.failed:
                raise WireError('Retained room writes require review before starting.')
            actor = await asyncio.to_thread(self.daemon.auth.validate_token, peer.token, 'player')
            if actor['_id'] != peer.account['_id']:
                raise WireError('Battle session identity changed.')
            await asyncio.to_thread(self.daemon.domain.shared_admission, actor['_id'], self.run_id, self.generation)
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise WireError('Invalid scenario digest.')
            expected = self.record.get('scenario_sha256', '')
            if expected and expected != digest:
                raise WireError('Installed battle scenario differs between players.')
            if not expected:
                self.record['scenario_sha256'] = digest
                self.persist()
            peer.loaded = True
            if self.record['state'] == 'running':
                for event in self.history:
                    if any(child.name == 'turn' for child in event.children):
                        await peer.send(event)
                await peer.send(message('alliance_start', reconnect='yes'))
                return
            if len(self.peers) != self.size or any(not other.loaded for other in self.peers.values()):
                await peer.send(message('alliance_waiting', connected=len(self.peers), required=self.size))
                return
            # Each seat may have waited while the other players loaded. A
            # password reset/logout during that wait must not start its game.
            for other in self.peers.values():
                try:
                    current = await asyncio.to_thread(self.daemon.auth.validate_token, other.token, 'player')
                except AuthError:
                    other.close()
                    raise
                if current['_id'] != other.account['_id']:
                    raise WireError('A loaded seat session changed.')
            result = await asyncio.to_thread(self.daemon.domain.shared_start, self.run_id, self.generation,
                                             list(self.peers), digest)
            if result['state'] != 'running':
                raise WireError('Server did not confirm battle start.')
            self.record['state'] = 'running'
            self.persist()
            await self.broadcast(message('alliance_start', reconnect='no'))

    async def command(self, peer, root):
        if root.attrs or len(root.children) != 1:
            raise WireError('Expected one battle message.')
        node = root.children[0]
        if node.name == 'alliance_loaded':
            if set(node.attrs) != {'scenario_sha256'} or node.children or peer.loaded or peer.upload_only:
                raise WireError('Invalid loaded acknowledgement.')
            await self.loaded(peer, node.attrs['scenario_sha256'])
            return
        async with self.lock:
            if self.failed:
                raise WireError('Retained room writes require review before continuing.')
            evidence_only = node.name in ('alliance_replay_begin','alliance_replay_chunk','alliance_result')
            if ((self.record['state'] != 'running' and not (self.record['state']=='completed' and peer.upload_only and evidence_only)) or
                    (peer.upload_only and not evidence_only) or (not peer.loaded and not evidence_only)):
                raise WireError('Battle has not started.')
            # A revoked or suspended account must not continue issuing commands.
            actor = await asyncio.to_thread(self.daemon.auth.validate_token, peer.token, 'player')
            if actor['_id'] != peer.account['_id']:
                raise WireError('Battle session identity changed.')
            admission = self.daemon.domain.shared_evidence_admission if peer.upload_only else self.daemon.domain.shared_admission
            await asyncio.to_thread(admission, peer.account['_id'], self.run_id, self.generation)
            if node.name == 'alliance_replay_begin':
                if set(node.attrs) != {'bytes','sha256'} or node.children or peer.upload is not None:
                    raise WireError('Invalid replay upload.')
                count=int(node.attrs['bytes'])
                digest=node.attrs['sha256']
                if not 1<=count<=32*1024*1024 or not re.fullmatch(r'[0-9a-f]{64}',digest):
                    raise WireError('Invalid replay evidence size or hash.')
                if self.record['state']=='completed':
                    run=await asyncio.to_thread(self.daemon.domain.get_run,self.run_id)
                    if run['shared_room']['result_reports'][peer.account['_id']]['replay_sha256']!=digest:
                        raise WireError('Completed result evidence differs.')
                filename=peer.account['_id']+'-'+uuid4().hex+'.replay.partial'
                path=safe_path(self.directory/filename)
                with path.open('xb'):
                    pass
                peer.upload={'path':path,'bytes':count,'sha256':digest,'received':0,'digest':hashlib.sha256()}
                await peer.send(message('alliance_replay_ready',offset=0))
            elif node.name == 'alliance_replay_chunk':
                if set(node.attrs)!={'offset','data'} or node.children or peer.upload is None:
                    raise WireError('Invalid replay chunk.')
                upload=peer.upload
                content=base64.b64decode(node.attrs['data'],validate=True)
                if not 1<=len(content)<=24000 or int(node.attrs['offset'])!=upload['received'] or upload['received']+len(content)>upload['bytes']:
                    raise WireError('Replay chunk sequence differs.')
                with upload['path'].open('ab') as stream:
                    stream.write(content);stream.flush();os.fsync(stream.fileno())
                upload['digest'].update(content);upload['received']+=len(content)
                await peer.send(message('alliance_replay_ready',offset=upload['received']))
            elif node.name == 'alliance_result':
                if set(node.attrs)!={'winner_team_id','draw','replay_sha256'} or node.children or peer.upload is None:
                    raise WireError('A terminal result requires its recorded replay.')
                upload=peer.upload
                if upload['received']!=upload['bytes'] or upload['digest'].hexdigest()!=upload['sha256'] or node.attrs['replay_sha256']!=upload['sha256']:
                    raise WireError('Replay evidence hash differs.')
                if node.attrs['draw'] not in ('yes','no'):
                    raise WireError('Invalid outcome.')
                destination=safe_path(self.directory/(peer.account['_id']+'-'+upload['sha256']+'.replay'))
                if destination.exists():
                    if destination.stat().st_size != upload['bytes'] or hashlib.sha256(destination.read_bytes()).hexdigest()!=upload['sha256']:
                        raise WireError('Retained replay differs.')
                else:
                    os.replace(upload['path'],destination)
                review=await asyncio.to_thread(self.daemon.domain.shared_report_result,peer.account['_id'],self.run_id,self.generation,
                    node.attrs['winner_team_id'] or None,node.attrs['draw']=='yes',upload['sha256'])
                self.record.setdefault('replays',{})[peer.account['_id']]={'filename':destination.name,'sha256':upload['sha256'],'bytes':upload['bytes']}
                self.verified_replays.add((peer.account['_id'], upload['sha256']))
                self.persist();peer.upload=None
                if upload['path'].exists():
                    # Exact duplicate retry used the already verified final
                    # recording. Only its new, owned upload scratch is removed.
                    upload['path'].unlink()
                await peer.send(message('alliance_result_saved',run_id=self.run_id,state=review['review_state']))
            elif node.name == 'request_choice':
                if set(node.attrs) != {'request_id'} or len(node.children)!=1 or node.children[0].name!='random_seed':
                    raise WireError('Only the fixed battle random choice is supported.')
                request_id = int(node.attrs['request_id'])
                if request_id in self.choices:
                    # Other clients may request the same globally sequenced seed;
                    # do not rebroadcast it or add it twice to the replay.
                    return
                if request_id < 0 or (self.last_choice < 0 and request_id not in (0,1)) or (self.last_choice >= 0 and request_id != self.last_choice+1):
                    raise WireError('Random choice sequence differs.')
                response = Node(children=[Node('turn', children=[Node('command',
                    {'from_side':'server','dependent':'yes'}, [Node('random_seed',
                    {'new_seed':secrets.token_hex(4),'request_id':request_id})])])])
                self.append(response)
                await self.broadcast(response)
            elif node.name == 'turn':
                if node.attrs or not node.children or len(node.children)>512:
                    raise WireError('Invalid turn commands.')
                # Validate the entire batch before writing or relaying anything.
                simulated_side = self.current_side
                captain_event = captain_action(root)
                if captain_event and not CAPTAIN_COMMANDS_ENABLED:
                    raise WireError('The native captain command is not available in this build.')
                if captain_event and peer.side != self.current_side:
                    raise WireError('A captain action belongs to its active side turn.')
                for command in node.children:
                    if command.name!='command' or not command.children:
                        raise WireError('Invalid turn command.')
                    source = command.attrs.get('from_side')
                    if source is not None and source != str(peer.side):
                        raise WireError('A command cannot impersonate another side.')
                    names = [item.name for item in command.children]
                    if any(name in ('random_seed','change_controller','change_controller_wml','add_side') or
                           name.startswith('debug_') for name in names):
                        raise WireError('A client cannot change fixed battle ownership.')
                    permitted_async = len(names)==1 and names[0] in ('speak','label','clear_labels','rename','countdown_update')
                    dependent = (command.attrs.get('dependent')=='yes' and source==str(peer.side) and
                                 len(names)==1 and names[0] not in ('end_turn','init_side'))
                    if peer.side != simulated_side and not permitted_async and not dependent:
                        raise WireError('The command does not belong to this turn.')
                    for child in command.children:
                        if child.name=='speak':
                            child.attrs['id']=peer.account['username']
                            child.attrs['side']=str(peer.side)
                            if len(child.attrs.get('message',''))>500:
                                raise WireError('Chat message too large.')
                            # Private chat is routed by explicit authenticated team.
                            if child.attrs.get('to_sides'):
                                raise WireError('Use captain orders for private team communication.')
                        if child.name=='end_turn':
                            next_side=int(child.attrs.get('next_player_number','0'))
                            next_side=next_side if next_side>0 else simulated_side+1
                            if not 1<=next_side<=self.size+1:
                                raise WireError('Invalid next side.')
                            simulated_side=(next_side-1)%self.size+1
                if captain_event:
                    replay = {'previous': self.chain, 'wml': serialize(root)}
                    binding = hashlib.sha256(json.dumps(replay, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    try:
                        await asyncio.to_thread(self.daemon.domain.shared_captain_command,
                            peer.account['_id'], self.run_id, self.generation, binding, captain_event, replay)
                    except DomainError:
                        raise
                    except BaseException:
                        # Commit response loss is uncertain. Freeze rather than
                        # letting later commands pass the durable pending one.
                        self.freeze()
                        raise
                try:
                    self.append(root)
                except BaseException:
                    if captain_event:
                        # Even preflight limits can fail before append's own
                        # write guard. No later command may pass the committed
                        # captain event until exact recovery completes it.
                        self.freeze()
                    raise
                await self.broadcast(root, exclude=peer.account['_id'])
            elif node.name in ('leave_game','stop_updates'):
                peer.close()
            elif node.name=='info':
                # The real play controller emits this advisory before its
                # replay upload. It proves no outcome and earns no reward.
                if (set(node.attrs)!={'type','condition','result'} or node.children or
                        node.attrs['type']!='termination' or node.attrs['condition']!='game over' or
                        node.attrs['result'] not in ('victory','defeat')):
                    raise WireError('Invalid game termination advisory.')
            elif node.name=='message':
                text=node.attrs.get('message','')
                if not 1<=len(text)<=500 or node.children:
                    raise WireError('Invalid chat message.')
                response=message('message',message=text,sender=peer.account['username'],side=peer.side)
                self.append(response);await self.broadcast(response)
            else:
                raise WireError('Unsupported shared battle command.')


class BattleDaemon:
    def __init__(self, db, storage, context):
        self.db, self.storage, self.context = db, safe_path(storage), context
        self.auth, self.domain = AuthService(db), AllianceService(db)
        self.rooms = {}
        self.room_lock = asyncio.Lock()
        self.connections = 0
        self.storage.mkdir(mode=0o700, parents=True, exist_ok=True)

    def load_record(self, run_id, directory, run):
        marker = safe_path(directory/'room.json')
        if not marker.is_file() or marker.stat().st_size > 65536:
            raise WireError('Room metadata is missing or exceeds its limit.')
        record = json.loads(marker.read_text(encoding='utf-8'))
        binding = run.get('shared_room', {})
        if (record.get('format') != 1 or record.get('run_id') != run_id or
                not ID.fullmatch(record.get('generation', '')) or record['generation'] != binding.get('generation') or
                not re.fullmatch(r'[0-9a-f]{8}', record.get('seed', '')) or record['battle'].get('id') != run_id):
            raise WireError('Room metadata differs from its database binding.')
        saved = {(p['id'], team['id'], p['side'], p['unit_type'], p['level'])
                 for team in record['battle']['teams'] for p in team['players']}
        actual = {(p['account_id'], p['team_id'], p['side'], p['leader']['unit_type'], p['leader']['level'])
                  for p in run['participants']}
        if saved != actual or record['battle']['map']['id'] != run['map_id']:
            raise WireError('Retained fixed lineup differs from the database.')
        if run['state'] == 'running':
            if record.get('scenario_sha256') != binding.get('scenario_sha256'):
                raise WireError('Retained scenario differs from the running database.')
            record['state'] = 'running'
        return record

    def recover_replays(self, room, run):
        """Recover the file-before-database-before-marker result write sequence."""
        changed = False
        for actor, report in run.get('shared_room', {}).get('result_reports', {}).items():
            digest = report['replay_sha256']
            if not ID.fullmatch(actor) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise WireError('Stored result evidence is invalid.')
            if (actor, digest) in room.verified_replays:
                continue
            path = safe_path(room.directory/(actor+'-'+digest+'.replay'))
            if not path.is_file() or not 1 <= path.stat().st_size <= 32*1024*1024:
                continue  # Keep reservations: missing evidence requires review.
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise WireError('Stored result recording differs.')
            value = {'filename': path.name, 'sha256': digest, 'bytes': path.stat().st_size}
            if room.record.setdefault('replays', {}).get(actor) != value:
                room.record['replays'][actor] = value
                changed = True
            room.verified_replays.add((actor, digest))
        if changed:
            room.persist()

    def recover_captain_commands(self, room, run):
        """Complete a committed command's missing event append exactly once."""
        commands = run.get('shared_room', {}).get('captain_commands', {})
        if len(commands) > 128:
            raise WireError('Retained captain command limit exceeded.')
        pending = {key: value for key, value in commands.items() if key not in room.event_hashes}
        while pending:
            candidates = [(key, value) for key, value in pending.items() if value['replay']['previous'] == room.chain]
            if len(candidates) != 1:
                raise WireError('Retained captain commands do not continue the event history.')
            binding, receipt = candidates[0]
            replay = receipt['replay']
            if (set(replay) != {'previous','wml'} or len(replay['wml'].encode()) > 65536 or
                    hashlib.sha256(json.dumps(replay,sort_keys=True,separators=(',', ':')).encode()).hexdigest() != binding):
                raise WireError('Retained captain command digest differs.')
            packet = parse(replay['wml'])
            if captain_action(packet) != receipt['event']:
                raise WireError('Retained captain action differs.')
            actor = next((item for item in run['participants'] if item['account_id']==receipt['actor_id']),None)
            if (actor is None or run['shared_room']['captains'].get(actor['team_id']) != receipt['actor_id'] or
                    actor['side'] != room.current_side or
                    any(command.attrs.get('from_side') not in (None,str(actor['side']))
                        for command in packet.children[0].children)):
                raise WireError('Retained captain command ownership differs.')
            room.append(packet)
            del pending[binding]

    async def recover_running(self):
        """Resume settlement after restart without requiring another player join."""
        runs = await asyncio.to_thread(lambda: list(self.db.game_runs.find(
            {'kind': 'alliance', 'state': 'running', 'shared_room.state': 'running'}).limit(MAX_ROOMS+1)))
        if len(runs) > MAX_ROOMS:
            raise WireError('Too many retained running rooms.')
        async with self.room_lock:
            for run in runs:
                run_id = run['_id']
                if not ID.fullmatch(run_id):
                    raise WireError('Invalid retained run identifier.')
                if run_id not in self.rooms:
                    await self.reserve_room_slot()
                    directory = safe_path(self.storage/run_id)
                    record = self.load_record(run_id, directory, run)
                    self.rooms[run_id] = Room(self, run_id, directory, record)
                room = self.rooms[run_id]
                async with room.lock:
                    if room.failed:
                        continue
                    self.recover_captain_commands(room, run)
                    self.recover_replays(room, run)

    async def reserve_room_slot(self):
        """Bound all loads, including retained completed evidence retries."""
        inactive = [key for key, value in self.rooms.items() if not value.peers]
        if inactive:
            closed = await asyncio.to_thread(lambda: list(self.db.game_runs.find(
                {'_id': {'$in': inactive}, 'state': {'$in': ['completed','cancelled']}}, {'_id': 1})))
            for item in closed: self.rooms.pop(item['_id'], None)
        if len(self.rooms) >= MAX_ROOMS:
            raise WireError('Room limit reached.')

    async def room(self, account_id, run_id, upload_only=False):
        if not ID.fullmatch(run_id):
            raise WireError('Invalid battle identifier.')
        async with self.room_lock:
            directory=safe_path(self.storage/run_id)
            marker=safe_path(directory/'room.json')
            run = await asyncio.to_thread(self.domain.get_run, run_id)
            binding = run.get('shared_room', {})
            renew = run['state'] == 'draft' and (binding.get('state') == 'cancelled' or
                (binding.get('expires_at') and binding['expires_at'] <= datetime.now(timezone.utc)))
            if renew and not upload_only:
                generation = str(uuid4())
                # Authenticate selection and fence the old generation in the
                # transaction before changing any retained files or sockets.
                # A competing all-loaded start wins or loses atomically.
                await asyncio.to_thread(self.domain.shared_prepare,account_id,run_id,generation)
                previous = self.rooms.pop(run_id, None)
                if previous:
                    async with previous.lock:
                        for old_peer in previous.peers.values(): old_peer.close()
                if directory.exists():
                    archived = safe_path(self.storage/(run_id+'-before-'+uuid4().hex))
                    os.replace(directory, archived)
                marker = directory/'room.json'
            elif run_id in self.rooms:
                return self.rooms[run_id]
            await self.reserve_room_slot()
            if marker.exists():
                record = self.load_record(run_id, directory, run)
                admission = self.domain.shared_evidence_admission if upload_only else self.domain.shared_admission
                await asyncio.to_thread(admission,account_id,run_id,record['generation'])
            else:
                if run['state'] != 'draft' or upload_only:
                    raise WireError('Running room evidence is unavailable. Preserve the run for review.')
                # A process can stop after prepare commits but before its first
                # marker is written. Reuse that unexpired preparation only;
                # running rooms can never synthesize missing game history.
                if not renew:
                    generation = binding['generation'] if binding else str(uuid4())
                result=await asyncio.to_thread(self.domain.shared_prepare,account_id,run_id,generation)
                if directory.exists():
                    os.replace(directory,safe_path(self.storage/(run_id+'-incomplete-'+uuid4().hex)))
                directory.mkdir(mode=0o700,exist_ok=False)
                record={'format':1,'run_id':run_id,'generation':generation,'battle':result['battle'],
                        'seed':secrets.token_hex(4),'state':'preparing','scenario_sha256':''}
                write_json(marker,record)
            room=Room(self,run_id,directory,record)
            self.recover_captain_commands(room, run)
            self.rooms[run_id]=room
            return room

    async def settle_ready(self):
        while True:
            await asyncio.sleep(2)
            try:
                await self.recover_running()
            except Exception as error:
                print('BATTLE RECOVERY PENDING: '+type(error).__name__,flush=True)
            for room in list(self.rooms.values()):
                if room.failed or room.record['state'] != 'running':
                    continue
                try:
                    participants=[p['id'] for team in room.record['battle']['teams'] for p in team['players']]
                    if set(room.record.get('replays',{})) != set(participants):
                        continue
                    if {actor for actor, _ in room.verified_replays} != set(participants):
                        continue
                    await asyncio.to_thread(self.domain.shared_finish,room.run_id,room.generation)
                    async with room.lock:
                        room.record['state']='completed';room.persist()
                        await room.broadcast(message('message',sender='Alliance',side=0,message='Battle result settled. Reopen Alliance to view your leader and team rewards.'))
                except DomainError:
                    pass
                except Exception as error:
                    print('BATTLE SETTLEMENT PENDING: '+type(error).__name__,flush=True)

    async def download_replay(self, reader, writer, account_id, token, run_id):
        """Stream an existing completed recording without loading a room."""
        access = await asyncio.to_thread(self.domain.shared_replay_access, account_id, run_id)
        if (not ID.fullmatch(access['account_id']) or
                not re.fullmatch(r'[0-9a-f]{64}', access['sha256'])):
            raise WireError('Stored replay binding is invalid.')
        path = safe_path(self.storage/run_id/(access['account_id']+'-'+access['sha256']+'.replay'))
        with path.open('rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not 1 <= metadata.st_size <= MAX_REPLAY:
                raise WireError('Stored replay size or type is invalid.')
            digest = hashlib.sha256()
            remaining = metadata.st_size
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk: raise WireError('Stored recording was truncated.')
                digest.update(chunk)
                remaining -= len(chunk)
            if stream.read(1) or digest.hexdigest() != access['sha256']:
                raise WireError('Stored recording differs from its completed result.')
            stream.seek(0)
            await send(writer, message('alliance_replay_info', run_id=run_id,
                account_id=access['account_id'], bytes=metadata.st_size, sha256=access['sha256'],
                format='wesnoth-replay-v1'))
            offset = 0
            while offset < metadata.st_size:
                root = await receive(reader, 30)
                request = root.one('alliance_replay_get')
                if root.attrs or len(root.children) != 1 or set(request.attrs) != {'offset'} or request.children or request.attrs['offset'] != str(offset):
                    raise WireError('Replay download sequence differs.')
                actor = await asyncio.to_thread(self.auth.validate_token, token, 'player')
                if actor['_id'] != account_id:
                    raise WireError('Replay session identity changed.')
                current = await asyncio.to_thread(self.domain.shared_replay_access, account_id, run_id)
                if current != access:
                    raise WireError('Replay authorization changed.')
                chunk = stream.read(min(24000, metadata.st_size-offset))
                if not chunk:
                    raise WireError('Stored replay was truncated.')
                await send(writer, message('alliance_replay_data', offset=offset,
                                          data=base64.b64encode(chunk).decode('ascii')))
                offset += len(chunk)

    async def handle(self, reader, writer):
        peer=room=None
        self.connections+=1
        try:
            if self.connections>32:
                return
            preamble=await asyncio.wait_for(reader.readexactly(4),10)
            if preamble!=b'\0\0\0\1':
                return
            writer.write(b'\0\0\0\0');await writer.drain()
            await writer.start_tls(self.context,ssl_handshake_timeout=10)
            root=await receive(reader,10)
            if root.attrs or len(root.children)!=1:
                raise WireError('Invalid handshake.')
            node=root.children[0]
            if node.name=='alliance_health' and not node.attrs and not node.children:
                await asyncio.to_thread(self.db.command,'ping')
                await send(writer,message('alliance_health',service='alliance-battles',api=1))
                return
            if node.name!='alliance_join' or set(node.attrs)!={'run_id','token','intent'} or node.children or node.attrs['intent'] not in ('play','result_retry','replay_download'):
                raise WireError('Invalid join request.')
            token=node.attrs.pop('token')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
                raise WireError('Invalid session.')
            account=await asyncio.to_thread(self.auth.validate_token,token,'player')
            if account.get('role')!='player':
                raise WireError('A player account is required.')
            if node.attrs['intent']=='replay_download':
                await self.download_replay(reader,writer,account['_id'],token,node.attrs['run_id'])
                return
            peer=Peer(reader,writer,account,token,node.attrs['intent']=='result_retry')
            room=await self.room(account['_id'],node.attrs['run_id'],peer.upload_only)
            await room.admit(peer)
            while True:
                await room.command(peer,await receive(reader))
        except (AuthError,DomainError,WireError,ValueError,KeyError,TypeError):
            try:
                await send(writer,message('leave_game',reason='Alliance battle request rejected. Refresh the plan, account session and service status.'))
            except Exception:
                pass
        except (OSError,asyncio.TimeoutError,asyncio.IncompleteReadError,ssl.SSLError):
            pass
        except Exception as error:
            # No arbitrary driver exception/body/capability is logged.
            print('BATTLE CONNECTION FAILED: '+type(error).__name__,flush=True)
        finally:
            if peer and room:
                async with room.lock:
                    if room.peers.get(peer.account['_id']) is peer:
                        del room.peers[peer.account['_id']]
            self.connections-=1
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


def tls_context(identity):
    identity=safe_path(identity)
    profile=verify_identity(identity,port=15001)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(safe_path(identity/'server-cert.pem')),str(safe_path(identity/'server-key.pem')))
    return context,profile['server_address']


async def run(runtime, identity):
    runtime=owned_runtime(safe_path(runtime))
    settings=Settings.load(runtime)
    context,address=tls_context(identity)
    with MongoClient(settings.mongo_uri,serverSelectionTimeoutMS=5000,connectTimeoutMS=3000,
                     socketTimeoutMS=10000,tz_aware=True) as client:
        db=client.get_default_database()
        await asyncio.to_thread(db.command,'ping')
        daemon=BattleDaemon(db,Path(runtime)/'battles',context)
        with process_lock(Path(runtime)/'battles'/'daemon.lock'):
            server=await asyncio.start_server(daemon.handle,address,15002,limit=131072)
            print(f'ALLIANCE SHARED BATTLE SERVICE READY {address}:15002',flush=True)
            print('Keep this window open. Existing accounts and fixed side ownership are required.',flush=True)
            settlement=asyncio.create_task(daemon.settle_ready())
            try:
                async with server:
                    await server.serve_forever()
            finally:
                settlement.cancel()
                await asyncio.gather(settlement,return_exceptions=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run the local fixed-seat Alliance battle service.')
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--identity',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        asyncio.run(run(args.runtime,args.identity))
        return 0
    except KeyboardInterrupt:
        print('Battle service stopped. Retained rooms can reconnect after restart.',flush=True)
        return 0
    except Exception as error:
        print('BATTLE SERVICE FAILED: '+type(error).__name__+'. Preserve runtime files and send the saved log.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
