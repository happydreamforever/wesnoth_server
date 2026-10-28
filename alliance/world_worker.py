"""Supervise the full native engine; Python never chooses an AI move or result.

The child receives a generation-scoped machine capability through stdin. Its
durable native ledger/replay is checked against the relay's exact terminal
cursor before the private domain settlement entry point can be called.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4

HASH = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
MAX_EVIDENCE = 32 * 1024 * 1024


def canonical(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def json_record(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate worker record field.")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def ordinary(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Worker storage must not traverse links.")
    if path.is_file() and path.stat().st_nlink != 1:
        raise ValueError("Worker storage must not use hard links.")
    return path


def bounded(path, limit):
    path = ordinary(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Worker evidence is missing or oversized.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Worker evidence changed during reading.")
    return data


def write_json(path, value):
    path = ordinary(path)
    temporary = path.with_name(path.name + '.partial-' + uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write(canonical(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        move = kernel.MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        if not move(str(temporary), str(path), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(temporary, path)
    if os.name != 'nt':
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(parent)
        finally: os.close(parent)


def validate_evidence(directory, descriptor, cursor, native_scenario):
    """Only called on a verified owned child's output, never a client upload."""
    raw = bounded(Path(directory) / "evidence.json", MAX_EVIDENCE)
    proof = json_record(raw)
    replay = bounded(Path(directory) / "replay.gz", MAX_EVIDENCE)
    if (not replay or proof.get("format") != 1 or proof.get("run_id") != descriptor["run_id"]
            or proof.get("generation") != descriptor["generation"]
            or proof.get("scenario_sha256") != native_scenario
            or proof.get("replay_sha256") != sha(replay)
            or proof.get("command_chain_sha256") != cursor["sha256"]
            or proof.get("command_count") != cursor["count"]
            or proof.get("sync_valid") is not True
            or proof.get("terminal") not in ("leaders_defeated", "turn_limit")
            or proof.get("outcome") not in ("win", "draw")
            or not HASH.fullmatch(proof.get("ledger_sha256", ""))):
        raise ValueError("Native World evidence binding differs.")
    teams = {side["team_id"] for side in descriptor["sides"] if side["controller"] != "closed"}
    if (proof["outcome"] == "draw" and proof.get("winner_team_id") not in (None, "")) or (
            proof["outcome"] == "win" and proof.get("winner_team_id") not in teams):
        raise ValueError("Native World outcome differs.")
    ledger = proof.get("ledger")
    if not isinstance(ledger, list) or len(ledger) > 100000 or proof.get("event_count") != len(ledger) or sha(canonical(ledger)) != proof["ledger_sha256"]:
        raise ValueError("Native troop ledger is incomplete.")
    units = {unit["instance_id"]: unit for side in descriptor["sides"]
             for unit in ([side["hero"]] if side.get("hero") else []) + side["soldiers"]}
    chain = "0" * 64
    earned = {key: 0 for key in units}
    deployed, dead = set(), set()
    for sequence, item in enumerate(ledger):
        row = dict(item)
        digest = row.pop("sha256", None)
        if (row.get("sequence") != sequence or row.get("previous") != chain
                or row.get("run_id") != descriptor["run_id"] or row.get("generation") != descriptor["generation"]
                or row.get("instance_id") not in units or sha(canonical(row)) != digest
                or row.get("kind") not in ("deployed", "experience", "advance", "fallen")
                or type(row.get("amount")) is not int or not 0 <= row["amount"] <= 1000000):
            raise ValueError("Native troop event chain differs.")
        chain = digest
        key = row["instance_id"]
        if row["kind"] == "deployed":
            if key in deployed: raise ValueError("Duplicate native deployment.")
            deployed.add(key)
        elif row["kind"] == "experience":
            if key not in deployed: raise ValueError("Undeployed troop earned experience.")
            earned[key] += row["amount"]
        elif row["kind"] == "fallen":
            if key not in deployed or key in dead: raise ValueError("Native wound sequence differs.")
            dead.add(key)
    summaries = proof.get("units")
    if not isinstance(summaries, list) or len(summaries) != len(units) or {u.get("instance_id") for u in summaries} != set(units):
        raise ValueError("Native troop summary is incomplete.")
    for row in summaries:
        key = row["instance_id"]
        if row.get("earned_xp") != earned[key] or row.get("deployed") != (key in deployed) or row.get("dead") != (key in dead):
            raise ValueError("Native troop summary differs from its ledger.")
    # Remove bulky replay event content from the transaction: it stays immutable
    # next to the recording and is bound by its digest in the receipt.
    if (proof.get("native_end") not in ("victory", "defeat", "observer_end")
            or type(proof.get("combat_verified")) is not bool
            or proof.get("completed_rounds") != cursor["completed_rounds"]):
        raise ValueError("Native terminal or tactical round evidence differs.")
    if proof["native_end"] == "observer_end" and any(side["controller"] == "worker" for side in descriptor["sides"]):
        raise ValueError("Only a noncontrolling native witness may report observer completion.")
    winner = proof["winner_team_id"] or None
    first_team = next(side["team_id"] for side in descriptor["sides"] if side["controller"] != "closed")
    outcome = "draw" if winner is None else "win" if winner == first_team else "loss"
    return {**{key: proof[key] for key in ("scenario_sha256", "replay_sha256", "ledger_sha256", "event_count",
            "command_chain_sha256", "units", "sync_valid", "combat_verified", "completed_rounds")},
            "terminal": ("draw" if winner is None else "victory") if proof["native_end"] == "observer_end" else proof["native_end"],
            "outcome": outcome, "winner_team_id": winner}


