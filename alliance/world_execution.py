"""World typed wire route. Authority is separate from legacy Team results."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import secrets
from .battle_wire import Node, WireError, message, receive, send, serialize, parse
from .world_worker import ordinary, bounded, canonical, sha, write_json, json_record


class WorldPeer:
    def __init__(self, reader, writer, actor, token, worker=False):
        self.reader, self.writer, self.actor, self.token, self.worker = reader, writer, actor, token, worker
        self.loaded = False
        self.sides = []
        self.lock = asyncio.Lock()

    async def send(self, node):
        async with self.lock: await send(self.writer, node)


class WorldRoom:
    def __init__(self, supervisor, descriptor, directory):
        self.supervisor, self.descriptor, self.directory = supervisor, descriptor, directory
        self.run_id, self.generation = descriptor["run_id"], descriptor["generation"]
        self.lock, self.peers = asyncio.Lock(), {}
        self.available = asyncio.Event()
        self.seed, self.scenario = secrets.token_hex(4), ""
        self.started = self.paused = self.completed = False
        self.pause_reason = ""
        self.completed_replay, self.terminal_cursor = None, None
        self.active = [s["side"] for s in descriptor["sides"] if s["controller"] != "closed"]
        self.current_side, self.turn, self.chain, self.count = min(self.active), 1, "0" * 64, 0
        self.choices, self.history = {}, []
        self.history_bytes = 0
        marker = directory / "room.json"
        if marker.exists():
            row = json_record(bounded(marker, 262144))
            if row["descriptor"] != descriptor: raise WireError("Retained World descriptor differs.")
            self.seed, self.scenario, self.started = row["seed"], row["scenario"], row["started"]
            self.completed = row["completed"]
            self.paused = row.get("paused", False)
            self.pause_reason = row.get("pause_reason", "")
            self.terminal_cursor = row["terminal_cursor"]
            anchor_count = row.get("command_count", 0)
            anchor_chain = row.get("command_chain_sha256", "0" * 64)
            anchor_seen = anchor_count == 0 and anchor_chain == "0" * 64
            if row.get("completed_replay"): self.completed_replay = ordinary(directory / row["completed_replay"])
            history = directory / "commands.jsonl"
            if history.exists():
                for line in bounded(history, 128*1024*1024).splitlines():
                    event = json_record(line)
                    digest = event.pop("sha256")
                    if event != {"sequence": self.count, "generation": self.generation,
                                 "previous": self.chain, "wml": event["wml"]} or sha(canonical(event)) != digest:
                        raise WireError("Retained World command chain differs.")
                    self._accept(parse(event["wml"]), event["wml"], digest)
                    if self.count == anchor_count:
                        anchor_seen = self.chain == anchor_chain
            if not anchor_seen:
                raise WireError("Retained World command tail is missing or changed.")
            if self.terminal_cursor is not None and (self.terminal_cursor["count"] != self.count
                    or self.terminal_cursor["sha256"] != self.chain):
                raise WireError("Retained World terminal cursor differs from its commands.")
        self.persist()

    def update_availability(self):
        required = set(self.descriptor["required_humans"]) | {"worker"}
        if (self.started and not self.paused and not self.completed
                and required <= self.peers.keys()
                and all(self.peers[key].loaded for key in required)):
            self.available.set()
        else:
            self.available.clear()

    def persist(self):
        write_json(self.directory / "room.json", {"descriptor": self.descriptor, "seed": self.seed,
            "scenario": self.scenario, "started": self.started, "paused": self.paused,
            "pause_reason": self.pause_reason,
            "completed": self.completed, "terminal_cursor": self.terminal_cursor,
            "command_count": self.count, "command_chain_sha256": self.chain,
            "completed_replay": str(self.completed_replay.relative_to(self.directory)) if self.completed_replay else None})

    def next_side(self, requested):
        return next((n for n in self.active if n >= requested), self.active[0])

    def _accept(self, root, text, digest):
        self.history_bytes += len(canonical({"sequence": self.count, "generation": self.generation,
            "previous": self.chain, "wml": text, "sha256": digest})) + 1
        if self.history_bytes > 128*1024*1024:
            raise WireError("World command history exceeds its total bound.")
        self.chain = digest
        self.count += 1
        self.history.append(root)
        for turn in root.children:
            for command in turn.children:
                for action in command.children:
                    if action.name == "end_turn":
                        target = int(action.attrs.get("next_player_number", "0")) or self.current_side + 1
                        following = self.next_side(target)
                        if following <= self.current_side: self.turn += 1
                        self.current_side = following
                    elif action.name == "random_seed":
                        self.choices[int(action.attrs["request_id"])] = action.attrs["new_seed"]

    def append(self, root):
        text = serialize(root)
        if self.count >= 100000 or len(text.encode()) > 2*1024*1024 or self.history_bytes + len(text.encode()) > 128*1024*1024:
            raise WireError("World command history exceeds its bound.")
        record = {"sequence": self.count, "generation": self.generation, "previous": self.chain, "wml": text}
        digest = sha(canonical(record))
        record["sha256"] = digest
        encoded = canonical(record) + b"\n"
        if self.history_bytes + len(encoded) > 128*1024*1024:
            raise WireError("World command journal exceeds its total bound.")
        import os
        try:
            with ordinary(self.directory / "commands.jsonl").open("ab") as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        except OSError:
            self.paused = True
            self.available.clear()
            self.persist()
            raise
        self._accept(root, text, digest)
        self.persist()

    async def broadcast(self, root, exclude=None):
        for key, peer in list(self.peers.items()):
            if key != exclude:
                try: await peer.send(root)
                except (OSError, asyncio.TimeoutError): peer.writer.close()

    async def broadcast_notice(self, text):
        await self.broadcast(message("message", sender="World", side=0, message=text))

    async def admit(self, peer):
        async with self.lock:
            key = "worker" if peer.worker else peer.actor
            if key in self.peers: raise WireError("World seat is already connected.")
            peer.sides = [side["side"] for side in self.descriptor["sides"] if
                (side["controller"] == "worker" if peer.worker else side["controller"] == "human" and side["account_id"] == peer.actor)]
            if not peer.worker and not peer.sides: raise WireError("Player does not control a World side.")
            self.peers[key] = peer
            await peer.send(message("world_room", descriptor=json.dumps(self.descriptor, separators=(",", ":")),
                seed=self.seed, controlled_sides=",".join(map(str, peer.sides)), worker="yes" if peer.worker else "no",
                reconnect="yes" if self.started else "no", current_turn=self.turn))

    async def authorize(self, peer):
        domain = self.supervisor.daemon.domain
        if peer.worker:
            lease = await asyncio.to_thread(domain.world_worker_lease, self.run_id, peer.actor, self.generation)
            if lease.get("state") not in ("preparing", "running", "paused"):
                raise WireError("The native execution lease is no longer active.")
        else:
            actor = await asyncio.to_thread(self.supervisor.daemon.auth.validate_token, peer.token, "player")
            if actor["_id"] != peer.actor: raise WireError("World session identity differs.")
            await asyncio.to_thread(domain.world_human_join, peer.actor, self.run_id)

    async def command(self, peer, root):
        if root.attrs or len(root.children) != 1: raise WireError("World packet differs.")
        # A disconnected human is never replaced with AI. Keep at most the
        # current bounded packet in this peer's receive loop until that account
        # has loaded the retained history again. Do not hold the room lock here.
        node = root.children[0]
        if self.started and node.name in ("turn", "request_choice"):
            if self.paused or self.completed: raise WireError("World battle is paused.")
            await asyncio.wait_for(self.available.wait(), 600)
        async with self.lock:
            await self.authorize(peer)
            node = root.children[0]
            if self.started and node.name in ("turn", "request_choice") and not self.available.is_set():
                raise WireError("A required human controller disconnected.")
            if node.name == "world_loaded":
                if set(node.attrs) != {"scenario_sha256"} or node.children or peer.loaded:
                    raise WireError("World load binding differs.")
                digest = node.attrs["scenario_sha256"]
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest): raise WireError("Invalid scenario digest.")
                if self.scenario and self.scenario != digest: raise WireError("World scenarios differ.")
                self.scenario = digest
                domain = self.supervisor.daemon.domain
                if peer.worker:
                    loaded = await asyncio.to_thread(domain.world_worker_loaded, self.run_id, peer.actor, self.generation, digest)
                else:
                    loaded = await asyncio.to_thread(domain.world_human_loaded, peer.actor, self.run_id, self.generation, digest)
                if loaded.get("state") not in ("preparing", "running", "paused"):
                    self.paused = True
                    self.pause_reason = "native_load_rejected"
                    self.persist()
                    raise WireError("The battle generation could not finish loading.")
                peer.loaded = True
                self.update_availability()
                self.persist()
                if self.started:
                    for packet in self.history: await peer.send(packet)
                    await peer.send(message("world_start", reconnect="yes"))
                else:
                    required = set(self.descriptor["required_humans"]) | {"worker"}
                    if required <= set(self.peers) and all(self.peers[key].loaded for key in required):
                        self.started = True
                        self.update_availability()
                        self.persist()
                        await self.broadcast(message("world_start", reconnect="no"))
                    else:
                        await self.broadcast(message("world_waiting", connected=sum(p.loaded for p in self.peers.values()), required=len(required)))
                return
            if not self.started or not peer.loaded or self.paused or self.completed:
                raise WireError("World battle is not active.")
            if node.name == "world_native_terminal":
                if not peer.worker or set(node.attrs) != {"scenario_sha256"} or node.attrs["scenario_sha256"] != self.scenario or node.children:
                    raise WireError("Native terminal authority differs.")
                self.terminal_cursor = {"sha256": self.chain, "count": self.count, "completed_rounds": max(0,self.turn-1)}
                self.persist()
                await peer.send(message("world_terminal_cursor", **self.terminal_cursor))
                return
            if self.terminal_cursor is not None: raise WireError("World native terminal is already frozen.")
            if "worker" not in self.peers or not self.peers["worker"].loaded:
                raise WireError("The native World witness is reconnecting.")
            if node.name == "request_choice":
                if set(node.attrs) != {"request_id"} or len(node.children) != 1 or node.children[0].name != "random_seed":
                    raise WireError("World random request differs.")
                request = int(node.attrs["request_id"])
                if request in self.choices: return
                if (request not in (0,1)) if not self.choices else (request != max(self.choices) + 1):
                    raise WireError("World random sequence differs.")
                packet = Node(children=[Node("turn", children=[Node("command", {"from_side":"server", "dependent":"yes"},
                    [Node("random_seed", {"new_seed":secrets.token_hex(4),"request_id":request})])])])
                self.append(packet); await self.broadcast(packet); return
            if node.name == "turn":
                if node.attrs or not 1 <= len(node.children) <= 512: raise WireError("Invalid World turn.")
                simulated = self.current_side
                for command in node.children:
                    if command.name != "command" or not command.children: raise WireError("Invalid World command.")
                    side = int(command.attrs.get("from_side", str(simulated)))
                    if side not in peer.sides: raise WireError("World command exceeds assigned authority.")
                    names = [action.name for action in command.children]
                    if any(name in ("change_controller", "change_controller_wml", "add_side", "random_seed", "custom_command") or name.startswith("debug_") for name in names):
                        raise WireError("World command may not rewrite controller or terminal state.")
                    dependent = command.attrs.get("dependent") == "yes" and command.attrs.get("from_side") == str(side) and len(names) == 1 and names[0] not in ("end_turn", "init_side")
                    if side != simulated and not dependent: raise WireError("World turn ownership differs.")
                    for action in command.children:
                        if action.name == "end_turn":
                            target = int(action.attrs.get("next_player_number", "0")) or simulated + 1
                            if not 1 <= target <= len(self.descriptor["sides"]) + 1: raise WireError("Invalid World next side.")
                            simulated = self.next_side(target)
                self.append(root)
                await self.broadcast(root, "worker" if peer.worker else peer.actor)
                return
            if node.name in ("leave_game", "stop_updates"):
                peer.writer.close(); return
            if node.name == "info":
                if node.attrs.get('condition') == 'out of sync':
                    self.paused = True
                    self.pause_reason = "native_sync_error"
                    self.update_availability()
                    self.persist()
                    await self.broadcast_notice('Synchronization failed. The battle is paused; no result was settled.')
                return  # Native advisory is never terminal evidence.
            raise WireError("Unsupported World command.")


async def handle_world(supervisor, reader, writer, node):
    if set(node.attrs) != {"run_id", "token", "role", "intent"} or node.children:
        raise WireError("Invalid World join.")
    run_id, token = node.attrs["run_id"], node.attrs.pop("token")
    worker = node.attrs["role"] == "worker"
    if node.attrs["role"] not in ("worker", "human") or node.attrs["intent"] not in ("play", "replay"):
        raise WireError("Invalid World role.")
    if worker:
        if node.attrs["intent"] != "play": raise WireError("Worker cannot browse history.")
        capability = supervisor.consume(token, run_id)
        actor = capability["worker_id"]
        await asyncio.to_thread(supervisor.daemon.domain.world_worker_lease, run_id, actor, capability["generation"])
    else:
        account = await asyncio.to_thread(supervisor.daemon.auth.validate_token, token, "player")
        actor = account["_id"]
        if node.attrs["intent"] == "replay":
            await download_world(supervisor, reader, writer, actor, token, run_id)
            return
        await asyncio.to_thread(supervisor.daemon.domain.world_human_join, actor, run_id)
    room = supervisor.rooms.get(run_id)
    if room is None: raise WireError("The World worker is still preparing this battle.")
    peer = WorldPeer(reader, writer, actor, token, worker)
    try:
        await room.admit(peer)
        while True: await room.command(peer, await receive(reader))
    finally:
        async with room.lock:
            key = "worker" if worker else actor
            if room.peers.get(key) is peer: room.peers.pop(key)
            room.update_availability()
            if not worker and not room.paused and not room.completed and room.terminal_cursor is None:
                await asyncio.to_thread(supervisor.daemon.domain.world_human_disconnect, actor, run_id, room.generation)


async def download_world(supervisor, reader, writer, actor, token, run_id):
    descriptor = await asyncio.to_thread(supervisor.daemon.domain.world_replay_authorize, actor, run_id)
    room = supervisor.rooms.get(run_id)
    if room is None:
        directory = ordinary(supervisor.root / run_id / descriptor["generation"])
        marker = json_record(bounded(directory / "room.json", 262144))
        if marker["descriptor"]["run_id"] != run_id or marker["descriptor"]["generation"] != descriptor["generation"]:
            raise WireError("Retained World replay generation differs.")
        room = WorldRoom(supervisor, marker["descriptor"], directory)
    candidates = [room.completed_replay] if room.completed_replay else sorted(room.directory.glob("worker-*/replay.gz"))
    data = None
    for candidate in candidates:
        value = bounded(candidate, 32*1024*1024)
        if sha(value) == descriptor["replay_sha256"]:
            data = value
            break
    if data is None: raise WireError("Retained World replay is unavailable or changed.")
    await send(writer, message("world_replay_info", run_id=run_id, sha256=sha(data), bytes=len(data)))
    for offset in range(0, len(data), 24000):
        request = (await receive(reader, 30)).one("world_replay_get")
        if request.attrs != {"offset": str(offset)} or request.children: raise WireError("World replay offset differs.")
        current = await asyncio.to_thread(supervisor.daemon.auth.validate_token, token, "player")
        if current["_id"] != actor: raise WireError("World replay identity changed.")
        await asyncio.to_thread(supervisor.daemon.domain.world_replay_authorize, actor, run_id)
        await send(writer, message("world_replay_data", offset=offset, data=base64.b64encode(data[offset:offset+24000]).decode("ascii")))
