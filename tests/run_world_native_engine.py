"""Actual two-engine Company encounter; fixtures replace accounts, never combat.

Run in cached host-engine container with /client,/server,/audit,/gamedata read-only
and /out (new worker build + isolated writable evidence). No network required
outside the container's local TLS socket. Human seat is an explicitly admitted
native AI companion, not evidence of multiple physical human players.
"""
from __future__ import annotations
import asyncio
import argparse
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0, '/server')
from alliance.world_worker import WorldWorkerSupervisor, canonical
from alliance.world_execution import handle_world
from alliance.battle_wire import receive, send, message
from tools.alliance_transport import prepare_identity


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case', choices=('company','standing','witness'), default='company')
    parser.add_argument('--mission', choices=('company_border_patrol','company_river_crossing','company_old_fortress'), default='company_border_patrol')
    parser.add_argument('--reconnect', action='store_true')
    parser.add_argument('--worker-restart', action='store_true')
    parser.add_argument('--unit-audit', action='store_true', help='Separate test binary: native tables and synthetic XP, no settlement.')
    args=parser.parse_args()
    output=Path('/out')/('native-run-'+uuid4().hex);output.mkdir()
    identity=output/'identity'
    prepare_identity(identity,'127.0.0.1',15001,Path('/usr/bin/openssl'))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(identity/'server-cert.pem',identity/'server-key.pem')
    actor,opponent,run,generation,team,other_team=[str(uuid4()) for _ in range(6)]
    token=secrets.token_urlsafe(32)
    hero={'instance_id':'hero:'+actor+':konrad','hero_id':'konrad','form_id':'konrad_05f7156385b9',
        'unit_type':'AH_konrad_05f7156385b9','hero_level':5,'xp':0,'advancement_preferences':{}}
    soldier={'instance_id':str(uuid4()),'unit_type':'Swordsman','xp':79,
        'advancement_preferences':{'Spearman':'Swordsman','Swordsman':'Royal Guard'}}
    if args.unit_audit: soldier.update(unit_type='Spearman',xp=41)
    descriptor={'run_id':run,'generation':generation,'mode':'company','mission_id':args.mission,
        'map_id':args.mission,'settings':{'gold':100,'base_income':2,'turns':30,'fog':False,'shroud':False,'observers':False},
        'required_humans':[actor],'worker_sides':[2],
        'sides':[{'side':1,'team_id':team,'account_id':actor,'username':'Native companion','controller':'human',
            'faction':'Loyalists','leader_type':hero['unit_type'],'hero':hero,'soldiers':[soldier]},
            {'side':2,'team_id':'npc','account_id':None,'username':'Native opponent','controller':'worker',
             'faction':'Northerners','leader_type':'Orcish Warrior','hero':None,'soldiers':[]}]}
    if args.case!='company':
        descriptor.update(mode='world',mission_id='',map_id='isars-cross')
        enemy_hero={**hero,'instance_id':'hero:'+opponent+':konrad','hero_level':1}
        enemy_soldier={**soldier,'instance_id':str(uuid4()),'unit_type':'Spearman','xp':41}
        descriptor['sides'][1].update(team_id=other_team,account_id=opponent,username='Delegated opponent',
            faction='Loyalists',leader_type=hero['unit_type'],hero=enemy_hero,soldiers=[enemy_soldier])
        for number in (3,4):
            descriptor['sides'].append({'side':number,'team_id':'closed','account_id':None,'username':'Closed',
                'controller':'closed','faction':'Loyalists','leader_type':'Lieutenant','hero':None,'soldiers':[]})
        if args.case=='witness':
            descriptor['sides'][1]['controller']='human'
            descriptor['required_humans'].append(opponent)
            descriptor['worker_sides']=[]
    class Domain:
        finished=None
        def world_worker_lease(self,*args):return {'state':'running'}
        def world_worker_loaded(self,*args):return {'state':'running'}
        def world_human_loaded(self,*args):return {'state':'running'}
        def world_human_join(self,*args):return descriptor
        def world_human_disconnect(self,*args):return {'state':'paused'}
        def world_worker_pause(self,*args):return {'state':'paused'}
        def world_worker_finish(self,r,w,g,e):
            assert (r,g)==(run,generation)
            assert e['combat_verified'] and e['completed_rounds']>=1
            assert len(e['units'])==(2 if args.case=='company' else 4)
            self.finished=e
            return {'state':'completed'}
        def world_replay_authorize(self,account,battle):
            assert account==actor and battle==run and self.finished
            return {'generation':generation,'replay_sha256':self.finished['replay_sha256']}
    domain=Domain()
    class Auth:
        def validate_token(self,value,role):
            assert value in (token,second_token) and role=='player'
            return {'_id':opponent if value==second_token else actor,'username':'Native companion'}
    second_token=secrets.token_urlsafe(32)
    daemon=SimpleNamespace(storage=output/'battles',domain=domain,auth=Auth())
    executable=Path('/out/world-unit-audit' if args.unit_audit else '/out/world-worker')
    supervisor=WorldWorkerSupervisor(daemon,identity,executable,Path('/gamedata'))
    errors=[]
    async def handle(reader,writer):
        try:
            assert await reader.readexactly(4)==b'\0\0\0\1'
            writer.write(b'\0'*4);await writer.drain();await writer.start_tls(context)
            root=await receive(reader,20)
            await handle_world(supervisor,reader,writer,root.one('world_join'))
        except asyncio.IncompleteReadError:pass
        except Exception as error:
            errors.append(type(error).__name__+': '+str(error))
            print('FIXTURE WIRE ERROR',type(error).__name__,str(error),flush=True)
            try:await send(writer,message('leave_game',reason='World fixture stopped.'))
            except Exception:pass
        finally:writer.close()
    server=await asyncio.start_server(handle,'127.0.0.1',15002)
    worker=asyncio.create_task(supervisor.launch(descriptor,str(uuid4())))
    while run not in supervisor.rooms:await asyncio.sleep(.05)
    children,logs=[],[]
    async def companion(account,password_token,replay=False):
        own=output/('companion-'+str(len(children)));own.mkdir();(own/'userdata').mkdir()
        env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',
            WESNOTH_WORLD_COMPANION_PROFILE=str(identity/'public-profile.json'))
        log=(own/'engine.log').open('wb');logs.append(log)
        child=await asyncio.create_subprocess_exec(str(executable),'/gamedata','--userdata-dir',str(own/'userdata'),
            '--nogui','--multiplayer','--nosound','--noaddons','--no-log-to-file','--log-none=audio',
            stdin=asyncio.subprocess.PIPE,stdout=log,stderr=asyncio.subprocess.STDOUT,env=env)
        children.append(child)
        admission={'run_id':run,'account_id':account,'token':password_token}
        if replay:admission['intent']='replay'
        child.stdin.write(canonical(admission)+b'\n')
        await child.stdin.drain();child.stdin.close()
        return child
    child=await companion(actor,token)
    if args.case=='witness':await companion(opponent,second_token)
    try:
        reconnected=False
        retired_children=0
        if args.reconnect:
            room=supervisor.rooms[run]
            async def interrupt():
                while room.count<24 and not worker.done():await asyncio.sleep(.01)
                assert not worker.done(),'Battle ended before reconnect check.'
                child.kill();await child.wait()
                while actor in room.peers:await asyncio.sleep(.01)
                stopped=room.count;await asyncio.sleep(.4)
                assert room.count==stopped,'Native commands advanced without the required human.'
                await companion(actor,token)
            await asyncio.wait_for(interrupt(),120)
            reconnected=True
            retired_children=1
        if args.worker_restart:
            room=supervisor.rooms[run]
            async def interrupt_worker():
                while room.count<24 and not worker.done():await asyncio.sleep(.01)
                assert not worker.done(),'Battle ended before worker recovery check.'
                supervisor.children[run].kill()
                await worker
                assert domain.finished is None,'An interrupted worker settled a result.'
                while room.peers:await asyncio.sleep(.01)
                stopped=room.count;await asyncio.sleep(.4)
                assert room.count==stopped,'Commands advanced without the native witness.'
                for child in children:
                    if child.returncode is None:await asyncio.wait_for(child.wait(),20)
            await asyncio.wait_for(interrupt_worker(),120)
            retired_children=len(children)
            worker=asyncio.create_task(supervisor.launch(descriptor,str(uuid4())))
            await companion(actor,token)
            if args.case=='witness':await companion(opponent,second_token)
        await asyncio.wait_for(asyncio.gather(worker,*(p.wait() for p in children)),300)
        if args.unit_audit:
            entries=list(output.rglob('engine.log'))
            assert domain.finished is None,'Synthetic native audit must never settle.'
            assert len(entries)==2 and all('WORLD NATIVE UNIT AUDIT PASSED' in p.read_text() for p in entries)
            (output/'result.json').write_text(json.dumps({'scope':'native initialized unit tables and explicit synthetic XP; no combat reward claim',
                'unit_audit':True,'completed':True,'settlement':False,'engine_logs':[str(p) for p in entries]},indent=2))
            print('ACTUAL NATIVE UNIT TABLE / ADVANCEMENT AUDIT PASSED',output,flush=True)
            return
        assert all(p.returncode==0 for p in children[retired_children:])
        assert domain.finished is not None,errors
        room=supervisor.rooms[run]
        assert room.count>10 and any('attack' in str(packet) for packet in room.history)
        # Drop the daemon's cache and use only the authorized durable recording.
        # A new full native engine downloads and plays that replay to completion.
        supervisor.rooms.clear()
        playback=await companion(actor,token,True)
        await asyncio.wait_for(playback.wait(),120)
        assert playback.returncode==0,'Native replay playback failed.'
        result={'scope':'actual native engines; separately authenticated AI companions and scoped native worker',
            'case':args.case,'mission':args.mission,'human_reconnect':reconnected,
            'native_worker_restart':args.worker_restart,
            'native_replay_after_cache_loss':True,
            'completed':True,'wire_errors':errors,'command_count':room.count,'evidence':domain.finished}
        (output/'result.json').write_text(json.dumps(result,indent=2))
        print('ACTUAL NATIVE WORLD COMBAT AND TERMINAL EVIDENCE PASSED',output,flush=True)
    finally:
        for p in children:
            if p.returncode is None:p.kill();await p.wait()
        for log in logs:log.close()
        await supervisor.close();server.close();await server.wait_closed()

if __name__=='__main__':asyncio.run(main())