class WorldWorkerSupervisor:
    def __init__(self, daemon, identity, executable=None, game_data=None, workers=1):
        self.daemon, self.identity = daemon, ordinary(identity)
        self.root = ordinary(daemon.storage / "world")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.executable, self.game_data = executable, game_data
        if type(workers) is not int or not 1 <= workers <= 4:
            raise ValueError("World worker limit must be between one and four.")
        self.limit = workers
        self.children, self.tickets, self.rooms = {}, {}, {}
        self.stopping = False

    def capability(self, run_id, generation, worker_id):
        token = secrets.token_urlsafe(32)
        self.tickets[sha(token.encode())] = {"run_id": run_id, "generation": generation,
            "worker_id": worker_id, "expires": time.monotonic() + 330, "connected": False}
        return token

    def consume(self, token, run_id):
        if not TOKEN.fullmatch(token): raise ValueError("Invalid worker admission.")
        row = self.tickets.get(sha(token.encode()))
        if row is None or row["run_id"] != run_id or row["expires"] < time.monotonic() or row["connected"]:
            raise ValueError("Worker admission is stale or already used.")
        row["connected"] = True
        return row

    async def launch(self, descriptor, worker_id):
        from .world_execution import WorldRoom
        from .battle_wire import WireError
        descriptor = {key: value for key, value in descriptor.items() if key not in ('state', 'scenario_sha256')}
        run_id, generation = descriptor["run_id"], descriptor["generation"]
        directory = ordinary(self.root / run_id / generation)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        room = self.rooms.get(run_id)
        if room is None:
            try:
                room = WorldRoom(self, descriptor, directory)
            except (ValueError, KeyError, TypeError, WireError):
                await asyncio.to_thread(self.daemon.domain.world_worker_pause,
                    run_id, worker_id, generation, "native_evidence_conflict")
                raise
            self.rooms[run_id] = room
        elif room.generation != generation:
            raise ValueError("World worker generation differs from retained room.")
        if room.pause_reason in ("native_sync_error", "native_evidence_conflict"):
            await asyncio.to_thread(self.daemon.domain.world_worker_pause,
                run_id, worker_id, generation, room.pause_reason)
            raise ValueError("The retained native synchronization failure requires review.")
        # An acquired replacement lease authorizes replay of the same generation,
        # never an invented result or a fresh battle with the old reservations.
        room.paused = False
        room.pause_reason = ""
        room.update_availability()
        room.persist()
        if room.terminal_cursor is not None:
            try:
                for previous in sorted(directory.glob("worker-*")):
                    if not (previous / "evidence.json").exists(): continue
                    evidence = validate_evidence(previous, descriptor, room.terminal_cursor, room.scenario)
                    loaded = await asyncio.to_thread(self.daemon.domain.world_worker_loaded,
                        run_id, worker_id, generation, room.scenario)
                    if loaded.get("state") not in ("preparing", "running", "paused"):
                        raise ValueError("The retained native scenario was rejected.")
                    settled = await asyncio.to_thread(self.daemon.domain.world_worker_finish,
                        run_id, worker_id, generation, evidence)
                    if settled.get("state") not in (None, "completed", "awaiting_confirmation"):
                        raise ValueError("The retained native result was rejected.")
                    room.completed_replay = previous / "replay.gz"
                    room.completed = True
                    room.persist()
                    return
                raise ValueError("Retained terminal cursor has no complete native evidence.")
            except (ValueError, KeyError, TypeError):
                room.paused = True
                room.pause_reason = "native_evidence_conflict"
                room.available.set()
                room.persist()
                await asyncio.to_thread(self.daemon.domain.world_worker_pause,
                    run_id, worker_id, generation, room.pause_reason)
                raise
        attempt = ordinary(directory / ("worker-" + uuid4().hex))
        attempt.mkdir(mode=0o700)
        (attempt / "userdata").mkdir(mode=0o700)
        token = self.capability(run_id, generation, worker_id)
        environment = os.environ.copy()
        environment.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
            WESNOTH_WORLD_WORKER_PROFILE=str(self.identity / "public-profile.json"),
            WESNOTH_WORLD_WORKER_OUTPUT=str(attempt),
            WESNOTH_ALLIANCE_PROFILE=str(self.identity / "public-profile.json"))
        # Runtime DLLs are beside the verified executable. Do not search unrelated
        # MSYS/UCRT installations for a second dependency ABI.
        if os.name == "nt":
            environment["PATH"] = str(Path(self.executable).parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
        command = [str(self.executable), str(self.game_data), "--userdata-dir", str(attempt / "userdata"),
                   "--nogui", "--multiplayer", "--nosound", "--noaddons", "--no-log-to-file", "--log-none=audio"]
        log = (attempt / "engine.log").open("xb")
        child, pulse = None, None
        async def heartbeat():
            try:
                while child.returncode is None:
                    lease = await asyncio.to_thread(self.daemon.domain.world_worker_lease, run_id, worker_id, generation)
                    if lease.get("state") not in ("preparing", "running", "paused"):
                        raise ValueError("The native execution lease is no longer active.")
                    await asyncio.sleep(25)
            except Exception:
                if child.returncode is None: child.terminate()
                raise
        try:
            child = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                stdout=log, stderr=asyncio.subprocess.STDOUT, env=environment)
            self.children[run_id] = child
            pulse = asyncio.create_task(heartbeat())
            child.stdin.write(canonical({"run_id": run_id, "token": token}) + b"\n")
            await child.stdin.drain()
            child.stdin.close()
            code = await child.wait()
            write_json(attempt / "process.json", {"exit_code": code, "terminal_cursor": room.terminal_cursor is not None})
            if code != 0 or room.terminal_cursor is None:
                raise ValueError("Native worker paused before a verified terminal.")
            try:
                evidence = validate_evidence(attempt, descriptor, room.terminal_cursor, room.scenario)
            except (ValueError, KeyError, TypeError):
                room.pause_reason = "native_evidence_conflict"
                raise
            settled = await asyncio.to_thread(self.daemon.domain.world_worker_finish,
                                   run_id, worker_id, generation, evidence)
            if settled.get("state") not in (None, "completed", "awaiting_confirmation"):
                room.pause_reason = "native_evidence_conflict"
                raise ValueError("The native result was rejected.")
            room.completed_replay = attempt / "replay.gz"
            room.completed = True
            room.persist()
            await room.broadcast_notice("Battle recording saved. Return to Battles for the result.")
        except Exception as error:
            room.paused = True
            room.available.set()  # Wake bounded pending packets so their guards close the old peers.
            room.persist()
            for peer in list(room.peers.values()): peer.writer.close()
            await asyncio.to_thread(self.daemon.domain.world_worker_pause, run_id, worker_id, generation,
                room.pause_reason or "worker_interrupted")
            print("WORLD WORKER PAUSED: " + type(error).__name__ + "; exit=" + str(getattr(child, "returncode", None)) + "; retained=" + str(attempt), flush=True)
        finally:
            if pulse is not None:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)
            if child is not None and child.returncode is None:
                child.terminate()
                await child.wait()
            self.children.pop(run_id, None)
            self.tickets.pop(sha(token.encode()), None)
            log.close()

    async def serve(self):
        tasks = set()
        while not self.stopping:
            try:
                for run_id, room in list(self.rooms.items()):
                    if room.completed and run_id not in self.children and not room.peers:
                        self.rooms.pop(run_id, None)  # History/replay reloads from the durable journal.
                if self.executable is not None and len(tasks) < self.limit:
                    worker_id = str(uuid4())
                    descriptor = await asyncio.to_thread(self.daemon.domain.world_worker_acquire, worker_id)
                    if descriptor:
                        task = asyncio.create_task(self.launch(descriptor, worker_id))
                        tasks.add(task)
                        def finished(task):
                            tasks.discard(task)
                            if not task.cancelled() and task.exception():
                                print("WORLD WORKER LAUNCH PAUSED: " + type(task.exception()).__name__, flush=True)
                        task.add_done_callback(finished)
            except Exception as error:
                print("WORLD WORKER QUEUE PAUSED: " + type(error).__name__, flush=True)
            await asyncio.sleep(2)

    async def close(self):
        self.stopping = True
        for room in self.rooms.values():
            room.paused = True
            room.available.set()
            for peer in list(room.peers.values()): peer.writer.close()
        for child in list(self.children.values()):
            if child.returncode is None: child.terminate()
        await asyncio.gather(*(child.wait() for child in self.children.values()), return_exceptions=True)
