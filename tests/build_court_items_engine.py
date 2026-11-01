"""Build an isolated native item-effect fixture from compiled production objects.

The injected scenario events invoke the real menu handlers on real owned heroes,
assert native HP/status effects and attempt wrong-turn/repeated uses. No fixture
code is written to production sources or packaged into the delivered worker.
"""
from pathlib import Path
import json
import subprocess

out = Path('/out')
target = out / 'fixture-items'
target.mkdir(exist_ok=True)
source = Path('/client/alliance_game/world_scenario.cpp').read_text()
needle = 'auto&timeout=c.add_child("event",config{"name","time over"});'
assert source.count(needle) == 1
fixture = r'''
if(p.mode=="court")for(const auto& selected:p.sides){
  if(selected.item_id.empty())continue;
  const auto number=std::to_string(selected.side);
  auto& verify=c.add_child("event",config{"name","side "+number+" turn refresh","first_time_only",true});
  verify.add_child("lua")["code"]=
    "local side="+number+"; local u=wesnoth.units.find_on_map{side=side,canrecruit=true}[1]; assert(u); "
    "u.hitpoints=u.max_hitpoints-20;u.status.poisoned=true;u.status.slowed=true; local old=u.hitpoints; "
    "if side==1 then wesnoth.game_events.fire('menu item court_item_2');assert(not wml.variables.court_item_used_2) end; "
    "wesnoth.game_events.fire('menu item court_item_"+number+"'); "
    "assert(wml.variables.court_item_used_"+number+"); "
    +(selected.item_id=="healing_draught"?
      "assert(u.hitpoints==old+12);assert(u.status.poisoned and u.status.slowed);":
      "assert(u.hitpoints==old);assert(not u.status.poisoned and not u.status.slowed);")+
    "local now=u.hitpoints;wesnoth.game_events.fire('menu item court_item_"+number+"');assert(u.hitpoints==now); "
    "print('COURT NATIVE ITEM EFFECT VERIFIED')";
}
'''
path = target / 'world_scenario.cpp'
path.write_text(source.replace(needle, fixture + needle))
commands = json.loads((out / 'commands.json').read_text())
compile_command = next(command for command in commands if '/client/alliance_game/world_scenario.cpp' in command)
compile_command = [str(path) if part == '/client/alliance_game/world_scenario.cpp' else
                   str(target / 'world_scenario.o') if part == '/out/world_scenario.o' else part for part in compile_command]
subprocess.run(compile_command, check=True)
link = [str(target / 'world_scenario.o') if part == '/out/world_scenario.o' else
        str(target / 'world-worker-items') if part == '/out/world-worker' else part for part in commands[-1]]
subprocess.run(link, cwd='/audit/engine', check=True)
(target / 'commands.json').write_text(json.dumps([compile_command, link], indent=2))
print('NATIVE COURT ITEM FIXTURE ENGINE BUILT')
