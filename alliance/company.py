"""Persistent personal companies. Native combat remains the only XP authority.

Snapshots are deployment inputs, never values to overwrite live hero progression.
All entry points below execute inside WorldProduct's idempotent transaction.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

BALANCE_REVISION = 'world-company-1'
CAPACITY = 12
# Native Wesnoth 1.19.26 cost, tier, XP threshold, legal advancement choices.
TROOPS = {
 'Spearman':(14,1,42,('Swordsman','Pikeman','Javelineer')),
 'Swordsman':(29,2,80,('Royal Guard',)), 'Pikeman':(24,2,69,('Halberdier',)),
 'Javelineer':(24,2,100,()), 'Royal Guard':(61,3,150,()), 'Halberdier':(52,3,150,()),
 'Bowman':(14,1,35,('Longbowman',)), 'Longbowman':(23,2,65,('Master Bowman',)), 'Master Bowman':(50,3,150,()),
 'Dwarvish Fighter':(16,1,45,('Dwarvish Steelclad',)), 'Dwarvish Steelclad':(36,2,88,('Dwarvish Lord',)), 'Dwarvish Lord':(69,3,150,()),
 'Elvish Shaman':(15,1,32,('Elvish Druid','Elvish Sorceress')), 'Elvish Druid':(25,2,85,('Elvish Shyde',)), 'Elvish Shyde':(52,3,150,()),
 'Elvish Sorceress':(34,2,90,('Elvish Enchantress',)), 'Elvish Enchantress':(57,3,180,('Elvish Sylph',)), 'Elvish Sylph':(110,4,200,()),
 'Cavalryman':(17,1,44,('Dragoon',)), 'Dragoon':(29,2,80,('Cavalier',)), 'Cavalier':(62,3,150,()),
 'Mage':(20,1,48,('White Mage','Red Mage')), 'White Mage':(31,2,75,('Mage of Light',)), 'Mage of Light':(59,3,150,()),
 'Red Mage':(35,2,83,('Arch Mage','Silver Mage')), 'Arch Mage':(63,3,150,('Great Mage',)), 'Great Mage':(110,4,200,()), 'Silver Mage':(59,3,150,()),
}
BASICS = ('Spearman','Bowman','Dwarvish Fighter','Elvish Shaman','Cavalryman','Mage')
BRACKETS = {
 'scout':{'name':'Scout','budget':120,'hero_tier':2,'soldier_tier':1,'level_cap':5},
 'veteran':{'name':'Veteran','budget':240,'hero_tier':3,'soldier_tier':3,'level_cap':15},
 'champion':{'name':'Champion','budget':420,'hero_tier':5,'soldier_tier':4,'level_cap':30},
}
EXPEDITIONS = (
 {'id':'company_border_patrol','name':'Border Patrol','map_id':'company_border_patrol'},
 {'id':'company_river_crossing','name':'The River Crossing','map_id':'company_river_crossing'},
 {'id':'company_old_fortress','name':'The Old Fortress','map_id':'company_old_fortress'},
)

def fail(code, message):
    from .domain import DomainError
    raise DomainError(code, message)

def exact(payload, required=(), optional=()):
    if not isinstance(payload, dict) or set(payload)-set(required)-set(optional) or set(required)-set(payload):
        fail('invalid_input','The requested fields are incomplete or unsupported.')

def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail('invalid_input','A number is outside its permitted range.')
    return value

def identifier(value):
    from .domain import _directory_id
    return _directory_id(value, uuid=True)

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

@lru_cache(maxsize=1)
def hero_costs():
    return json.loads(Path(__file__).with_name('company_hero_costs.json').read_text())['costs']

def hero_points(unit_type, tier, stored_level, bracket):
    if bracket not in BRACKETS: fail('invalid_input','Choose a supported force bracket.')
    b=BRACKETS[bracket]; level=min(stored_level,b['level_cap'])
    if tier>b['hero_tier']: fail('force_review','This hero form exceeds the selected bracket.')
    if unit_type not in hero_costs(): fail('unsupported_ruleset','The hero price catalogue is incomplete.')
    base=max(hero_costs()[unit_type],20*max(1,tier))
    return (base*(100+2*(level-1))*(100+level-1)+9999)//10000,level

def advance_native(unit_type, xp, earned, preferences):
    """Validate exact native XP accounting; terminal AMLA never adds combat stats."""
    integer(xp,0,1000000); integer(earned,0,1000000)
    value=xp+earned; visited=[]
    while TROOPS[unit_type][3] and value>=TROOPS[unit_type][2]:
        value-=TROOPS[unit_type][2]
        choices=TROOPS[unit_type][3]
        selected=preferences.get(unit_type,choices[0])
        if selected not in choices: fail('invalid_input','An advancement preference is not a native branch.')
        visited.append(selected);unit_type=selected
    if not TROOPS[unit_type][3]:value=min(value,TROOPS[unit_type][2]-1)
    return unit_type,value,visited

def validate_native_result(unit_type, xp, earned, final_type, final_xp, preferences, delegated):
    if delegated:
        typ,value,_=advance_native(unit_type,xp,earned,preferences)
        return (typ,value)==(final_type,final_xp)
    # Human advancement dialogs may choose any legal native branch; the worker
    # proves the actual choice. Preferences bind delegated AI, not human input.
    remaining=xp+earned;stack=[(unit_type,remaining)]
    while stack:
        typ,value=stack.pop();_,_,threshold,choices=TROOPS[typ]
        if not choices:
            if (typ,min(value,threshold-1))==(final_type,final_xp):return True
        elif value<threshold:
            if (typ,value)==(final_type,final_xp):return True
        else:
            stack.extend((choice,value-threshold) for choice in choices)
    return False

class CompanyProduct:
    def _company(self, actor, session=None, required=True):
        row=self.db.companies.find_one({'_id':actor},session=session)
        if row is None and required:fail('hero_required','Earn a campaign hero, then enlist your company.')
        return row

    def _company_revision(self, actor, expected, session):
        row=self._company(actor,session)
        integer(expected,0,9223372036854775807)
        if row['revision']!=expected:fail('stale_revision','Your company changed. Refresh before saving.')
        return row

    def _company_available(self, actor, session, allow_assignment=None):
        self._player(actor,session)
        lease=self.db.company_asset_locks.find_one({'owner_id':actor},session=session)
        if lease and lease.get('assignment_id')!=allow_assignment:
            fail('busy','This company is committed to another expedition or defense.')
        if lease and lease.get('run_id'):fail('busy','This company is already locked for a battle.')

    def _wound(self, actor, kind, asset_id, session=None):
        return self.db.company_wounds.find_one({'_id':actor+':'+kind+':'+asset_id},session=session)

    def _soldier_public(self, soldier, session=None):
        cost,level,threshold,_=TROOPS[soldier['unit_type']]
        wound=self._wound(soldier['owner_id'],'soldier',soldier['_id'],session)
        lock=self.db.company_asset_locks.find_one({'_id':'soldier:'+soldier['_id']},session=session)
        return {'id':soldier['_id'],'type':soldier['unit_type'],'name':soldier['name'], 'level':level,
                'xp':soldier['xp'],'total_earned':soldier['total_earned'],'next_xp':threshold,
                'status':wound['kind'] if wound else ('committed' if lock else 'healthy'),
                'recover_at_round':wound.get('recover_at_round') if wound else None,
                'points':cost,'advances':list(TROOPS[soldier['unit_type']][3]),'revision':soldier['revision'],'advancement_preferences':soldier['preferences']}

    def _company_snapshot(self, actor, session=None):
        from .product import owned_heroes
        row=self._company(actor,session,False)
        heroes=owned_heroes(self.db,actor,session)
        for hero in heroes:
            key=hero.get('hero_id',hero.get('id'))
            wound=self._wound(actor,'hero',key,session)
            hero['company_status']=wound['kind'] if wound else 'healthy'
            hero['recover_at_round']=wound.get('recover_at_round') if wound else None
        soldiers=list(self.db.company_soldiers.find({'owner_id':actor,'retired':False},session=session).sort('_id',1))
        return {'revision':row['revision'] if row else 0,'initialized':row is not None,'hero_required':not heroes,
                'capacity':CAPACITY,'soldiers':[self._soldier_public(x,session) for x in soldiers],
                'warband':deepcopy(row['warband']) if row else {'hero_id':'','form_id':'','soldier_ids':[],'bracket':'scout'},
                'location':row.get('location') if row else None,'heroes':heroes,
                'recruit_catalog':[{'type':x,'cost':TROOPS[x][0],'level':1} for x in BASICS],
                'expeditions':list(EXPEDITIONS),'brackets':deepcopy(BRACKETS),
                'can_rest':bool(self.db.company_wounds.find_one({'owner_id':actor,'kind':'rest_wounded'},session=session))}

    def _new_soldier(self, actor, unit_type, session):
        from .domain import _id, _now
        row={'_id':_id(),'owner_id':actor,'unit_type':unit_type,'name':unit_type,'xp':0,'total_earned':0,
             'preferences':{},'revision':0,'retired':False,'created_at':_now()}
        self.db.company_soldiers.insert_one(row,session=session)
        return row

    def _company_command(self, actor, operation, payload, session):
        from .domain import _now
        if operation=='company_initialize':
            exact(payload)
            if self._company(actor,session,False):return self._company_snapshot(actor,session)
            if not self.db.account_heroes.find_one({'account_id':actor},session=session):
                fail('hero_required','Complete a story scenario to discover your first hero.')
            self.db.companies.insert_one({'_id':actor,'revision':0,'created_at':_now(),'location':None,
                'warband':{'hero_id':'','form_id':'','soldier_ids':[],'bracket':'scout'}},session=session)
            for unit_type in BASICS:self._new_soldier(actor,unit_type,session)
            return self._company_snapshot(actor,session)
        fields={
            'company_recruit':('unit_type',), 'company_retire':('soldier_id',),
            'company_select':('hero_id','form_id','soldier_ids','bracket'),
            'company_preferences':('soldier_id','preferences'), 'company_rest':(),
            'company_expedition':('mission_id',)}
        if operation not in fields:fail('invalid_input','Unknown company operation.')
        exact(payload,('expected_revision',)+fields[operation])
        company=self._company_revision(actor,payload['expected_revision'],session)
        if operation in ('company_select','company_expedition'):self._company_available(actor,session)
        if operation=='company_recruit':
            if payload['unit_type'] not in BASICS:fail('invalid_input','Only basic catalogue soldiers may be recruited.')
            if self.db.company_soldiers.count_documents({'owner_id':actor,'retired':False},session=session)>=CAPACITY:
                fail('capacity','Your company already has twelve soldiers.')
            self._new_soldier(actor,payload['unit_type'],session)
        elif operation=='company_retire':
            soldier=self.db.company_soldiers.find_one({'_id':identifier(payload['soldier_id']),'owner_id':actor,'retired':False},session=session)
            if soldier is None:fail('not_found','This soldier is not in your company.')
            if self._wound(actor,'soldier',soldier['_id'],session):fail('wounded','A wounded soldier cannot retire.')
            if self.db.company_asset_locks.find_one({'_id':'soldier:'+soldier['_id']},session=session):fail('busy','This soldier is committed and cannot retire.')
            if soldier['_id'] in company['warband']['soldier_ids']:fail('selected','Remove this soldier from your warband before retiring.')
            self.db.company_soldiers.update_one({'_id':soldier['_id']},{'$set':{'retired':True},'$inc':{'revision':1}},session=session)
        elif operation=='company_select':
            selection={key:deepcopy(payload[key]) for key in ('hero_id','form_id','soldier_ids','bracket')}
            self._company_force(actor,selection,session)
            self.db.companies.update_one({'_id':actor},{'$set':{'warband':selection}},session=session)
        elif operation=='company_preferences':
            soldier=self.db.company_soldiers.find_one({'_id':identifier(payload['soldier_id']),'owner_id':actor,'retired':False},session=session)
            if soldier is None:fail('not_found','This soldier is not in your company.')
            if self._wound(actor,'soldier',soldier['_id'],session):fail('wounded','Wait for this soldier to recover before changing advancement preferences.')
            if self.db.company_asset_locks.find_one({'_id':'soldier:'+soldier['_id']},session=session):fail('busy','This soldier has frozen advancement preferences.')
            prefs=payload['preferences']
            if not isinstance(prefs,dict) or len(prefs)>len(TROOPS):fail('invalid_input','Invalid advancement choices.')
            for source,target in prefs.items():
                if source not in TROOPS or target not in TROOPS[source][3]:fail('invalid_input','Choose an existing native advancement branch.')
            self.db.company_soldiers.update_one({'_id':soldier['_id']},{'$set':{'preferences':prefs},'$inc':{'revision':1}},session=session)
        elif operation=='company_rest':
            for wound in self.db.company_wounds.find({'owner_id':actor,'kind':'rest_wounded'},session=session):
                key='hero:'+actor+':'+wound['asset_id'] if wound['asset_kind']=='hero' else 'soldier:'+wound['asset_id']
                if not self.db.company_asset_locks.find_one({'_id':key},session=session):self.db.company_wounds.delete_one({'_id':wound['_id']},session=session)
        elif operation=='company_expedition':
            mission=next((m for m in EXPEDITIONS if m['id']==payload['mission_id']),None)
            if mission is None:fail('invalid_input','Choose a company expedition.')
            force=self._company_force(actor,company['warband'],session)
            run=self._company_create_expedition(actor,force,mission,session)
            self.db.companies.update_one({'_id':actor},{'$inc':{'revision':1}},session=session)
            return {'battle':self._world_public_contract(run,actor,session)}
        self.db.companies.update_one({'_id':actor},{'$inc':{'revision':1}},session=session)
        return self._company_snapshot(actor,session)

    def _company_force(self, actor, selection, session=None):
        exact(selection,('hero_id','form_id','soldier_ids','bracket'))
        if not isinstance(selection['bracket'],str) or selection['bracket'] not in BRACKETS:fail('invalid_input','Choose a force bracket.')
        ids=selection['soldier_ids']
        if not isinstance(ids,list) or len(ids)>4 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):fail('invalid_input','Choose up to four different soldiers.')
        hero=self._selection(actor,selection['hero_id'],selection['form_id'],session)
        account=self._account(actor,session=session)
        legacy_ids=[account['active_run_id']] if account.get('active_run_id') else []
        network=self.db.network_battle_reservations.find_one({'_id':actor,'kind':'team'},session=session)
        if network:legacy_ids.append(network['run_id'])
        for legacy in self.db.game_runs.find({'_id':{'$in':legacy_ids},'state':{'$in':['draft','running']}},session=session):
            if any(p['account_id']==actor and (p.get('selection') or {}).get('hero_id')==hero['hero_id'] for p in legacy['participants']):fail('busy','This hero is committed to another persistent battle.')
        if self._wound(actor,'hero',hero['hero_id'],session):fail('wounded','This hero must recover before another deployment.')
        points,effective=hero_points(hero['unit_type'],hero['unit_level'],hero['hero_level'],selection['bracket'])
        units=[{'instance_id':'hero:'+actor+':'+hero['hero_id'],'kind':'hero','owner_account_id':actor,
                'hero_id':hero['hero_id'],'form_id':hero['form_id'],'unit_type':hero['unit_type'],'native_level':hero['unit_level'],
                'xp':0,'stored_level':hero['hero_level'],'effective_level':effective,'revision':hero['hero_revision'],
                'advancement_preferences':{},'points':points}]
        for sid in ids:
            identifier(sid)
            row=self.db.company_soldiers.find_one({'_id':sid,'owner_id':actor,'retired':False},session=session)
            if row is None:fail('not_found','A selected soldier is unavailable.')
            if self._wound(actor,'soldier',sid,session):fail('wounded','A selected soldier must recover first.')
            cost,tier,threshold,_=TROOPS[row['unit_type']]
            if tier>BRACKETS[selection['bracket']]['soldier_tier']:fail('force_review','A soldier exceeds the selected bracket.')
            points+=cost
            units.append({'instance_id':sid,'kind':'soldier','owner_account_id':actor,'unit_type':row['unit_type'],
                          'native_level':tier,'xp':row['xp'],'revision':row['revision'],
                          'advancement_preferences':deepcopy(row['preferences']),'points':cost,'recall_cost':20})
        if points>BRACKETS[selection['bracket']]['budget']:fail('force_review','Your warband exceeds this bracket. Review its force.')
        return {'account_id':actor,'username':self._account(actor,session=session)['username'],
                'selection':deepcopy(selection),'points':points,'units':units,'company_revision':self._company(actor,session)['revision']}

    def _company_lock(self, force, session, run_id=None, assignment_id=None):
        from .domain import _now
        for unit in force['units']:
            key=('hero:'+unit['owner_account_id']+':'+unit['hero_id']) if unit['kind']=='hero' else 'soldier:'+unit['instance_id']
            previous=self.db.company_asset_locks.find_one({'_id':key},session=session)
            if previous and (previous.get('assignment_id')!=assignment_id or previous.get('run_id') not in (None,run_id)):
                fail('busy','A selected personal unit is already committed.')
            self.db.company_asset_locks.replace_one({'_id':key},{'_id':key,'owner_id':force['account_id'],
                'run_id':run_id,'assignment_id':assignment_id,'created_at':_now()},upsert=True,session=session)

    def _company_apply_ledger(self, run, evidence, session):
        """Trusted native witness proof only; caller must validate lease/chain first."""
        from .domain import _now
        from .heroes import MAX_XP
        entries=evidence['units'];expected={u['instance_id']:u for a in run['armies'] for u in a['units']}
        if not isinstance(entries,list) or len(entries)!=len(expected) or any(not isinstance(x,dict) or not isinstance(x.get('instance_id'),str) for x in entries) or len({x['instance_id'] for x in entries})!=len(expected):
            fail('invalid_evidence','The native troop ledger is incomplete.')
        rewards=[]
        for entry in entries:
            exact(entry,('instance_id','earned_xp','final_type','final_xp','dead','deployed'))
            unit=expected.get(entry['instance_id'])
            if unit is None or type(entry['dead']) is not bool or type(entry['deployed']) is not bool:fail('invalid_evidence','Unknown native ledger unit.')
            integer(entry['earned_xp'],0,1000000);integer(entry['final_xp'],0,1000000)
            if not entry['deployed'] and (entry['dead'] or entry['earned_xp']):fail('invalid_evidence','An undeployed soldier cannot earn combat XP or die.')
            if unit['kind']=='soldier':
                army=next(a for a in run['armies'] if a['account_id']==unit['owner_account_id'])
                if not validate_native_result(unit['unit_type'],unit['xp'],entry['earned_xp'],entry['final_type'],entry['final_xp'],unit['advancement_preferences'],army['controller']=='worker'):fail('invalid_evidence','Native advancement and earned XP disagree.')
                typ,xp=entry['final_type'],entry['final_xp']
                row=self.db.company_soldiers.find_one({'_id':unit['instance_id'],'owner_id':unit['owner_account_id'],'revision':unit['revision'],'retired':False},session=session)
                if row is None:fail('result_conflict','A committed soldier changed during combat.')
                if row['total_earned']+entry['earned_xp']>MAX_XP:fail('invalid_evidence','Soldier XP exceeds the storage bound.')
                self.db.company_soldiers.update_one({'_id':row['_id']},{'$set':{'unit_type':typ,'xp':xp},'$inc':{'total_earned':entry['earned_xp'],'revision':1}},session=session)
            else:
                if entry['final_type']!=unit['unit_type'] or entry['final_xp']!=0 or entry['earned_xp']!=0:
                    fail('invalid_evidence','A persistent hero uses the frozen form and outcome reward.')
                army=next(a for a in run['armies'] if a['account_id']==unit['owner_account_id'])
                result='draw' if evidence['outcome']=='draw' else ('win' if army['team_id']==evidence['winner_team_id'] else 'loss')
                amount=(20 if result=='win' else 0) if run['kind']=='company' else {'win':20,'loss':10,'draw':10}[result]
                if run.get('neutral_target') and (result!='win' or not run.get('neutral_bonus_available')):amount=0
                current=self._hero(unit['owner_account_id'],unit['hero_id'],session)
                if current['total_experience']+amount>MAX_XP:fail('invalid_evidence','Hero XP exceeds the storage bound.')
                self.db.account_heroes.update_one({'_id':current['_id']},{'$inc':{'total_experience':amount,'revision':1}},session=session)
                rewards.append({'account_id':unit['owner_account_id'],'hero_id':unit['hero_id'],'experience':amount})
            if entry['dead']:
                kind='world_wounded' if run['kind']=='world' else 'rest_wounded'
                asset_id=unit['hero_id'] if unit['kind']=='hero' else unit['instance_id']
                row={'_id':unit['owner_account_id']+':'+unit['kind']+':'+asset_id,'owner_id':unit['owner_account_id'],
                     'asset_kind':unit['kind'],'asset_id':asset_id,'kind':kind,'created_at':_now(),'run_id':run['_id']}
                if kind=='world_wounded':row['recover_at_round']=run['round']+1
                self.db.company_wounds.replace_one({'_id':row['_id']},row,upsert=True,session=session)
        return rewards
