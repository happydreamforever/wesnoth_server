"""Opt-in real native host + production individual companion over actual TLS.

Fixture uses two disposable accounts with server-owned heroes, a real map and
two synchronized AI rounds. Host choices and turn-3 ending are scripted. No
Android execution or human-input acceptance is claimed by this Linux test.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import unittest

from test_individual_native import Individual


@unittest.skipUnless(os.environ.get('ALLIANCE_INDIVIDUAL_ENGINE'), 'Requires completed isolated native engine fixture')
class Engine(Individual):
    def test_actual_individual_host_and_production_companion(self):
        binary=Path(os.environ['ALLIANCE_INDIVIDUAL_ENGINE'])
        output=Path(os.environ['ALLIANCE_INDIVIDUAL_ENGINE_OUTPUT']);output.mkdir()
        actors=[self.account(),self.account()]
        before=[self.db.account_heroes.find_one({'account_id':actor['id']}) for _,_,actor in actors]
        processes=[];logs=[];events=queue.Queue();threads=[];observed=[[],[]]
        def launch(index,room=1):
            api,token,actor=actors[index];own=output/str(index);own.mkdir()
            environment=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',
                WESNOTH_INDIVIDUAL_COMPANION_PROFILE=str(self.identity/'public-profile.json'))
            if index==0:environment['INDIVIDUAL_FIXTURE_HOST']='1'
            command=[str(binary),'/gamedata','--userdata-dir',str(own/'userdata'),'--test=test',
                '--multiplayer','--nogui','--nosound','--no-log-to-file','--log-none=audio']
            process=subprocess.Popen(command,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,text=True,bufsize=1)
            processes.append(process);log=(own/'engine.log').open('x');logs.append(log)
            def capture():
                for line in process.stdout:
                    log.write(line);log.flush();events.put((index,line.rstrip()))
                events.put((index,None))
            thread=threading.Thread(target=capture,daemon=True);thread.start();threads.append(thread)
            payload={'intent':'individual_play','account_id':actor['id'],'token':token,
                'room_id':room,'hero_id':self.hero,'form_id':self.form['id']}
            if index == 1 and os.environ.get('INDIVIDUAL_FIXTURE_ROOM_NAME'):
                payload.pop('room_id')
                payload['room_name'] = 'Individual actual engine fixture'
            process.stdin.write(json.dumps(payload)+'\n');process.stdin.flush()
            return process
        try:
            launch(0);deadline=time.monotonic()+180;guest=None;reviews=[]
            while time.monotonic()<deadline:
                try: index,line=events.get(timeout=min(1,max(.1,deadline-time.monotonic())))
                except queue.Empty:
                    if len(processes)==2 and all(process.poll() is not None for process in processes):break
                    continue
                if line is None:
                    processes[index].wait(timeout=5)
                    if all(process.poll() is not None for process in processes) and len(processes)==2:break
                    continue
                observed[index].append(line)
                if line.startswith('INDIVIDUAL HOST ROOM '):
                    self.assertIsNone(guest);guest=launch(1,int(line.rsplit(' ',1)[1]))
                elif line.startswith('INDIVIDUAL COMPANION REVIEW '):
                    value=json.loads(line[len('INDIVIDUAL COMPANION REVIEW '):]);reviews.append(value)
                    self.assertEqual(value['capacity'],2);self.assertIn(value['gold'],('100','125'))
                    self.assertIn(value['action'],('join','ready'))
                    guest.stdin.write(json.dumps({'action':value['action'],'revision':value['room_revision']})+'\n');guest.stdin.flush()
            self.assertEqual(len(processes),2)
            for process in processes:self.assertEqual(process.wait(timeout=5),0)
            self.assertTrue(any(review['action']=='join' for review in reviews))
            self.assertTrue(any(review['action']=='ready' for review in reviews))
            if os.environ.get('INDIVIDUAL_FIXTURE_REVIEW_CHANGE'):
                ready_reviews=[review for review in reviews if review['action']=='ready']
                self.assertEqual([review['gold'] for review in ready_reviews],['100','125'])
                self.assertGreater(ready_reviews[1]['room_revision'],ready_reviews[0]['room_revision'])
                self.assertIn('INDIVIDUAL HOST SETTINGS CHANGED AFTER GUEST READY','\n'.join(observed[0]))
            for index in range(2):
                text='\n'.join(observed[index])
                for marker in ('INDIVIDUAL ACTUAL HERO CONFIG VERIFIED','INDIVIDUAL ACTUAL NETWORK ROUND VERIFIED',
                        'INDIVIDUAL ACTUAL SECOND ROUND VERIFIED'):
                    self.assertIn(marker,text)
                self.assertNotIn('out of sync',text.lower())
            self.assertIn('INDIVIDUAL HOST FINISHED','\n'.join(observed[0]))
            self.assertIn('INDIVIDUAL COMPANION FINISHED: native battle ended; no permanent rewards','\n'.join(observed[1]))
            after=[self.db.account_heroes.find_one({'account_id':actor['id']}) for _,_,actor in actors]
            self.assertEqual(before,after)
            self.assertEqual(self.db.settlements.count_documents({}),0)
            result={'status':'passed','actual_engine_clients':2,'ai_rounds':2,'owned_hero_state_unchanged':True,
                'selected_by_unique_room_name':bool(os.environ.get('INDIVIDUAL_FIXTURE_ROOM_NAME')),
                'changed_settings_reconsent':bool(os.environ.get('INDIVIDUAL_FIXTURE_REVIEW_CHANGE')),
                'reviews':[{'action':x['action'],'revision':x['room_revision']} for x in reviews],'scope':__doc__}
            (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
        finally:
            for process in processes:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                process.stdin.close();process.stdout.close()
            for thread in threads:thread.join(2)
            for log in logs:log.close()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([Engine('test_actual_individual_host_and_production_companion')])
