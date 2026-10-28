"""Host-led territorial rounds and personal-company contracts.

Ordinary player commands never accept XP, outcomes or worker evidence. Machine
entry points are separately authenticated by the local battle supervisor.
"""
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid5, NAMESPACE_URL
import re
import json
from .company import CompanyProduct, BALANCE_REVISION, BRACKETS, BASICS, TROOPS, EXPEDITIONS, fail, exact, identifier, integer, fingerprint
from .flexible import DEFAULT_SETTINGS
from .rules import MAPS, team_level

QUERY_FIELDS={'snapshot':(), 'company':(), 'catalog':(), 'castle':('castle_id',), 'battles':(), 'history':(), 'battle':('run_id',), 'command_status':('command_id',)}
COMMAND_FIELDS={
 'company_initialize':(), 'company_recruit':('expected_revision','unit_type'),
 'company_retire':('expected_revision','soldier_id'),
 'company_select':('expected_revision','hero_id','form_id','soldier_ids','bracket'),
 'company_preferences':('expected_revision','soldier_id','preferences'),
 'company_rest':('expected_revision',), 'company_expedition':('expected_revision','mission_id'),
 'skirmish_create':('plan_id',), 'battle_confirm':('run_id',), 'enroll':(), 'station':('castle_id',), 'roadworks':('castle_id',), 'roadworks_propose':('castle_id',), 'governor':('castle_id','account_id'),
 'defense_offer':('castle_id','bracket'), 'defense_approve':('assignment_id',), 'defense_withdraw':('assignment_id',),
 'attack':('origin_id','target_id','bracket'), 'battle_join':('run_id','team_id'),
 'battle_ready':('run_id','ready'), 'battle_approve':('run_id',), 'battle_cancel':('run_id',),
 'war_propose':('opponent_team_id','target_ids','objective_area_id'), 'war_approve':('war_id',)}
TERMINAL=('completed','cancelled')
WORLD_COLLECTIONS=('companies','company_soldiers','company_wounds','company_asset_locks','world_states','world_areas',
 'world_castles','world_teams','world_enrollments','world_enrollment_history','world_orders','world_defenses','world_wars','world_contracts',
 'world_round_participation','world_castle_reservations','world_command_receipts','world_settlements','world_round_receipts')
# Additive schema: unrelated schema-3 documents and legacy replay bytes stay intact.
_STRING={'bsonType':'string'}; _INT={'bsonType':['int','long'],'minimum':0}
WORLD_SCHEMAS={name:{'$jsonSchema':{'bsonType':'object','required':['_id'],'properties':{'_id':_STRING}}} for name in WORLD_COLLECTIONS}
for name,required,props in (
 ('companies',['revision','warband'],{'revision':_INT,'warband':{'bsonType':'object'}}),
 ('company_soldiers',['owner_id','unit_type','xp','total_earned','revision','retired'],{'owner_id':_STRING,'unit_type':{'enum':list(TROOPS)},'xp':_INT,'total_earned':_INT,'revision':_INT,'retired':{'bsonType':'bool'}}),
 ('company_wounds',['owner_id','kind','asset_kind','asset_id'],{'kind':{'enum':['rest_wounded','world_wounded']},'asset_kind':{'enum':['hero','soldier']}}),
 ('world_contracts',['kind','state','generation','armies'],{'kind':{'enum':['company','world','skirmish']},'state':{'enum':['draft','queued','preparing','running','paused','disputed','awaiting_confirmation','completed','cancelled']},'armies':{'bsonType':'array','maxItems':8}}),
 ('world_states',['round','phase','revision','team_ids'],{'round':_INT,'revision':_INT,'phase':{'enum':['planning','deployment','committed','battles','settlement']},'team_ids':{'bsonType':'array','minItems':2,'maxItems':2,'uniqueItems':True}}),
 ('world_command_receipts',['actor_id','command_id','digest','result'],{'actor_id':_STRING,'command_id':_STRING,'digest':_STRING}),
):
 WORLD_SCHEMAS[name]['$jsonSchema']['required']+=required
 WORLD_SCHEMAS[name]['$jsonSchema']['properties'].update(props)
# Every authority/financial record has explicit required persisted fields.
_DATE={'bsonType':'date'}; _NULL={'bsonType':['string','null']}; _BOOL={'bsonType':'bool'}
_REQUIRED={
 'companies':('revision','warband','location','created_at'),
 'company_soldiers':('owner_id','unit_type','name','xp','total_earned','preferences','revision','retired','created_at'),
 'company_wounds':('owner_id','asset_kind','asset_id','kind','run_id','created_at'),
 'company_asset_locks':('owner_id','run_id','assignment_id','created_at'),
 'world_states':('round','phase','revision','team_ids','created_at'),
 'world_areas':('name','castle_ids','capital_id','controller_team_id','state'),
 'world_castles':('area_id','name','kind','owner_team_id','governor_id','roadworks','neighbors','revision','first_occupation_rewarded'),
 'world_teams':('supply','revision','capital_id','frontier_id','enrolled_at'),
 'world_enrollments':('team_id','homeland_frontier_id','created_at'),
 'world_enrollment_history':('owner_id','team_id','homeland_frontier_id','location','created_at','ended_at','round'),
 'world_orders':('owner_id','team_id','round','kind','state','origin_id','target_id'),
 'world_defenses':('owner_id','username','team_id','castle_id','selection','bracket','status','approved','run_id','created_at','revision'),
 'world_wars':('team_ids','captain_ids','target_ids','objective_area_id','approvals','state','start_round','end_round','created_at'),
 'world_contracts':('kind','state','generation','armies','round','created_at','team_ids','captain_ids','attacker_team_id','defender_team_id','target_id','bracket','map_id','settings','approvals','revision'),
 'world_round_participation':('owner_id','round','run_id'),
 'world_castle_reservations':('run_id','round'),
 'world_command_receipts':('actor_id','command_id','digest','result','created_at'),
 'world_settlements':('kind','round','generation','proof_digest','outcome','winner_team_id','hero_rewards','soldier_rewards','team_rewards','captured_castle_id','replay_sha256','ledger_sha256','event_count','combat_verified','completed_rounds','wounds','created_at'),
 'world_round_receipts':('round','combat','income','wars','healed','created_at'),
}
for _collection,_fields in _REQUIRED.items():
    _schema=WORLD_SCHEMAS[_collection]['$jsonSchema'];_schema['required']=['_id',*_fields]
    for _field in _fields:
        if _field in _schema['properties']:continue
        if _field in ('created_at','enrolled_at','ended_at'):_type=_DATE
        elif _field in ('owner_team_id','governor_id','controller_team_id','capital_id','assignment_id','defender_team_id','target_id','objective_area_id','winner_team_id','captured_castle_id','location'):_type=_NULL
        elif _field=='run_id' and _collection in ('company_asset_locks','world_defenses'):_type=_NULL
        elif _field=='round' and _collection in ('world_contracts','world_settlements'):_type={'bsonType':['int','long','null'],'minimum':0}
        elif _field in ('round','start_round','end_round','revision','supply','event_count','completed_rounds','healed','xp','total_earned'):_type=_INT
        elif _field in ('roadworks','first_occupation_rewarded','approved','combat','combat_verified','retired'):_type=_BOOL
        elif _field in ('warband','preferences','selection','settings','result'):_type={'bsonType':'object'}
        elif _field in ('team_ids','captain_ids','castle_ids','neighbors','target_ids','approvals'):_type={'bsonType':'array','items':_STRING,'maxItems':8,'uniqueItems':True}
        elif _field in ('armies','hero_rewards','soldier_rewards','team_rewards','wounds','income','wars'):_type={'bsonType':'array','maxItems':64,'items':{'bsonType':'object'}}
        else:_type={'bsonType':'string','maxLength':500}
        _schema['properties'][_field]=_type
WORLD_SCHEMAS['world_teams']['$jsonSchema']['properties']['supply']={**_INT,'maximum':40}
WORLD_SCHEMAS['world_defenses']['$jsonSchema']['properties']['status']={'enum':['offered','active','needs_review','withdraw_pending','withdrawn']}
WORLD_SCHEMAS['world_castles']['$jsonSchema']['properties']['kind']={'enum':['capital','frontier','supply']}
WORLD_SCHEMAS['companies']['$jsonSchema']['properties']['warband']={'bsonType':'object','required':['hero_id','form_id','soldier_ids','bracket'],'properties':{'hero_id':_STRING,'form_id':_STRING,'soldier_ids':{'bsonType':'array','items':_STRING,'maxItems':4,'uniqueItems':True},'bracket':{'enum':list(BRACKETS)}}}
WORLD_INDEXES={
 'company_soldiers':[((('owner_id',1),('retired',1)),False)],
 'company_asset_locks':[((('owner_id',1),),False),((('run_id',1),),False)],
 'company_wounds':[((('owner_id',1),),False)],
 'world_defenses':[((('castle_id',1),('status',1)),False),((('owner_id',1),('status',1)),False)],
 'world_contracts':[((('state',1),('created_at',1)),False),((('round',1),),False),((('armies.account_id',1),),False)],
 'world_command_receipts':[((('actor_id',1),('command_id',1)),True)],
 'world_enrollments':[((('team_id',1),),False)],
}

def bootstrap_world_schema(db):
    existing=set(db.list_collection_names())
    for name,validator in WORLD_SCHEMAS.items():
        if name not in existing:db.create_collection(name,validator=validator)
        else:db.command('collMod',name,validator=validator,validationLevel='strict',validationAction='error')
    for name,indexes in WORLD_INDEXES.items():
        for keys,unique in indexes:db[name].create_index(list(keys),unique=unique)

def public(value):
    if isinstance(value,datetime):return value.isoformat()
    if isinstance(value,dict):return {('id' if k=='_id' else k):public(v) for k,v in value.items() if k not in ('password_hash','worker_id','lease_until','worker_ticket','native_evidence')}
    if isinstance(value,(list,tuple)):return [public(v) for v in value]
    return value

