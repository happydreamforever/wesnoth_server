"""Audit pinned native company values and generate the public hero cost table.

Run from any directory. --check is read-only and is required before release.
No runtime, credentials or database is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from alliance.company import TROOPS

def top_level(text):
    depth=0;current={};rows=[]
    for line in text.splitlines():
        line=line.strip()
        if re.fullmatch(r'\[[^/].*\]',line):
            depth+=1
            if depth==1:current={}
        elif re.fullmatch(r'\[/.*\]',line):
            if depth==1:rows.append(current)
            depth-=1
        elif depth==1:
            match=re.fullmatch(r'(id|cost|level|experience|advances_to)=(.*)',line)
            if match:current[match[1]]=match[2].strip('"')
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    data=ROOT.parent/'gamedata-1.19.26/data/core/units';actual={};sources={}
    for path in sorted(data.rglob('*.cfg')):
        for row in top_level(path.read_text()):
            if row.get('id') not in TROOPS:continue
            choices=() if row.get('advances_to')=='null' else tuple(row.get('advances_to','').split(','))
            actual[row['id']]=(int(row['cost']),int(row['level']),int(row['experience']),choices)
            sources[str(path.relative_to(data))]=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=TROOPS:raise SystemExit('Pinned native company values differ: '+repr({k:(TROOPS.get(k),actual.get(k)) for k in TROOPS if TROOPS[k]!=actual.get(k)}))
    path=ROOT.parent/'wesnoth_client/alliance_game/hero_unit_data.inc';raw=path.read_bytes();text=raw.decode();text=text[text.index('[unit_type]'):]
    costs={row['id']:int(row.get('cost',0)) for row in top_level(text) if row.get('id')}
    catalog=json.loads((ROOT/'alliance/hero_catalog.json').read_text())
    if any(f['unit_type'] not in costs for f in catalog['forms']):raise SystemExit('Incomplete hero cost coverage')
    outputs={'company_hero_costs.json':{'source_sha256':hashlib.sha256(raw).hexdigest(),'costs':costs},
             'company_source_manifest.json':{'format':'company-native-sources-1','files':sources}}
    for name,value in outputs.items():
        output=json.dumps(value,sort_keys=True,separators=(',',':'))+'\n';destination=ROOT/'alliance'/name
        if args.check:
            if destination.read_text()!=output:raise SystemExit('Regenerate '+name)
        else:destination.write_text(output)
    print('COMPANY NATIVE CATALOGUE VERIFIED: '+str(len(actual))+' troop forms; '+str(len(catalog['forms']))+' hero forms.')
if __name__=='__main__':main()