class WorldProduct(CompanyProduct):
    def _world_state(self, session=None, required=True):
        row=self.db.world_states.find_one({'_id':'world'},session=session)
        if row is None and required:fail('world_unavailable','The host has not opened the world yet.')
        return row

    def _world_team(self, actor, session=None):
        row=self.db.teams.find_one({'members.account_id':actor,'status':'active'},session=session)
        if row is None:fail('team_required','Join a team to enter the world.')
        if not self.db.world_teams.find_one({'_id':row['_id']},session=session):fail('not_enrolled','This team has not enrolled in this world.')
        return row

    def _world_capability(self, actor, team_id, session):
        team=self._team(team_id,session)
        if team['captain_id']!=actor:fail('forbidden','Only this team captain can approve the commitment.')
        return team

    def _world_castle(self, key, session=None):
        row=self.db.world_castles.find_one({'_id':identifier(key)},session=session)
        if row is None:fail('not_found','This castle is unavailable.')
        return row

    def _world_planning(self, session):
        state=self._world_state(session)
        if state['phase'] not in ('planning','deployment'):fail('round_locked','The host has locked this round.')
        # Every strategic mutation touches this fence; phase transition races retry.
        self.db.world_states.update_one({'_id':'world'},{'$inc':{'revision':1}},session=session)
        return state

    def _world_envelope(self, actor, data):
        return {'version':1,'balance_revision':BALANCE_REVISION,'database_generation':self._generation(),
                'actor_id':actor,'data':public(data)}

    def world_query(self, actor_id, operation, payload):
        self._directory_player(actor_id)
        if not isinstance(operation,str) or operation not in QUERY_FIELDS:fail('invalid_input','Unknown world query.')
        exact(payload,QUERY_FIELDS[operation],('before','limit') if operation=='history' else ())
        if operation=='company':data=self._company_snapshot(actor_id)
        elif operation=='catalog':data=self._world_catalog()
        elif operation=='command_status':
            receipt=self.db.world_command_receipts.find_one({'_id':actor_id+':'+identifier(payload['command_id'])})
            data={'found':receipt is not None,'result':receipt['result'] if receipt else None}
        elif operation=='snapshot':data=self._world_snapshot(actor_id)
        elif operation=='castle':data=self._world_castle_view(actor_id,payload['castle_id'])
        elif operation=='battle':data=self._world_battle_view(actor_id,payload['run_id'])
        else:data=self._world_list(actor_id,operation=='history',payload)
        return self._world_envelope(actor_id,data)

    def world_command(self, actor_id, operation, payload):
        if not isinstance(operation,str) or operation not in COMMAND_FIELDS:fail('invalid_input','Unknown world command.')
        optional=('war_id',) if operation=='attack' else ()
        exact(payload,('command_id',)+COMMAND_FIELDS[operation],optional)
        command_id=identifier(payload['command_id']); digest=fingerprint({'operation':operation,'payload':payload})
        body={k:deepcopy(v) for k,v in payload.items() if k!='command_id'}
        def write(session):
            from .domain import _now
            self._player(actor_id,session);self._generation(session)
            key=actor_id+':'+command_id
            previous=self.db.world_command_receipts.find_one({'_id':key},session=session)
            if previous:
                if previous['digest']!=digest:fail('command_conflict','This command identifier already describes another change.')
                return previous['result']
            result=self._company_command(actor_id,operation,body,session) if operation.startswith('company_') else self._world_mutate(actor_id,operation,body,session)
            result=public(result)
            self.db.world_command_receipts.insert_one({'_id':key,'actor_id':actor_id,'command_id':command_id,'digest':digest,'result':result,'created_at':_now()},session=session)
            return result
        result=self._tx(write)
        if operation=='battle_confirm':
            run=self._world_run(body['run_id'])
            if run['state']=='awaiting_confirmation' and set(run.get('confirmations',[]))==set(run['team_ids']):
                self.world_worker_finish(run['_id'],run['worker_id'],run['generation'],run['native_evidence'])
        return self._world_envelope(actor_id,result)

    def _world_catalog(self):
        return {'brackets':deepcopy(BRACKETS),'recruit_catalog':[{'type':t,'cost':TROOPS[t][0],'level':1} for t in BASICS],
            'troops':[{'type':t,'cost':v[0],'level':v[1],'next_xp':v[2],'advances':list(v[3])} for t,v in TROOPS.items()],
            'expeditions':list(EXPEDITIONS),'recall_cost':20,'capacity':12}

    def _world_snapshot(self, actor, session=None):
        state=self._world_state(session,False)
        team=self.db.teams.find_one({'members.account_id':actor,'status':'active'},session=session)
        treasury=self.db.world_teams.find_one({'_id':team['_id']},session=session) if team else None
        company=self._company(actor,session,False)
        teams=list(self.db.teams.find({'_id':{'$in':[r['_id'] for r in self.db.world_teams.find({},session=session).limit(64)]},'status':'active'},{'name':1,'captain_id':1,'members':1},session=session))
        names={t['_id']:t['name'] for t in teams}
        castles=[self._world_castle_labels(x,names,session) for x in self.db.world_castles.find({},session=session)]
        areas=list(self.db.world_areas.find({},session=session))
        for area in areas:area['controller_team_name']=names.get(area['controller_team_id'])
        roster=[{'id':m['account_id'],'username':self._account(m['account_id'],session=session,active=False)['username']} for m in team['members']] if team else []
        return {'enrolled':bool(team and self.db.world_enrollments.find_one({'_id':actor,'team_id':team['_id']},session=session)),
            'round':{'number':state['round'],'phase':state['phase']} if state else None,
            'team':{'id':team['_id'],'name':team['name'],'supply':treasury['supply'] if treasury else 0,'world_eligible':treasury is not None,'last_title':treasury.get('last_title') if treasury else None,'captain':team['captain_id']==actor,'captain_id':team['captain_id'],'members':roster} if team else None,
            'areas':areas,'castles':castles,'teams':[{'id':t['_id'],'name':t['name'],'captain_id':t['captain_id']} for t in teams],
            'company_location':company.get('location') if company else None,
            'defenses':self._world_defense_rows({'$or':[{'owner_id':actor}]+([{'team_id':team['_id']}] if team else [])},session),
            'wars':list(self.db.world_wars.find({'team_ids':team['_id']},session=session).sort('created_at',-1).limit(20)) if team else [],
            'capabilities':{'captain':bool(team and team['captain_id']==actor),'governor':bool(self.db.world_castles.find_one({'governor_id':actor},session=session)), 'company':company is not None}}

    def _world_castle_labels(self, castle, names, session=None):
        castle=deepcopy(castle);castle['owner_team_name']=names.get(castle['owner_team_id'])
        governor=self.db.accounts.find_one({'_id':castle['governor_id']},{'username':1},session=session) if castle['governor_id'] else None
        castle['governor_name']=governor['username'] if governor else None
        return castle

    def _world_defense_rows(self, query, session=None):
        result=[]
        active_query={'$and':[query,{'status':{'$in':['offered','active','needs_review','withdraw_pending']}}]}
        for row in self.db.world_defenses.find(active_query,session=session).sort('created_at',-1).limit(32):
            row=deepcopy(row)
            if row['status'] in ('active','offered','needs_review') and not row.get('run_id'):
                try:self._company_force(row['owner_id'],row['selection'],session)
                except Exception as error:
                    from .domain import DomainError
                    if not isinstance(error,DomainError):raise
                    row['status']='needs_review';row['reason']=error.code
            result.append(row)
        return result

    def _world_castle_view(self, actor, key):
        castle=self._world_castle(key);team=self.db.teams.find_one({'members.account_id':actor,'status':'active'})
        own=bool(team and team['_id']==castle['owner_team_id']);captain=bool(own and team['captain_id']==actor)
        company=self._company(actor,required=False);origins=[];can_station=False
        if team and company and company.get('location'):
            location=company['location']
            if location.startswith('camp:'):
                home=self.db.world_teams.find_one({'_id':team['_id']})
                if home and home['frontier_id']==key and not self.db.world_castles.find_one({'owner_team_id':team['_id']}):origins=[{'id':location,'name':'Recovery camp'}]
            else:
                origin=self._world_castle(location)
                if not own and key in origin['neighbors'] and origin['owner_team_id']==team['_id']:origins=[{'id':location,'name':origin['name']}]
                distance=self._world_distance(location,key,team['_id'])
                can_station=own and (distance==1 or distance==2 and (origin['roadworks'] or castle['roadworks']))
        names={t['_id']:t['name'] for t in self.db.teams.find({'status':'active'},{'name':1}).limit(64)}
        castle=self._world_castle_labels(castle,names)
        return {'castle':castle,'eligible_origins':origins,'can_station':can_station,'defenses':self._world_defense_rows({'castle_id':key,'team_id':team['_id']}) if own else [],
            'contracts':[self._world_public_contract(x,actor) for x in self.db.world_contracts.find({'target_id':key,'state':{'$nin':list(TERMINAL)}}).limit(20) if self._world_can_view(actor,x)],
            'can_govern':captain,'can_develop':captain,'can_propose_development':own and castle['governor_id']==actor,'can_offer_defense':own,'can_attack':bool(team and not own and team['captain_id']==actor)}

    def _world_can_view(self, actor, run, session=None):
        if actor in [a['account_id'] for a in run['armies']] or actor in run.get('captain_ids',[]):return True
        return bool(self.db.teams.find_one({'_id':{'$in':run.get('team_ids',[])},'members.account_id':actor,'status':'active'},session=session))

    def _world_public_contract(self, run, actor, session=None):
        result=deepcopy(run)
        if run['state']=='awaiting_confirmation' and run.get('native_evidence'):
            result['provisional_result']={k:run['native_evidence'][k] for k in ('outcome','winner_team_id','completed_rounds')}
            result['provisional_result']['replay_available']=True
        for key in ('worker_id','lease_until','native_evidence','worker_ticket','proof_digest','loaded_humans','worker_loaded','descriptor'):
            result.pop(key,None)
        result['receipt']=self.db.world_settlements.find_one({'_id':run['_id']},session=session)
        return public(result)

    def _world_run(self, key, session=None):
        row=self.db.world_contracts.find_one({'_id':identifier(key)},session=session)
        if row is None:fail('not_found','This battle contract is unavailable.')
        return row

    def _world_battle_view(self, actor, key):
        run=self._world_run(key)
        if not self._world_can_view(actor,run):fail('forbidden','This battle belongs to another company or team.')
        own=next((a for a in run['armies'] if a['account_id']==actor),None)
        captain=bool(self.db.teams.find_one({'_id':{'$in':run['team_ids']},'captain_id':actor,'status':'active'}))
        return {'battle':self._world_public_contract(run,actor),'can_join':run['state']=='draft',
                'can_ready':bool(own and own['controller']=='human' and run['state']=='draft'),
                'can_approve':captain and run['state']=='draft','can_confirm':captain and run['state']=='awaiting_confirmation','can_cancel':(captain or run['kind']=='company' and own is not None) and run['state'] in ('draft','queued','preparing')}

    def _world_list(self, actor, history, payload):
        team=self.db.teams.find_one({'members.account_id':actor,'status':'active'})
        query={'$or':[{'armies.account_id':actor},{'captain_ids':actor}]+([{'team_ids':team['_id']}] if team else []),
               'state':{'$in':list(TERMINAL)} if history else {'$nin':list(TERMINAL)}}
        before=payload.get('before');limit=integer(payload.get('limit',20),1,30)
        if before:
            cursor=self._world_run(identifier(before))
            if not self._world_can_view(actor,cursor):fail('forbidden','This history cursor is unavailable.')
            query['$and']=[{'$or':[{'created_at':{'$lt':cursor['created_at']}},{'created_at':cursor['created_at'],'_id':{'$lt':before}}]}]
        rows=list(self.db.world_contracts.find(query).sort([('created_at',-1),('_id',-1)]).limit(limit+1))
        items=[]
        for row in rows[:limit]:
            item=self._world_public_contract(row,actor)
            for army in item['armies']:army.pop('units',None);army.pop('selection',None)
            if items and len(json.dumps(items+[item],separators=(',',':')).encode())>180000:break
            items.append(item)
        return {'items':items,'next_before':items[-1]['id'] if items and len(rows)>len(items) else ''}

    def _world_mutate(self, actor, operation, p, session):
        from .domain import _id, _now
        if operation=='skirmish_create':return self._world_skirmish_create(actor,p,session)
        if operation.startswith('battle_'):return self._world_battle_mutate(actor,operation,p,session)
        state=self._world_state(session) if operation=='defense_withdraw' else self._world_planning(session)
        if operation=='defense_withdraw':return self._world_defense_command(actor,None,state,operation,p,session)
        team=self._world_team(actor,session);tid=team['_id']
        if operation=='enroll':
            company=self._company(actor,session)
            prior=self.db.world_enrollments.find_one({'_id':actor},session=session)
            if not prior or prior['team_id']!=tid:
                self._company_available(actor,session)
                if self.db.network_battle_reservations.find_one({'_id':actor},session=session) or self._player(actor,session).get('active_run_id'):
                    fail('busy','Complete your current battle before enrolling.')
                if self.db.world_defenses.find_one({'owner_id':actor,'status':{'$ne':'withdrawn'}},session=session) or self.db.world_contracts.find_one({'armies.account_id':actor,'state':{'$nin':list(TERMINAL)}},session=session):
                    fail('busy','Withdraw standing permission and complete or cancel outstanding contracts first.')
                if prior and (self.db.world_orders.find_one({'owner_id':actor,'round':state['round']},session=session) or self.db.world_round_participation.find_one({'owner_id':actor,'round':state['round']},session=session)):
                    fail('round_limit','Join your new team in the next world round after this round’s orders.')
                home=self.db.world_teams.find_one({'_id':tid},session=session)
                location=home['capital_id'] if home['capital_id'] and self.db.world_castles.find_one({'_id':home['capital_id'],'owner_team_id':tid},session=session) else 'camp:'+tid
                if prior:
                    self.db.world_enrollment_history.insert_one({'_id':_id(),'owner_id':actor,'team_id':prior['team_id'],'homeland_frontier_id':prior['homeland_frontier_id'],'location':company.get('location'),'created_at':prior['created_at'],'ended_at':_now(),'round':state['round']},session=session)
                self.db.world_enrollments.replace_one({'_id':actor},{'_id':actor,'team_id':tid,'homeland_frontier_id':home['frontier_id'],'created_at':_now()},upsert=True,session=session)
                self.db.companies.update_one({'_id':actor},{'$set':{'location':location},'$inc':{'revision':1}},session=session)
            return self._world_snapshot(actor,session)
        if operation in ('war_propose','war_approve'):return self._world_war_command(actor,team,state,operation,p,session)
        if operation.startswith('defense_'):return self._world_defense_command(actor,team,state,operation,p,session)
        if operation=='station':
            self._world_enrolled(actor,tid,session)
            if state['phase']!='planning':fail('round_locked','Stationing orders close before deployment.')
            self._company_available(actor,session);company=self._company(actor,session)
            target=self._world_castle(p['castle_id'],session)
            if target['owner_team_id']!=tid:fail('forbidden','Station only in a friendly castle.')
            source=company.get('location')
            if not source:fail('not_enrolled','Enroll your company in the world first.')
            if source.startswith('camp:'):fail('no_route','A recovery camp only has its fixed attack route.')
            origin=self._world_castle(source,session)
            path=self._world_distance(source,target['_id'],tid,session)
            if path!=1 and not(path==2 and (origin['roadworks'] or target['roadworks'])):fail('no_route','Choose one friendly edge, or two with Roadworks.')
            self._world_order_once(actor,state['round'],'move',session)
            self.db.world_orders.insert_one({'_id':_id(),'owner_id':actor,'team_id':tid,'round':state['round'],'kind':'move','origin_id':source,'target_id':target['_id'],'state':'queued'},session=session)
            return {'queued':True,'castle_id':target['_id']}
        if operation in ('roadworks','roadworks_propose','governor'):
            castle=self._world_castle(p['castle_id'],session)
            if operation=='roadworks_propose':
                if castle['owner_team_id']!=tid or castle['governor_id']!=actor:fail('forbidden','Only this castle governor may propose Roadworks.')
                if castle['roadworks']:fail('already_built','Roadworks already exists here.')
                self.db.world_castles.update_one({'_id':castle['_id']},{'$set':{'roadworks_proposal':{'proposer_id':actor,'created_at':_now()}},'$inc':{'revision':1}},session=session)
                return {'castle':self._world_castle(castle['_id'],session)}
            self._world_capability(actor,tid,session)
            if castle['owner_team_id']!=tid:fail('forbidden','Only the owner captain may change this castle.')
            if operation=='governor':
                target=p['account_id']
                if target is not None and not any(m['account_id']==identifier(target) for m in team['members']):fail('forbidden','Choose a current teammate as governor.')
                self.db.world_castles.update_one({'_id':castle['_id']},{'$set':{'governor_id':target},'$inc':{'revision':1}},session=session)
            else:
                if castle['roadworks']:fail('already_built','This castle already has Roadworks.')
                treasury=self.db.world_teams.find_one({'_id':tid},session=session)
                if treasury['supply']<15:fail('insufficient_supply','Roadworks requires 15 Supply.')
                self.db.world_teams.update_one({'_id':tid},{'$inc':{'supply':-15,'revision':1}},session=session)
                self.db.world_castles.update_one({'_id':castle['_id']},{'$set':{'roadworks':True,'roadworks_proposal':None},'$inc':{'revision':1}},session=session)
            return {'castle':self._world_castle(castle['_id'],session)}
        if operation=='attack':return self._world_attack(actor,team,state,p,session)
        fail('invalid_input','Unsupported world operation.')

    def _world_enrolled(self, actor, team_id, session):
        if not self.db.world_enrollments.find_one({'_id':actor,'team_id':team_id},session=session):
            fail('not_enrolled','Enroll your company with its current team first.')

    def _world_order_once(self, actor, round_number, kind, session):
        if self.db.world_round_participation.find_one({'_id':str(round_number)+':'+actor},session=session):fail('round_limit','Your company already committed an engagement this round.')
        if self.db.world_contracts.find_one({'kind':'world','round':round_number,'armies.account_id':actor,'state':{'$nin':list(TERMINAL)}},session=session):
            fail('round_limit','Your company already has a territorial engagement this round.')
        query={'owner_id':actor,'round':round_number,'state':{'$ne':'cancelled'}}
        # One relocation and one engagement are independent allowances. A pending
        # move cannot supply a future attack origin; deployment uses its applied
        # station, and a published battle cannot subsequently change that origin.
        if kind=='move':query['kind']='move'
        else:query['$or']=[{'kind':{'$ne':'move'}},{'kind':'move','state':'queued'}]
        if self.db.world_orders.find_one(query,session=session):fail('round_limit','This round’s order is already used or its relocation is still pending.')

    def _world_distance(self, source, target, team_id=None, session=None):
        rows={r['_id']:r for r in self.db.world_castles.find({},session=session)};q=deque([(source,0)]);seen=set()
        while q:
            node,dist=q.popleft()
            if node in seen:continue
            seen.add(node)
            if node==target:return dist
            for other in rows.get(node,{}).get('neighbors',[]):
                if team_id is None or rows[other]['owner_team_id']==team_id:q.append((other,dist+1))
        return None

    def _world_defense_command(self, actor, team, state, op, p, session):
        from .domain import _id, _now
        if op=='defense_offer':
            self._world_enrolled(actor,team['_id'],session)
            castle=self._world_castle(p['castle_id'],session)
            if castle['owner_team_id']!=team['_id']:fail('forbidden','Volunteer only for a friendly castle.')
            company=self._company(actor,session);self._company_available(actor,session)
            if company.get('location')!=castle['_id']:fail('wrong_station','Station your company at this castle before volunteering.')
            selection=deepcopy(company['warband']);selection['bracket']=p['bracket'];force=self._company_force(actor,selection,session)
            row={'_id':_id(),'owner_id':actor,'username':force['username'],'team_id':team['_id'],'castle_id':castle['_id'],
                 'selection':selection,'bracket':p['bracket'],'status':'active' if team['captain_id']==actor else 'offered',
                 'approved':team['captain_id']==actor,'captain_approved_by':actor if team['captain_id']==actor else None,'run_id':None,'created_at':_now(),'revision':0}
            self._company_lock(force,session,assignment_id=row['_id']);self.db.world_defenses.insert_one(row,session=session)
            return {'defense':row}
        row=self.db.world_defenses.find_one({'_id':identifier(p['assignment_id'])},session=session)
        if row is None:fail('not_found','This defense permission is unavailable.')
        if op=='defense_approve':
            self._world_capability(actor,row['team_id'],session)
            castle=self._world_castle(row['castle_id'],session)
            if castle['owner_team_id']!=row['team_id'] or row['status'] not in ('offered','needs_review','active'):fail('stale_revision','This defense permission is no longer eligible.')
            self._company_force(row['owner_id'],row['selection'],session)
            self.db.world_defenses.update_one({'_id':row['_id']},{'$set':{'approved':True,'status':'active','captain_approved_by':actor},'$inc':{'revision':1}},session=session)
        else:
            if actor!=row['owner_id']:fail('forbidden','Only the owner can withdraw their standing permission.')
            status='withdraw_pending' if row.get('run_id') else 'withdrawn'
            self.db.world_defenses.update_one({'_id':row['_id']},{'$set':{'status':status},'$inc':{'revision':1}},session=session)
            if status=='withdrawn':self.db.company_asset_locks.delete_many({'assignment_id':row['_id']},session=session)
        return {'defense':self.db.world_defenses.find_one({'_id':row['_id']},session=session)}

    def _world_war_command(self, actor, team, state, op, p, session):
        from .domain import _id, _now
        self._world_capability(actor,team['_id'],session)
        if op=='war_propose':
            other=self._team(identifier(p['opponent_team_id']),session)
            if other['_id']==team['_id'] or not self.db.world_teams.find_one({'_id':other['_id']},session=session):fail('invalid_input','Choose the opposing enrolled team.')
            targets=p['target_ids']
            if not isinstance(targets,list) or not 1<=len(targets)<=6 or any(not isinstance(x,str) for x in targets) or len(set(targets))!=len(targets):fail('invalid_input','Choose one to six distinct objectives.')
            for key in targets:self._world_castle(key,session)
            area=p['objective_area_id']
            if area is not None and not self.db.world_areas.find_one({'_id':identifier(area)},session=session):fail('invalid_input','Choose a world area.')
            if self.db.world_wars.find_one({'state':{'$in':['proposed','active']},'team_ids':team['_id']},session=session):fail('busy','Your team already has a proposed or active war.')
            row={'_id':_id(),'team_ids':[team['_id'],other['_id']],'captain_ids':[team['captain_id'],other['captain_id']],
                 'target_ids':targets,'objective_area_id':area,'objective_initial_controller':self.db.world_areas.find_one({'_id':area},session=session)['controller_team_id'] if area else None,'approvals':[team['_id']],'state':'proposed','start_round':state['round'],
                 'end_round':state['round']+2,'created_at':_now()}
            self.db.world_wars.insert_one(row,session=session);return {'war':row}
        row=self.db.world_wars.find_one({'_id':identifier(p['war_id'])},session=session)
        if not row or team['_id'] not in row['team_ids'] or row['state']!='proposed':fail('forbidden','This war is not awaiting your team approval.')
        approvals=sorted(set(row['approvals']+[team['_id']]))
        self.db.world_wars.update_one({'_id':row['_id']},{'$set':{'approvals':approvals,'state':'active' if len(approvals)==2 else 'proposed','start_round':state['round'],'end_round':state['round']+2}},session=session)
        return {'war':self.db.world_wars.find_one({'_id':row['_id']},session=session)}

    def _world_attack(self, actor, team, state, p, session):
        from .domain import _id, _now
        self._world_capability(actor,team['_id'],session);self._company_available(actor,session)
        self._world_enrolled(actor,team['_id'],session)
        company=self._company(actor,session);origin=p['origin_id'];target=self._world_castle(p['target_id'],session)
        if company.get('location')!=origin:fail('wrong_station','Your company is not stationed at this origin.')
        if target['owner_team_id']==team['_id']:fail('invalid_input','The target is already friendly.')
        if origin=='camp:'+team['_id']:
            homeland=self.db.world_teams.find_one({'_id':team['_id']},session=session)
            if self.db.world_castles.find_one({'owner_team_id':team['_id']},session=session) or target['_id']!=homeland['frontier_id']:fail('no_route','The recovery camp only connects to its fixed homeland frontier.')
        else:
            source=self._world_castle(origin,session)
            if source['owner_team_id']!=team['_id'] or target['_id'] not in source['neighbors']:fail('no_route','Attack from an adjacent friendly castle.')
        war=None
        if target['owner_team_id']:
            war=self.db.world_wars.find_one({'_id':identifier(p.get('war_id')),'state':'active','team_ids':{'$all':[team['_id'],target['owner_team_id']]},'target_ids':target['_id']},session=session)
            if not war:fail('war_required','Both captains must first approve this territorial objective.')
        self._world_order_once(actor,state['round'],'attack',session)
        if self.db.world_orders.find_one({'team_id':team['_id'],'round':state['round'],'kind':'attack','state':{'$ne':'cancelled'}},session=session):fail('round_limit','Your team already has an attack this round.')
        if self.db.world_castle_reservations.find_one({'_id':target['_id']},session=session):fail('castle_busy','Another accepted contest reserves this castle.')
        selection=deepcopy(company['warband']);selection['bracket']=p['bracket'];force=self._company_force(actor,selection,session)
        teams=[team['_id']]+([target['owner_team_id']] if target['owner_team_id'] else [])
        captains=[self._team(t,session)['captain_id'] for t in teams]
        run={'_id':_id(),'generation':_id(),'kind':'world','state':'draft','round':state['round'],'created_at':_now(),
             'team_ids':teams,'captain_ids':captains,'attacker_team_id':team['_id'],'defender_team_id':target['owner_team_id'],
             'target_id':target['_id'],'target_revision':target['revision'],'origin_id':origin,'war_id':war['_id'] if war else None,
             'neutral_target':target['owner_team_id'] is None,'neutral_bonus_available':not target['first_occupation_rewarded'],
             'bracket':p['bracket'],'map_id':'isars-cross','settings':deepcopy(DEFAULT_SETTINGS),'approvals':[],
             'armies':[dict(force,team_id=team['_id'],controller='human',ready=False,assignment_id=None)],'revision':0}
        self.db.world_contracts.insert_one(run,session=session)
        self.db.world_orders.insert_one({'_id':_id(),'owner_id':actor,'team_id':team['_id'],'round':state['round'],'kind':'attack','state':'queued','run_id':run['_id'],'origin_id':origin,'target_id':target['_id']},session=session)
        self.db.world_castle_reservations.insert_one({'_id':target['_id'],'run_id':run['_id'],'round':state['round']},session=session)
        return {'battle':self._world_public_contract(run,actor,session)}

    def _company_create_expedition(self, actor, force, mission, session):
        from .domain import _id, _now
        run={'_id':_id(),'generation':_id(),'kind':'company','state':'queued','round':None,'created_at':_now(),
             'team_ids':[],'captain_ids':[],'attacker_team_id':actor,'defender_team_id':None,
             'target_id':None,'bracket':force['selection']['bracket'],'map_id':mission['map_id'],'mission_id':mission['id'],
             'settings':dict(DEFAULT_SETTINGS,turns=30),'approvals':[],
             'armies':[dict(force,team_id=actor,controller='human',ready=True,assignment_id=None)],'revision':0}
        self._world_reserve_contract(run,session)
        self._world_freeze_descriptor(run)
        self.db.world_contracts.insert_one(run,session=session)
        return run

    def _world_battle_mutate(self, actor, operation, p, session):
        run=self._world_run(p['run_id'],session)
        if not self._world_can_view(actor,run,session):fail('forbidden','This contract belongs to another company or team.')
        if operation=='battle_confirm':
            if run['kind']!='skirmish' or run['state']!='awaiting_confirmation':fail('battle_locked','This battle is not awaiting captain confirmation.')
            team=self.db.teams.find_one({'_id':{'$in':run['team_ids']},'captain_id':actor,'status':'active'},session=session)
            if not team:fail('forbidden','Only a participating current captain can confirm this result.')
            self.db.world_contracts.update_one({'_id':run['_id']},{'$addToSet':{'confirmations':team['_id']}},session=session)
            return {'battle':self._world_public_contract(self._world_run(run['_id'],session),actor,session)}
        if operation=='battle_cancel':
            if run['state'] not in ('draft','queued','preparing'):fail('battle_locked','An active battle cannot be cancelled by a participant.')
            if run['kind']=='company':
                if run['armies'][0]['account_id']!=actor:fail('forbidden','Only the expedition owner can cancel it.')
            elif actor not in [self._team(t,session)['captain_id'] for t in run['team_ids']]:fail('forbidden','Only a participating captain can cancel preparation.')
            self._world_cancel(run,'participant_cancelled',session)
            return {'battle':self._world_public_contract(self._world_run(run['_id'],session),actor,session)}
        if run['kind']=='world':self._world_planning(session)
        if run['state']!='draft':fail('battle_locked','The battle force is already frozen.')
        armies=deepcopy(run['armies']);own=next((a for a in armies if a['account_id']==actor),None)
        if operation=='battle_join':
            team=self.db.teams.find_one({'members.account_id':actor,'status':'active'},session=session)
            if not team:fail('team_required','Join a participating team first.')
            if p['team_id']!=team['_id'] or team['_id'] not in run['team_ids']:fail('forbidden','Join with your current participating team.')
            if own:fail('already_joined','Your company already participates in this contract.')
            if len(armies)>=8:fail('capacity','This battle already has eight companies.')
            if run['kind']=='world':
                self._world_enrolled(actor,team['_id'],session)
                self._world_order_once(actor,run['round'],'battle',session)
            company=self._company(actor,session)
            required_location=(run['origin_id'] if team['_id']==run['attacker_team_id'] else run['target_id']) if run['kind']=='world' else company.get('location')
            if company.get('location')!=required_location:fail('wrong_station','Station at the battle origin or defending castle before joining.')
            assignment=self.db.world_defenses.find_one({'owner_id':actor,'castle_id':run['target_id'],'status':{'$in':['active','offered','needs_review']},'run_id':None},session=session)
            self._company_available(actor,session,assignment['_id'] if assignment else None)
            selection=deepcopy(company['warband']);selection['bracket']=run['bracket']
            force=self._company_force(actor,selection,session)
            side=None
            if run['kind']=='skirmish':
                occupied={a.get('side') for a in armies}
                slot=next((x for x in run['native_slots'] if x['team_id']==team['_id'] and x['side'] not in occupied and (x['kind']=='open' or x['kind']=='reserved' and x['account_id']==actor)),None)
                if not slot:fail('capacity','No eligible human company seat remains for you.')
                side=slot['side']
            armies.append(dict(force,team_id=team['_id'],controller='human',ready=False,assignment_id=assignment['_id'] if assignment else None,side=side))
            for a in armies:a['ready']=False
            run['approvals']=[]
        elif operation=='battle_ready':
            if type(p['ready']) is not bool or own is None or own['controller']!='human':fail('forbidden','Only a participating human owner can set readiness.')
            # Changes since joining require fresh snapshot and every captain/owner consent.
            fresh=self._company_force(actor,own['selection'],session)
            if fresh['units']!=own['units']:
                own.update(fresh)
                for a in armies:a['ready']=False
                run['approvals']=[]
            own['ready']=p['ready']
        elif operation=='battle_approve':
            team=self.db.teams.find_one({'members.account_id':actor,'status':'active'},session=session)
            if not team:fail('team_required','Join a participating team first.')
            self._world_capability(actor,team['_id'],session)
            if team['_id'] not in run['team_ids']:fail('forbidden','Your team is not participating.')
            run['approvals']=sorted(set(run['approvals']+[team['_id']]))
            run.setdefault('approval_captains',{})[team['_id']]=actor
        else:fail('invalid_input','Unsupported battle change.')
        self.db.world_contracts.update_one({'_id':run['_id']},{'$set':{'armies':armies,'approvals':run['approvals'],'approval_captains':run.get('approval_captains',{})},'$inc':{'revision':1}},session=session)
        if run['kind']=='skirmish':self._world_prepare_skirmish(self._world_run(run['_id'],session),session)
        return {'battle':self._world_public_contract(self._world_run(run['_id'],session),actor,session)}

    def _world_reserve_contract(self, run, session):
        from .domain import _now
        for army in run['armies']:
            actor=army['account_id'];self._player(actor,session)
            if run['kind']=='world':
                key=str(run['round'])+':'+actor
                prior=self.db.world_round_participation.find_one({'_id':key},session=session)
                if prior and prior['run_id']!=run['_id']:fail('round_limit','A company already committed to another engagement this round.')
                self.db.world_round_participation.replace_one({'_id':key},{'_id':key,'owner_id':actor,'round':run['round'],'run_id':run['_id']},upsert=True,session=session)
            self._company_lock(army,session,run_id=run['_id'],assignment_id=army.get('assignment_id'))
            if army['controller']=='human':
                self._network_reserve(actor,run['kind'],run['_id'],run['generation'],session)
            if army.get('assignment_id'):
                self.db.world_defenses.update_one({'_id':army['assignment_id']},{'$set':{'run_id':run['_id']}},session=session)
        # Owner-wide fence prevents selecting another hero/soldier subset to bypass
        # company engagement limits. Authored story campaigns are not blocked.
        for army in run['armies']:
            self.db.companies.update_one({'_id':army['account_id']},{'$inc':{'revision':1}},session=session)

    def _world_freeze_descriptor(self, run):
        if run['kind']=='skirmish':return self._world_freeze_skirmish_descriptor(run)
        sides=[]
        ordered=sorted(run['armies'],key=lambda a:(a['team_id']!=run['attacker_team_id'],a['account_id']))
        attackers=[a for a in ordered if a['team_id']==run['attacker_team_id']]
        defenders=[a for a in ordered if a['team_id']!=run['attacker_team_id']]
        size=max(len(attackers),len(defenders),1)
        if size>4:fail('capacity','At most four companies per side may enter this battle.')
        if run['kind']=='company':side_groups=((1,),(2,));run['map_id']=run['mission_id']
        else:
            run['map_id']='isars-cross' if size<=2 else ('hexcake' if size==3 else 'mokena-prairie')
            side_groups=MAPS[run['map_id']]['sides']
        for group,armies in zip(side_groups,(attackers,defenders)):
            for index,side in enumerate(group):
                if index<len(armies):
                    army=armies[index];hero=next(u for u in army['units'] if u['kind']=='hero')
                    hero=deepcopy(hero);hero['hero_level']=hero['effective_level'];hero['xp']=0
                    soldiers=[deepcopy(u) for u in army['units'] if u['kind']=='soldier']
                    for u in army['units']:u['side']=side
                    army['side']=side
                    sides.append({'side':side,'team_id':army['team_id'],'account_id':army['account_id'],'username':army['username'],
                        'controller':army['controller'],'faction':'Loyalists','leader_type':hero['unit_type'],'hero':hero,'soldiers':soldiers})
                elif index==0 and (run['kind']=='company' or run.get('neutral_target')) and group==side_groups[1]:
                    sides.append({'side':side,'team_id':'npc','account_id':None,'username':'Castle defenders' if run['kind']=='world' else 'Expedition opponent',
                        'controller':'worker','faction':'Northerners','leader_type':'Orcish Warrior','hero':None,'soldiers':[]})
                else:sides.append({'side':side,'team_id':'closed','account_id':None,'username':'Closed','controller':'closed','faction':'Loyalists','leader_type':'Lieutenant','hero':None,'soldiers':[]})
        # The native engine reads personal soldiers as recall entries at 20 gold.
        descriptor={'run_id':run['_id'],'generation':run['generation'],'mode':run['kind'],'mission_id':run.get('mission_id',''),
            'map_id':run['map_id'],'settings':deepcopy(run['settings']),'seed':int(run['_id'].replace('-','')[:8],16),
            'balance_revision':BALANCE_REVISION,'round':run['round'],'sides':sides,
            'required_humans':[s['account_id'] for s in sides if s['controller']=='human'],
            'worker_sides':[s['side'] for s in sides if s['controller']=='worker'],
            'units':[dict(deepcopy(u),side=a['side']) for a in ordered for u in a['units']]}
        descriptor['descriptor_sha256']=fingerprint(descriptor)
        run['descriptor']=descriptor;run['scenario_sha256']=None;run['loaded_humans']=[];run['worker_loaded']=False

    def _world_commit(self, state, session):
        from .domain import _now
        for run in self.db.world_contracts.find({'kind':'world','round':state['round'],'state':'draft'},session=session).sort('_id',1):
            target=self._world_castle(run['target_id'],session)
            if target['revision']!=run['target_revision'] or target['owner_team_id']!=run['defender_team_id']:fail('stale_revision','A target changed after planning. Review its contract.')
            current_approvals={t for t in run['approvals'] if run.get('approval_captains',{}).get(t)==self._team(t,session)['captain_id']}
            if run['attacker_team_id'] not in current_approvals:fail('consent_required','The attacking captain must approve this contract.')
            if any(not a['ready'] for a in run['armies'] if a['controller']=='human'):fail('consent_required','Every human owner must be Ready before commitment.')
            # Select only explicit active standing permission matching the bracket;
            # never downgrade forms, substitute assets or enlarge prior permission.
            present={a['account_id'] for a in run['armies']}
            for assignment in self.db.world_defenses.find({'castle_id':run['target_id'],'team_id':run['defender_team_id'],'status':'active','approved':True,'run_id':None},session=session).sort('_id',1):
                if assignment['owner_id'] in present or assignment['bracket']!=run['bracket']:continue
                owner_team=self.db.teams.find_one({'_id':assignment['team_id'],'members.account_id':assignment['owner_id'],'status':'active'},session=session)
                if not owner_team:continue
                force=self._company_force(assignment['owner_id'],assignment['selection'],session)
                run['armies'].append(dict(force,team_id=assignment['team_id'],controller='worker',ready=True,assignment_id=assignment['_id']))
            if not run.get('neutral_target'):
                if not any(a['team_id']==run['defender_team_id'] for a in run['armies']):fail('consent_required','The defending team needs a consenting human or volunteered company.')
                standing=[a for a in run['armies'] if a['team_id']==run['defender_team_id'] and a['controller']=='worker' and a.get('assignment_id')]
                war=self.db.world_wars.find_one({'_id':run['war_id'],'state':'active','target_ids':run['target_id'],'team_ids':{'$all':run['team_ids']}},session=session)
                if run['defender_team_id'] not in current_approvals:
                    if not standing or not war or set(war['approvals'])!=set(run['team_ids']):fail('consent_required','The defending captain must approve this human defense.')
                    run['defense_consent']={'kind':'standing_permission','war_id':war['_id'],'assignment_ids':[a['assignment_id'] for a in standing]}
                    run['approvals']=sorted(set(run['approvals']+[run['defender_team_id']]))
            for army in run['armies']:
                self._world_enrolled(army['account_id'],army['team_id'],session)
                location=self._company(army['account_id'],session).get('location')
                if location!=(run['origin_id'] if army['team_id']==run['attacker_team_id'] else run['target_id']):fail('wrong_station','A company moved away from its approved battle station.')
                team=self._team(army['team_id'],session)
                if not any(m['account_id']==army['account_id'] for m in team['members']):fail('membership_changed','A participating owner left the team.')
                current=self._company_force(army['account_id'],army['selection'],session)
                if army['controller']=='human' and current['units']!=army['units']:fail('force_review','A human force changed after Ready. Refresh its consent.')
                if army['controller']=='worker':army.update(current)
            self._world_reserve_contract(run,session);self._world_freeze_descriptor(run)
            run['state']='queued';run['committed_at']=_now();run['revision']+=1
            self.db.world_contracts.replace_one({'_id':run['_id']},run,session=session)

    def _world_release(self, run, session):
        for army in run['armies']:
            assignment=None
            if army.get('assignment_id'):assignment=self.db.world_defenses.find_one({'_id':army['assignment_id']},session=session)
            retain=bool(assignment and assignment['status']=='active' and self.db.world_castles.find_one({'_id':assignment['castle_id'],'owner_team_id':assignment['team_id']},session=session))
            if retain:
                self.db.company_asset_locks.update_many({'run_id':run['_id'],'assignment_id':assignment['_id']},{'$set':{'run_id':None}},session=session)
                self.db.world_defenses.update_one({'_id':assignment['_id']},{'$set':{'run_id':None}},session=session)
            elif assignment:
                self.db.world_defenses.update_one({'_id':assignment['_id']},{'$set':{'run_id':None,'status':'withdrawn'}},session=session)
            self.db.companies.update_one({'_id':army['account_id']},{'$inc':{'revision':1}},session=session)
        self.db.company_asset_locks.delete_many({'run_id':run['_id']},session=session)
        self.db.network_battle_reservations.delete_many({'run_id':run['_id'],'generation':run['generation'],'kind':{'$in':['world','company','skirmish']}},session=session)
        self.db.world_castle_reservations.delete_many({'run_id':run['_id']},session=session)

    def _world_cancel(self, run, reason, session):
        from .domain import _now
        if run['state'] in TERMINAL:return
        self._world_release(run,session)
        self.db.world_contracts.update_one({'_id':run['_id']},{'$set':{'state':'cancelled','cancel_reason':reason,'finished_at':_now()},'$inc':{'revision':1}},session=session)
        self.db.world_orders.update_many({'run_id':run['_id']},{'$set':{'state':'cancelled'}},session=session)

    def world_admin_snapshot(self, actor_id):
        if self._account(actor_id)['role']!='admin':fail('forbidden','Administrator access is required.')
        data={'world':self._world_state(required=False),'teams':list(self.db.teams.find({'status':'active'},{'name':1,'captain_id':1})),
            'areas':list(self.db.world_areas.find({})),'castles':list(self.db.world_castles.find({})),
            'wars':list(self.db.world_wars.find({}).sort('created_at',-1).limit(30)),
            'contracts':[public(x) for x in self.db.world_contracts.find({'state':{'$nin':list(TERMINAL)}}).sort('created_at',1).limit(64)]}
        for run in data['contracts']:run.pop('descriptor',None)
        return self._world_envelope(actor_id,data)

    def world_admin_command(self, actor_id, operation, payload):
        required={'bootstrap':('team_ids',),'phase':('expected_phase',),'advance':(),'cancel':('run_id','reason'),'enroll_team':('team_id','homeland_frontier_id')}
        if operation not in required:fail('invalid_input','Unknown host action.')
        exact(payload,('command_id',)+required[operation]);command=identifier(payload['command_id']);digest=fingerprint({'operation':operation,'payload':payload})
        def write(session):
            from .domain import _now
            self._admin(actor_id,session)
            key=actor_id+':'+command;prior=self.db.world_command_receipts.find_one({'_id':key},session=session)
            if prior:
                if prior['digest']!=digest:fail('command_conflict','Host command identifier was already used.')
                return prior['result']
            if operation=='bootstrap':result=self._world_bootstrap(payload['team_ids'],session)
            elif operation=='enroll_team':
                self._world_state(session)
                if self.db.world_teams.count_documents({},session=session)>=64:fail('capacity','This world has reached its enrolled-team limit.')
                team=self._team(identifier(payload['team_id']),session)
                frontier=self._world_castle(payload['homeland_frontier_id'],session)
                if frontier['kind']!='frontier':fail('invalid_input','Choose a fixed homeland frontier.')
                if self.db.world_teams.find_one({'_id':team['_id']},session=session):fail('already_enrolled','This team already retains an enrollment.')
                self.db.world_teams.insert_one({'_id':team['_id'],'supply':0,'revision':0,'capital_id':None,'frontier_id':frontier['_id'],'enrolled_at':_now()},session=session)
                result={'team_id':team['_id'],'supply':0,'land_granted':False}
            elif operation=='cancel':
                if not isinstance(payload['reason'],str) or not 3<=len(payload['reason'])<=200:fail('invalid_input','A short cancellation reason is required.')
                run=self._world_run(payload['run_id'],session)
                if run['state']=='completed':fail('battle_locked','A completed result cannot be cancelled.')
                self._world_cancel(run,payload['reason'],session);result={'run_id':run['_id'],'state':'cancelled'}
            else:
                state=self._world_state(session)
                self.db.world_states.update_one({'_id':'world'},{'$inc':{'revision':1}},session=session)
                if operation=='advance':result=self._world_advance(state,session)
                else:
                    if payload['expected_phase']!=state['phase']:fail('stale_revision','The round phase changed. Refresh first.')
                    order=['planning','deployment','committed','battles','settlement'];index=order.index(state['phase'])
                    if index==4:fail('invalid_input','Advance the settled round to begin planning.')
                    if state['phase']=='planning':self._world_apply_moves(state,session)
                    if state['phase']=='deployment':self._world_commit(state,session)
                    if state['phase']=='battles' and self.db.world_contracts.find_one({'kind':'world','round':state['round'],'state':{'$nin':list(TERMINAL)}},session=session):fail('unfinished_battles','Settle or explicitly cancel every engagement first.')
                    self.db.world_states.update_one({'_id':'world'},{'$set':{'phase':order[index+1]}},session=session)
                    result={'round':state['round'],'phase':order[index+1]}
            result=public(result)
            self.db.world_command_receipts.insert_one({'_id':key,'actor_id':actor_id,'command_id':command,'digest':digest,'result':result,'created_at':_now()},session=session)
            self._audit(actor_id,'world_'+operation,'world','Host world session action',None,result,session)
            return result
        return self._world_envelope(actor_id,self._tx(write))

    def _world_bootstrap(self, teams, session):
        from .domain import _now
        if not isinstance(teams,list) or len(teams)!=2 or any(not isinstance(x,str) for x in teams) or len(set(teams))!=2:fail('invalid_input','Select two different existing teams.')
        for key in teams:self._team(identifier(key),session)
        if self._world_state(session,False):fail('already_initialized','This world already exists. Its land and treasury cannot be regenerated.')
        frontiers=[];capitals=[]
        for index,team in enumerate(teams):
            area=str(uuid5(NAMESPACE_URL,'wesnoth-world-1-area-'+str(index)))
            ids={kind:str(uuid5(NAMESPACE_URL,'wesnoth-world-1-'+str(index)+'-'+kind)) for kind in ('capital','frontier','supply')}
            capitals.append(ids['capital']);frontiers.append(ids['frontier'])
            self.db.world_areas.insert_one({'_id':area,'name':('Dawnreach','Mistvale')[index],'castle_ids':list(ids.values()),'capital_id':ids['capital'],'controller_team_id':team,'state':'controlled'},session=session)
            for kind,key in ids.items():
                self.db.world_castles.insert_one({'_id':key,'area_id':area,'name':('Dawnreach' if index==0 else 'Mistvale')+' '+{'capital':'Citadel','frontier':'Gate','supply':'Market'}[kind],
                    'kind':kind,'owner_team_id':team if kind!='supply' else None,'governor_id':None,'roadworks':False,'neighbors':[x for x in ids.values() if x!=key],
                    'revision':0,'first_occupation_rewarded':kind!='supply'},session=session)
            self.db.world_teams.insert_one({'_id':team,'supply':20,'revision':0,'capital_id':ids['capital'],'frontier_id':ids['frontier'],'enrolled_at':_now()},session=session)
        for key,other in zip(frontiers,reversed(frontiers)):
            self.db.world_castles.update_one({'_id':key},{'$addToSet':{'neighbors':other}},session=session)
        self.db.world_states.insert_one({'_id':'world','round':1,'phase':'planning','revision':0,'team_ids':teams,'created_at':_now()},session=session)
        return {'round':1,'phase':'planning','areas':2,'castles':6,'team_ids':teams}

    def _world_apply_moves(self, state, session):
        for order in self.db.world_orders.find({'round':state['round'],'kind':'move','state':'queued'},session=session):
            company=self._company(order['owner_id'],session);self._company_available(order['owner_id'],session)
            if company.get('location')!=order['origin_id']:fail('stale_revision','A moving company changed its station.')
            if self._world_castle(order['target_id'],session)['owner_team_id']!=order['team_id']:fail('stale_revision','A movement target is no longer friendly.')
            self.db.companies.update_one({'_id':order['owner_id']},{'$set':{'location':order['target_id']},'$inc':{'revision':1}},session=session)
            self.db.world_orders.update_one({'_id':order['_id']},{'$set':{'state':'applied'}},session=session)

    def _world_area_control(self, session):
        for area in self.db.world_areas.find({},session=session):
            castles=list(self.db.world_castles.find({'area_id':area['_id']},session=session));capital=next(x for x in castles if x['kind']=='capital')
            owner=capital['owner_team_id'];control=owner if owner and sum(c['owner_team_id']==owner for c in castles)>=2 else None
            self.db.world_areas.update_one({'_id':area['_id']},{'$set':{'controller_team_id':control,'state':'controlled' if control else ('contested' if any(c['owner_team_id'] for c in castles) else 'neutral')}},session=session)

    def _world_advance(self, state, session):
        from .domain import _now
        if state['phase']!='settlement':fail('wrong_phase','Complete the round settlement phase first.')
        if self.db.world_contracts.find_one({'kind':'world','round':state['round'],'state':{'$nin':list(TERMINAL)}},session=session):fail('unfinished_battles','An engagement still needs resolution.')
        combat=bool(self.db.world_settlements.find_one({'kind':'world','round':state['round'],'combat_verified':True,'completed_rounds':{'$gte':1}},session=session))
        income=[]
        for team in self.db.world_teams.find({},session=session):
            amount=0;castles=list(self.db.world_castles.find({'owner_team_id':team['_id']},session=session));capitals=[c['_id'] for c in castles if c['kind']=='capital']
            if combat:
                for castle in castles:
                    production=2 if castle['kind'] in ('capital','supply') else 1
                    if not any(self._world_distance(c,castle['_id'],team['_id'],session) is not None for c in capitals):production//=2
                    amount+=production
                amount=min(6,amount,40-team['supply'])
                self.db.world_teams.update_one({'_id':team['_id']},{'$inc':{'supply':amount,'revision':1}},session=session)
            income.append({'team_id':team['_id'],'supply':amount})
        self._world_area_control(session)
        war_results=[]
        for war in self.db.world_wars.find({'state':'active'},session=session):
            winner=None
            if war['objective_area_id']:
                area=self.db.world_areas.find_one({'_id':war['objective_area_id']},session=session)
                if area['controller_team_id'] in war['team_ids'] and area['controller_team_id']!=war.get('objective_initial_controller'):winner=area['controller_team_id']
            if winner or state['round']>=war['end_round']:
                scores={team:0 for team in war['team_ids']}
                for castle in self.db.world_castles.find({'_id':{'$in':war['target_ids']}},session=session):
                    if castle['owner_team_id'] in scores:scores[castle['owner_team_id']]+=2 if castle['kind']=='capital' else 1
                if not winner and len(set(scores.values()))>1:winner=max(scores,key=scores.get)
                title='World War Victor' if winner else None
                result={'war_id':war['_id'],'winner_team_id':winner,'scores':scores,'round':state['round'],'title':title}
                if winner:
                    self.db.world_teams.update_one({'_id':winner},{'$set':{'last_title':{'war_id':war['_id'],'title':title,'round':state['round']}},'$inc':{'revision':1}},session=session)
                self.db.world_wars.update_one({'_id':war['_id']},{'$set':{'state':'completed','result':result,'finished_at':_now()}},session=session);war_results.append(result)
        next_round=state['round']+1
        healed=self.db.company_wounds.delete_many({'kind':'world_wounded','recover_at_round':{'$lte':next_round}},session=session).deleted_count
        receipt={'_id':str(state['round']),'round':state['round'],'combat':combat,'income':income,'wars':war_results,'healed':healed,'created_at':_now()}
        self.db.world_round_receipts.insert_one(receipt,session=session)
        self.db.world_states.update_one({'_id':'world'},{'$set':{'round':next_round,'phase':'planning'}},session=session)
        return {'round':next_round,'phase':'planning','receipt':receipt}

    def _world_machine_identity(self, worker_id):
        if not isinstance(worker_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',worker_id):fail('invalid_input','Invalid native worker identity.')

    def world_worker_acquire(self, worker_id):
        """Private supervisor API. Never expose through world_command."""
        from .domain import _now
        self._world_machine_identity(worker_id)
        def write(session):
            now=_now();state=self._world_state(session,False)
            # Keep failed evidence and old descriptor. Expiry never awards a win.
            for old in self.db.world_contracts.find({'state':'preparing','prepare_until':{'$lte':now},'has_started':{'$ne':True}},session=session):
                self._world_cancel(old,'preparation_timeout',session)
            for old in self.db.world_contracts.find({'state':'running','lease_until':{'$lte':now}},session=session):
                self.db.world_contracts.update_one({'_id':old['_id']},{'$set':{'state':'paused','pause_reason':'worker_unavailable'}},session=session)
            candidates={'state':'queued','$or':[{'kind':'company'},{'kind':'skirmish'}]}
            if state and state['phase']=='battles':candidates['$or'].append({'kind':'world','round':state['round']})
            run=self.db.world_contracts.find_one({'state':'paused','pause_reason':{'$in':['worker_interrupted','worker_unavailable']},'lease_until':{'$lte':now}},session=session,sort=[('created_at',1),('_id',1)])
            if run is None:run=self.db.world_contracts.find_one(candidates,session=session,sort=[('created_at',1),('_id',1)])
            if run is None:return None
            next_state='paused' if run.get('has_started') else 'preparing'
            self.db.world_contracts.update_one({'_id':run['_id']},{'$set':{'state':next_state,'worker_id':worker_id,'lease_until':now+timedelta(seconds=90),
                'prepare_until':now+timedelta(minutes=5),'loaded_humans':[],'worker_loaded':False}},session=session)
            result=deepcopy(run['descriptor']);result['state']=next_state;return public(result)
        return self._tx(write)

    def world_worker_lease(self, run_id, worker_id, generation):
        from .domain import _now
        self._world_machine_identity(worker_id);identifier(generation)
        def write(session):
            run=self._world_run(run_id,session)
            if run.get('worker_id')!=worker_id or run['generation']!=generation or run['state'] not in ('preparing','running','paused'):
                fail('forbidden','This worker does not hold the native execution lease.')
            self.db.world_contracts.update_one({'_id':run_id},{'$set':{'lease_until':_now()+timedelta(seconds=90)}},session=session)
            return {'run_id':run_id,'generation':generation,'state':run['state']}
        return self._tx(write)

    def _world_loaded(self, run, scenario_sha256, session, actor=None, worker=False):
        from .domain import _now
        if not isinstance(scenario_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',scenario_sha256):fail('invalid_input','Native scenario hash is required.')
        if run.get('scenario_sha256') not in (None,scenario_sha256):
            self.db.world_contracts.update_one({'_id':run['_id']},{'$set':{'state':'disputed','pause_reason':'scenario_mismatch'}},session=session)
            return {'state':'disputed','reason':'scenario_mismatch'}
        if run['state'] not in ('preparing','paused','running'):fail('battle_locked','This native battle is not loading.')
        if run['state']=='preparing' and run.get('prepare_until',_now())<=_now():
            self._world_cancel(run,'preparation_timeout',session);return {'state':'cancelled','reason':'preparation_timeout'}
        loaded=sorted(set(run.get('loaded_humans',[])+([actor] if actor else [])))
        worker_loaded=worker or run.get('worker_loaded',False)
        state='running' if worker_loaded and set(loaded)==set(run['descriptor']['required_humans']) else run['state']
        self.db.world_contracts.update_one({'_id':run['_id']},{'$set':{'scenario_sha256':scenario_sha256,'loaded_humans':loaded,'worker_loaded':worker_loaded,'state':state,'has_started':run.get('has_started',False) or state=='running'}},session=session)
        return {'run_id':run['_id'],'generation':run['generation'],'state':state,'scenario_sha256':scenario_sha256}

    def world_worker_loaded(self, run_id, worker_id, generation, scenario_sha256):
        from .domain import _now
        def write(session):
            run=self._world_run(run_id,session)
            if run.get('worker_id')!=worker_id or run['generation']!=generation or run.get('lease_until',_now())<=_now():fail('forbidden','The worker lease is missing or expired.')
            return self._world_loaded(run,scenario_sha256,session,worker=True)
        return self._tx(write)

    def world_human_join(self, actor_id, run_id):
        def write(session):
            self._player(actor_id,session);run=self._world_run(run_id,session)
            if run['state'] not in ('preparing','running','paused') or actor_id not in run['descriptor']['required_humans']:fail('forbidden','This account has no human controller seat in the battle.')
            lease=self.db.network_battle_reservations.find_one({'_id':actor_id,'run_id':run_id,'generation':run['generation']},session=session)
            if not lease:fail('reservation_lost','The player execution reservation is unavailable.')
            result=deepcopy(run['descriptor']);result['state']=run['state'];result['scenario_sha256']=run.get('scenario_sha256');return public(result)
        return self._tx(write)

    def world_human_loaded(self, actor_id, run_id, generation, scenario_sha256):
        def write(session):
            self._player(actor_id,session);run=self._world_run(run_id,session)
            if run['generation']!=generation or actor_id not in run.get('descriptor',{}).get('required_humans',[]):fail('forbidden','This account cannot load that battle generation.')
            if not self.db.network_battle_reservations.find_one({'_id':actor_id,'run_id':run_id,'generation':generation},session=session):fail('reservation_lost','The execution reservation is missing.')
            return self._world_loaded(run,scenario_sha256,session,actor=actor_id)
        return self._tx(write)

    def world_human_disconnect(self, actor_id, run_id, generation):
        def write(session):
            run=self._world_run(run_id,session)
            if generation!=run['generation'] or actor_id not in run.get('descriptor',{}).get('required_humans',[]):fail('forbidden','This controller does not belong to the battle.')
            if run['state'] in ('running','preparing','paused'):
                self.db.world_contracts.update_one({'_id':run_id},{'$set':{'state':'paused','pause_reason':'human_disconnected'},'$pull':{'loaded_humans':actor_id}},session=session)
            return {'state':'paused' if run['state'] not in TERMINAL else run['state']}
        return self._tx(write)

    def world_worker_pause(self, run_id, worker_id, generation, reason='worker_interrupted'):
        def write(session):
            run=self._world_run(run_id,session)
            if run.get('worker_id')!=worker_id or run['generation']!=generation:fail('forbidden','Worker authority does not match this run.')
            if run['state'] not in TERMINAL:
                self.db.world_contracts.update_one({'_id':run_id},{'$set':{'state':'paused','pause_reason':str(reason)[:100],'worker_loaded':False}},session=session)
            return {'state':'paused' if run['state'] not in TERMINAL else run['state']}
        return self._tx(write)

    def world_worker_finish(self, run_id, worker_id, generation, evidence):
        """Authenticated supervisor only, after durable replay/command-chain checks.

        A boolean client END is never accepted. Native daemon verifies on-disk
        replay/ledger bytes and complete command sequence before calling here.
        """
        from .domain import _now
        self._world_machine_identity(worker_id);identifier(generation)
        exact(evidence,('scenario_sha256','replay_sha256','ledger_sha256','event_count','command_chain_sha256',
            'terminal','outcome','winner_team_id','units','sync_valid','combat_verified','completed_rounds'))
        for key in ('scenario_sha256','replay_sha256','ledger_sha256','command_chain_sha256'):
            if not isinstance(evidence[key],str) or not re.fullmatch(r'[0-9a-f]{64}',evidence[key]):fail('invalid_evidence','A complete native evidence digest is required.')
        integer(evidence['event_count'],1,10000000);integer(evidence['completed_rounds'],0,10000)
        if type(evidence['combat_verified']) is not bool or type(evidence['sync_valid']) is not bool:fail('invalid_evidence','Native synchronization evidence is required.')
        if evidence['terminal'] not in ('victory','defeat','draw') or evidence['outcome'] not in ('win','loss','draw'):fail('invalid_evidence','A native terminal outcome is required.')
        digest=fingerprint(evidence)
        def write(session):
            run=self._world_run(run_id,session)
            if run.get('worker_id')!=worker_id or run['generation']!=generation:fail('forbidden','Only the leased worker may settle this generation.')
            prior=self.db.world_settlements.find_one({'_id':run_id},session=session)
            if prior:
                if prior['proof_digest']!=digest:fail('result_conflict','A different native result already settled this contract.')
                return public(prior)
            if run['state'] not in ('running','paused','awaiting_confirmation'):fail('battle_locked','This battle is not awaiting a native outcome.')
            if not run.get('worker_loaded') or not run.get('scenario_sha256'):fail('invalid_evidence','The native worker never completed loading.')
            if not evidence['sync_valid'] or evidence['scenario_sha256']!=run['scenario_sha256']:
                self.db.world_contracts.update_one({'_id':run_id},{'$set':{'state':'disputed','pause_reason':'native_evidence_conflict'}},session=session)
                return {'run_id':run_id,'state':'disputed'}
            valid_winners=set(run['team_ids']) if run['kind'] in ('world','skirmish') else {run['attacker_team_id']}
            if run.get('neutral_target') or run['kind']=='company':valid_winners.add('npc')
            if (evidence['outcome']=='draw')!=(evidence['winner_team_id'] is None):fail('invalid_evidence','Draw and winner fields disagree.')
            if evidence['winner_team_id'] is not None and evidence['winner_team_id'] not in valid_winners:fail('invalid_evidence','The winning side does not belong to this battle.')
            # Absence of a post-game human upload cannot veto already complete
            # worker evidence. Disconnected before terminal remains paused.
            if run['kind']=='skirmish' and set(run.get('confirmations',[]))!=set(run['team_ids']):
                if run.get('proof_digest') not in (None,digest):fail('result_conflict','The staged native outcome differs.')
                self.db.world_contracts.update_one({'_id':run_id},{'$set':{'state':'awaiting_confirmation','proof_digest':digest,'native_evidence':deepcopy(evidence)}},session=session)
                return {'run_id':run_id,'state':'awaiting_confirmation'}
            rewards=self._company_apply_ledger(run,evidence,session);team_rewards=[];captured=None
            if run['kind']=='skirmish':
                for tid in run['team_ids']:
                    outcome='draw' if evidence['outcome']=='draw' else ('win' if tid==evidence['winner_team_id'] else 'loss')
                    amount={'win':100,'loss':25,'draw':50}[outcome];team=self._team(tid,session)
                    self.db.teams.update_one({'_id':tid},{'$inc':{'experience':amount,'revision':1},'$set':{'level':team_level(team['experience']+amount)}},session=session)
                    team_rewards.append({'team_id':tid,'experience':amount})
            if run['kind']=='world':
                target=self._world_castle(run['target_id'],session)
                if target['revision']!=run['target_revision'] or target['owner_team_id']!=run['defender_team_id']:fail('result_conflict','The reserved target changed during the battle.')
                if not self.db.world_castle_reservations.find_one({'_id':target['_id'],'run_id':run_id},session=session):fail('reservation_lost','The castle reservation is missing.')
                for tid in run['team_ids']:
                    outcome='draw' if evidence['outcome']=='draw' else ('win' if tid==evidence['winner_team_id'] else 'loss')
                    amount={'win':100,'loss':25,'draw':50}[outcome]
                    if run['neutral_target']:amount=100 if outcome=='win' and run['neutral_bonus_available'] else 0
                    team=self._team(tid,session);new_xp=team['experience']+amount
                    if new_xp>9223372036854775807:fail('invalid_evidence','Team XP exceeds the storage bound.')
                    self.db.teams.update_one({'_id':tid},{'$inc':{'experience':amount,'revision':1},'$set':{'level':team_level(new_xp)}},session=session)
                    team_rewards.append({'team_id':tid,'experience':amount})
                if evidence['winner_team_id']==run['attacker_team_id']:
                    captured=target['_id'];self._world_capture(run,target,session)
                self._world_area_control(session)
            frozen={u['instance_id']:u for a in run['armies'] for u in a['units']}
            soldier_rewards=[{'owner_id':frozen[e['instance_id']]['owner_account_id'],'soldier_id':e['instance_id'],
                'before_type':frozen[e['instance_id']]['unit_type'],'after_type':e['final_type'],'earned_xp':e['earned_xp'],
                'final_xp':e['final_xp'],'dead':e['dead'],'deployed':e['deployed'],
                'recover_at_round':run['round']+1 if e['dead'] and run['kind']=='world' else None}
                for e in evidence['units'] if frozen[e['instance_id']]['kind']=='soldier']
            receipt={'_id':run_id,'kind':run['kind'],'round':run['round'],'generation':generation,'proof_digest':digest,
                'outcome':evidence['outcome'],'winner_team_id':evidence['winner_team_id'],'hero_rewards':rewards,'soldier_rewards':soldier_rewards,'team_rewards':team_rewards,
                'captured_castle_id':captured,'replay_sha256':evidence['replay_sha256'],'ledger_sha256':evidence['ledger_sha256'],
                'event_count':evidence['event_count'],'combat_verified':evidence['combat_verified'],'completed_rounds':evidence['completed_rounds'],
                'wounds':list(self.db.company_wounds.find({'run_id':run_id},session=session)),'created_at':_now()}
            self.db.world_settlements.insert_one(receipt,session=session)
            self.db.world_contracts.update_one({'_id':run_id},{'$set':{'state':'completed','finished_at':_now(),'native_evidence':deepcopy(evidence)},'$inc':{'revision':1}},session=session)
            self._world_release(run,session)
            return public(self.db.world_settlements.find_one({'_id':run_id},session=session))
        return self._tx(write)

    def _world_capture(self, run, castle, session):
        old=castle['owner_team_id'];new=run['attacker_team_id']
        self.db.world_castles.update_one({'_id':castle['_id']},{'$set':{'owner_team_id':new,'governor_id':None,'roadworks_proposal':None,'first_occupation_rewarded':True},'$inc':{'revision':1}},session=session)
        for army in run['armies']:
            if army['team_id']==new:self.db.companies.update_one({'_id':army['account_id']},{'$set':{'location':castle['_id']},'$inc':{'revision':1}},session=session)
        for defense in self.db.world_defenses.find({'castle_id':castle['_id'],'status':{'$ne':'withdrawn'}},session=session):
            self.db.world_defenses.update_one({'_id':defense['_id']},{'$set':{'status':'withdrawn','approved':False}},session=session)
            # Another locked battle never shares assets. Its reservation remains
            # until that contract releases; uncommitted assignments end now.
            self.db.company_asset_locks.delete_many({'assignment_id':defense['_id'],'run_id':None},session=session)
        for company in self.db.companies.find({'location':castle['_id']},session=session):
            enrollment=self.db.world_enrollments.find_one({'_id':company['_id']},session=session)
            if not enrollment or enrollment['team_id']==new:continue
            tid=enrollment['team_id'];choices=[]
            for other in self.db.world_castles.find({'owner_team_id':tid},session=session):
                distance=self._world_distance(castle['_id'],other['_id'],None,session)
                if distance is not None:choices.append((distance,other['_id']))
            location=min(choices)[1] if choices else 'camp:'+tid
            self.db.companies.update_one({'_id':company['_id']},{'$set':{'location':location},'$inc':{'revision':1}},session=session)

    def world_replay_authorize(self, actor_id, run_id):
        self._directory_player(actor_id);run=self._world_run(run_id)
        if run['state']!='completed' or not self._world_can_view(actor_id,run):fail('forbidden','This replay is not available to this account.')
        receipt=self.db.world_settlements.find_one({'_id':run_id})
        return {'run_id':run_id,'generation':run['generation'],'replay_sha256':receipt['replay_sha256']}

    def _world_skirmish_create(self, actor, payload, session):
        from .domain import _id, _now
        source=self._run(identifier(payload['plan_id']),session)
        if source.get('army_contract_id'):
            run=self._world_run(source['army_contract_id'],session)
            if not self._world_can_view(actor,run,session):fail('forbidden','This plan belongs to another team.')
            return {'battle':self._world_public_contract(run,actor,session)}
        if source.get('plan_format')!=2 or source['state']!='draft' or source.get('shared_room',{}).get('state') in ('preparing','running'):
            fail('battle_locked','Choose an unprepared draft before setting ordinary readiness.')
        teams=self._flex_teams(source,session)
        if actor not in [t['captain_id'] for t in teams]:fail('forbidden','Only a participating captain may choose company mode.')
        if self.db.network_battle_reservations.find_one({'run_id':source['_id']},session=session):fail('busy','The original plan already reserves players.')
        slots=deepcopy(source['slots'])
        for participant in source['participants']:
            slot=next(s for s in slots if s['side']==participant['side']);slot.update(kind='reserved',account_id=participant['account_id'])
        company=self._company(actor,session)
        run={'_id':_id(),'generation':_id(),'kind':'skirmish','state':'draft','round':None,'created_at':_now(),
            'team_ids':source['team_ids'],'captain_ids':[t['captain_id'] for t in teams],
            'attacker_team_id':source['team_ids'][0],'defender_team_id':source['team_ids'][1],
            'target_id':None,'bracket':company['warband']['bracket'],'map_id':source['map_id'],'settings':deepcopy(source['settings']),
            'area_id':source['area_id'],'source_plan_id':source['_id'],'native_slots':slots,'approvals':[],'armies':[],
            'confirmations':[],'ranked':False,'revision':0}
        self.db.world_contracts.insert_one(run,session=session)
        self.db.game_runs.update_one({'_id':source['_id']},{'$set':{'state':'cancelled','army_contract_id':run['_id'],'cancel_reason':'converted_to_companies'},'$inc':{'revision':1}},session=session)
        return {'battle':self._world_public_contract(run,actor,session)}

    def _world_prepare_skirmish(self, run, session):
        if set(run['approvals'])!=set(run['team_ids']) or any(run.get('approval_captains',{}).get(t)!=self._team(t,session)['captain_id'] for t in run['team_ids']):return
        humans=[s for s in run['native_slots'] if s['kind'] in ('open','reserved')]
        if {a['side'] for a in run['armies']}!={s['side'] for s in humans} or any(not a['ready'] for a in run['armies']):return
        counts=[sum(s['kind']!='closed' and s['team_id']==t for s in run['native_slots']) for t in run['team_ids']]
        if counts[0]!=counts[1]:fail('invalid_lineup','Enable the same number of sides for both teams.')
        teams=[self._team(t,session) for t in run['team_ids']]
        if teams[0]['area_id']!=teams[1]['area_id'] or teams[0]['area_id']!=run['area_id']:fail('different_area','Ordinary team skirmishes require the same area.')
        for army in run['armies']:
            team=next(t for t in teams if t['_id']==army['team_id'])
            if not any(m['account_id']==army['account_id'] for m in team['members']):fail('membership_changed','A selected company owner left the team.')
            current=self._company_force(army['account_id'],army['selection'],session)
            if current['units']!=army['units']:fail('force_review','A company changed after readiness.')
        self._world_reserve_contract(run,session);self._world_freeze_descriptor(run);run['state']='queued';run['revision']+=1
        self.db.world_contracts.replace_one({'_id':run['_id']},run,session=session)

    def _world_freeze_skirmish_descriptor(self, run):
        sides=[]
        for slot in run['native_slots']:
            army=next((a for a in run['armies'] if a['side']==slot['side']),None)
            if army:
                hero=deepcopy(next(u for u in army['units'] if u['kind']=='hero'));hero['hero_level']=hero['effective_level']
                side={'side':slot['side'],'team_id':army['team_id'],'account_id':army['account_id'],'username':army['username'],
                    'controller':'human','faction':'Loyalists','leader_type':hero['unit_type'],'hero':hero,
                    'soldiers':[deepcopy(u) for u in army['units'] if u['kind']=='soldier']}
            else:
                ai=slot['kind']=='ai'
                side={'side':slot['side'],'team_id':slot['team_id'],'account_id':None,'username':'Computer' if ai else 'Closed',
                    'controller':'worker' if ai else 'closed','faction':slot['ai_faction'] if ai else 'Loyalists',
                    'leader_type':slot['ai_leader'] if ai else 'Lieutenant','hero':None,'soldiers':[]}
            sides.append(side)
        descriptor={'run_id':run['_id'],'generation':run['generation'],'mode':'skirmish','mission_id':'','map_id':run['map_id'],
            'settings':deepcopy(run['settings']),'seed':int(run['_id'].replace('-','')[:8],16),'balance_revision':BALANCE_REVISION,'round':None,'sides':sides,
            'required_humans':[a['account_id'] for a in run['armies']],'worker_sides':[s['side'] for s in sides if s['controller']=='worker'],
            'units':[dict(deepcopy(u),side=a['side']) for a in run['armies'] for u in a['units']]}
        descriptor['descriptor_sha256']=fingerprint(descriptor);run['descriptor']=descriptor
        run['scenario_sha256']=None;run['loaded_humans']=[];run['worker_loaded']=False

    def _company_external_hero_guard(self, actor, hero_id, run_id, session):
        key='hero:'+actor+':'+hero_id
        lock=self.db.company_asset_locks.find_one({'_id':key},session=session)
        if lock and (run_id is None or lock.get('run_id')!=run_id):fail('busy','This hero is committed to a personal company or standing defense.')
        if self._wound(actor,'hero',hero_id,session):fail('wounded','This hero must recover before another persistent deployment.')

    def _network_reserve(self, actor_id, kind, run_id, generation, session, expires_at=None):
        if kind=='team':
            run=self.db.game_runs.find_one({'_id':run_id},session=session)
            if run:
                participant=next((p for p in run['participants'] if p['account_id']==actor_id),None)
                if participant and participant.get('selection'):
                    self._company_external_hero_guard(actor_id,participant['selection']['hero_id'],run_id,session)
        elif kind in ('company','world','skirmish'):
            account=self._account(actor_id,session=session)
            if account.get('active_run_id') not in (None,run_id):fail('busy','Finish the active game before controlling another persistent battle.')
        return super()._network_reserve(actor_id,kind,run_id,generation,session,expires_at)

    def progression_start(self, actor_id, mission_id, hero_id, form_id):
        # Retained old training API, with the same transactions/rewards and an
        # additional permanent-asset fence. Authored story_begin/checkpoint are
        # intentionally untouched, so campaign rewards can accrue while pledged.
        import secrets
        from .domain import _id, _now
        from .rules import MISSIONS, RULESET_VERSION, MISSION_VERSION
        if mission_id not in MISSIONS:fail('invalid_mission','Choose an approved training mission.')
        def write(session):
            actor=self._player(actor_id,session)
            self._company_external_hero_guard(actor_id,hero_id,None,session)
            if any(m not in actor.get('training_completed',[]) for m in MISSIONS[:MISSIONS.index(mission_id)]):fail('mission_locked','Complete the previous training mission first.')
            selection=self._selection(actor_id,hero_id,form_id,session);run_id=_id()
            self._reserve_account(actor_id,run_id,session)
            run={'_id':run_id,'kind':'campaign','state':'running','ruleset_version':RULESET_VERSION,'mission_id':mission_id,
                'database_generation':self._generation(session),'participants':[{'account_id':actor_id,'selection':selection}],
                'created_at':_now(),'started_at':_now(),'native_campaign':{'mission_version':MISSION_VERSION,'nonce':secrets.token_hex(32),'username':actor['username']}}
            self.db.game_runs.insert_one(run,session=session)
            return {'run':self._campaign_record(actor_id,run,nonce=True,session=session)}
        return self._tx(write)
