"""Local operator screens: bounded queries, explicit projections and domain actions.

These pages intentionally never serialize Mongo documents wholesale. Player
passwords, admission tickets, worker secrets and native command streams do not
belong in an operator's browser.
"""
from datetime import datetime, timezone
import re

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from .domain import DomainError
from .product import owned_heroes
from .heroes import catalog_hero, catalog_form


PAGE_SIZE = 25
TERMINAL = ('completed', 'cancelled')


def shown(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ', '.join(shown(x) for x in value if isinstance(x, (str, int))) or '—'
    return '—'


def columns(*names):
    return [{'key': key, 'label': label} for key, label in names]


def section(title, headings, rows, description=''):
    return {'title': title, 'columns': columns(*headings), 'rows': rows,
            'description': description, 'empty_message': 'No records.'}


def field(name, label='', value='', kind='hidden', **kwargs):
    return dict(name=name, label=label, value=value, type=kind, **kwargs)


def action(title, endpoint, values, revision, description, *, extra=(), danger=True):
    return {'title': title, 'description': description, 'url': url_for(endpoint, **values),
            'fields': [field('revision', value=revision), *extra,
                       field('reason', 'Reason', kind='textarea', required=True, minlength=3, maxlength=500),
                       field('confirmation', 'I have reviewed this change.', 'confirmed', 'checkbox', required=True)],
            'button': title, 'danger': danger}


# Each category explicitly names every browser-visible database field.
SPECS = {
    'plans': ('game_runs', {'kind': 'alliance'}, ('_id', 'map_id'),
              ('kind', 'state', 'map_id', 'team_ids', 'participants', 'ready', 'revision', 'created_at'), 'Team battles'),
    'campaigns': ('game_runs', {'kind': 'campaign'}, ('_id', 'campaign_id', 'mission_id'),
                  ('kind', 'state', 'campaign_id', 'mission_id', 'next_scenario_id', 'next_checkpoint', 'participants', 'created_at'), 'Campaign progress'),
    'contracts': ('world_contracts', {}, ('_id', 'map_id', 'kind'),
                  ('kind', 'state', 'map_id', 'round', 'bracket', 'team_ids', 'target_id', 'revision', 'created_at'), 'Company & World battles'),
    'castles': ('world_castles', {}, ('_id', 'name', 'kind'),
                ('name', 'kind', 'area_id', 'owner_team_id', 'governor_id', 'roadworks', 'revision'), 'Castles'),
    'defenses': ('world_defenses', {}, ('_id', 'username', 'castle_id'),
                 ('owner_id', 'username', 'team_id', 'castle_id', 'bracket', 'status', 'approved', 'run_id', 'revision', 'created_at'), 'Standing defenses'),
    'wars': ('world_wars', {}, ('_id', 'state'),
             ('team_ids', 'state', 'start_round', 'end_round', 'objective_area_id', 'target_ids', 'created_at'), 'Area wars'),
    'soldiers': ('company_soldiers', {}, ('_id', 'name', 'unit_type', 'owner_id'),
                 ('owner_id', 'name', 'unit_type', 'xp', 'total_earned', 'retired', 'revision', 'created_at'), 'Soldiers'),
    'heroes': ('account_heroes', {}, ('hero_id', 'account_id'),
               ('account_id', 'hero_id', 'forms', 'total_experience', 'revision'), 'Earned heroes'),
    'history': ('world_settlements', {}, ('_id', 'kind', 'outcome'),
                ('kind', 'round', 'outcome', 'winner_team_id', 'captured_castle_id', 'combat_verified', 'completed_rounds', 'created_at'), 'Company & territorial results'),
}
STATES = ('draft', 'queued', 'preparing', 'running', 'paused', 'disputed', 'awaiting_confirmation',
          'completed', 'cancelled', 'active', 'suspended', 'archived', 'offered', 'needs_review', 'withdraw_pending', 'withdrawn')


class AdminConsole:
    def __init__(self, db, domain):
        self.db, self.domain = db, domain

    def name(self, collection, identity):
        if not identity:
            return '—'
        key = 'username' if collection == 'accounts' else 'name'
        row = self.db[collection].find_one({'_id': identity}, {key: 1})
        return row.get(key, identity) if row else identity

    def names(self, collection, ids):
        return ', '.join(self.name(collection, identity) for identity in ids) or '—'

    def query(self, collection, base, fields, search=(), status_field='state'):
        if set(request.args) - {'q', 'state', 'page'} or any(len(request.args.getlist(k)) != 1 for k in request.args):
            abort(400)
        q, state, page = request.args.get('q', '').strip(), request.args.get('state', ''), request.args.get('page', '1')
        if len(q) > 80 or state not in ('', *STATES) or not re.fullmatch(r'[1-9][0-9]{0,3}', page):
            abort(400)
        query = dict(base)
        if q and search:
            query['$or'] = [{key: {'$regex': re.escape(q), '$options': 'i'}} for key in search]
        if state:
            query[status_field] = state
        page = int(page)
        rows = list(self.db[collection].find(query, {key: 1 for key in ('_id', *fields)})
                    .sort('_id', 1).skip((page-1)*PAGE_SIZE).limit(PAGE_SIZE+1))
        params = dict(request.view_args or {}, q=q, state=state)
        pagination = {'previous_url': url_for(request.endpoint, **params, page=page-1) if page > 1 else None,
                      'next_url': url_for(request.endpoint, **params, page=page+1) if len(rows) > PAGE_SIZE else None,
                      'label': f'Page {page} · {PAGE_SIZE} records per page'}
        filters = [{'name': 'q', 'label': 'Search', 'value': q},
                   {'name': 'state', 'label': 'Status', 'value': state,
                    'options': [{'value': '', 'label': 'All statuses'}] + [{'value': s, 'label': s.replace('_', ' ').title()} for s in STATES]}]
        return rows[:PAGE_SIZE], filters, pagination

    def listing(self, title, subtitle, headings, rows, filters=(), pagination=None):
        return render_template('management_list.html', page={'title': title, 'subtitle': subtitle,
            'columns': columns(*headings), 'rows': rows, 'filters': filters, 'pagination': pagination,
            'reset_url': request.path,
            'primary_actions': [{'label': 'Refresh', 'url': request.full_path.rstrip('?')}],
            'empty_message': 'No matching records. Try another search or status.'})

    def detail(self, title, subtitle, back, summary, sections=(), actions=()):
        return render_template('management_detail.html', page={'title': title, 'subtitle': subtitle,
            'back_url': back, 'summary': [{'label': k, 'value': shown(v)} for k, v in summary],
            'sections': sections, 'actions': actions})

    def dashboard(self):
        definitions = [('Players', 'accounts', {'role': 'player'}, 'accounts'),
                       ('Teams', 'teams', {'status': 'active'}, 'teams'),
                       ('Companies', 'companies', {}, 'admin_companies'),
                       ('Team plans', 'game_runs', {'kind': 'alliance', 'state': 'draft'}, 'admin_plans'),
                       ('Active engagements', 'world_contracts', {'state': {'$nin': list(TERMINAL)}}, 'admin_contracts'),
                       ('Earned heroes', 'account_heroes', {}, 'admin_records')]
        metrics = [{'label': label, 'value': self.db[col].count_documents(query),
                    'url': url_for(endpoint, **({'category': 'heroes'} if endpoint == 'admin_records' else {}))}
                   for label, col, query, endpoint in definitions]
        recent = list(self.db.game_runs.find({}, {'_id': 1, 'kind': 1, 'state': 1, 'created_at': 1, 'map_id': 1, 'campaign_id': 1})
                      .sort([('created_at', -1), ('_id', 1)]).limit(10))
        for row in recent:
            row.update(detail_url=url_for('run_detail', run_id=row['_id']), title=row.get('campaign_id') or row.get('map_id') or 'Recorded game', created_at=shown(row.get('created_at')))
        return render_template('dashboard.html', metrics=metrics, recent_runs=recent)

    def accounts(self):
        records, filters, pagination = self.query('accounts', {}, ('username', 'role', 'status', 'revision'), ('username', '_id'), 'status')
        for row in records:
            row['heroes'] = list(self.db.account_heroes.find({'account_id': row['_id']}, {'_id': 1}).limit(117))
        return render_template('accounts.html', records=records, filters=filters, pagination=pagination)

    def teams(self):
        rows, filters, pagination = self.query('teams', {}, ('name', 'area_id', 'captain_id', 'members', 'experience', 'rating', 'status'), ('name', '_id'), 'status')
        for row in rows:
            row.update(detail_url=url_for('admin_team_detail', team_id=row['_id']),
                       area=self.name('areas', row.get('area_id')), captain=self.name('accounts', row.get('captain_id')),
                       seats=f"{len(row.get('members', []))}/8")
        return self.listing('Teams', 'Roster, captain, administrative area and battle history.',
            [('name', 'Team'), ('area', 'Area'), ('captain', 'Captain'), ('seats', 'Members'), ('rating', 'Rating'), ('status', 'Status')], rows, filters, pagination)

    def team(self, identity):
        row = self.db.teams.find_one({'_id': identity}, {k: 1 for k in ('name','status','revision','captain_id','area_id','members','join_requests','experience','level','rating')})
        if row is None: abort(404)
        members = [{'name': self.name('accounts', m['account_id']), 'role': 'Captain' if m['account_id'] == row['captain_id'] else 'Member',
                    'joined': shown(m.get('joined_at')), 'detail_url': url_for('account_detail', account_id=m['account_id'])} for m in row['members']]
        applications = [{'name': self.name('accounts', i), 'detail_url': url_for('account_detail', account_id=i)} for i in row.get('join_requests', [])]
        plans = self.run_rows({'kind': 'alliance', 'team_ids': identity})
        sections = [section('Roster', [('name','Player'),('role','Role'),('joined','Joined')],members),
                    section('Applications', [('name','Applicant')], applications),
                    section('Recent Team battles', [('title','Battle'),('state','State'),('created','Created')],plans)]
        controls=[]
        if row['status']=='active':
            members_options=[{'value':m['account_id'],'label':self.name('accounts',m['account_id'])} for m in row['members']]
            for op,title,extra in (
                ('rename','Rename Team',field('value','Team name',row['name'],'text',required=True,minlength=3,maxlength=40)),
                ('captain','Change captain',field('value','New captain',kind='select',options=[x for x in members_options if x['value']!=row['captain_id']],required=True)),
                ('remove_member','Remove member',field('value','Member',kind='select',options=[x for x in members_options if x['value']!=row['captain_id']],required=True))):
                if op!='rename' and len(members_options)<2:continue
                controls.append(action(title,'admin_team_action',{'team_id':identity},row['revision'],
                    'Active battles and territorial commitments must be resolved first. Saved plan consent is invalidated when required.',
                    extra=[field('operation',value=op),extra],danger=op!='rename'))
            areas=list(self.db.areas.find({'enabled':True},{'name':1}).limit(500))
            controls.append(action('Move administrative area','admin_team_action',{'team_id':identity},row['revision'],
                'Geographical Castle ownership is unchanged. Prepared battles and territorial commitments must be resolved first.',
                extra=[field('operation',value='move_area'),field('value','Area',row['area_id'],'select',required=True,
                    options=[{'value':a['_id'],'label':a['name']} for a in areas])]))
        return self.detail(row['name'],'Team management',url_for('teams'),
            [('Status',row['status']),('Area',self.name('areas',row['area_id'])),('Captain',self.name('accounts',row['captain_id'])),
             ('Level',row['level']),('Team XP',row['experience']),('Rating',row['rating']),('Record',identity)],sections,controls)

    def run_rows(self, query):
        return [{'title':r.get('campaign_id') or r.get('map_id') or r.get('mission_id') or 'Recorded game',
                 'state':r['state'],'created':shown(r.get('created_at')),'detail_url':url_for('run_detail',run_id=r['_id'])}
                for r in self.db.game_runs.find(query,{'kind':1,'state':1,'map_id':1,'mission_id':1,'campaign_id':1,'created_at':1}).sort('created_at',-1).limit(25)]

    def records(self, category):
        if category not in SPECS:abort(404)
        collection,base,search,fields,title=SPECS[category]
        rows,filters,pagination=self.query(collection,base,fields,search,'status' if category=='defenses' else 'state')
        for r in rows:
            r['detail_url']=url_for('admin_record_detail',category=category,record_id=r['_id'])
            r['name']=r.get('name') or r.get('campaign_id') or r.get('mission_id') or r.get('hero_id') or r.get('map_id') or r.get('username') or r['_id']
            r['state']=r.get('state') or r.get('status') or ('Retired' if r.get('retired') else r.get('outcome','—'))
            r['owner']=self.name('accounts',r.get('owner_id') or r.get('account_id'))
            r['teams']=self.names('teams',r.get('team_ids',[])) if 'team_ids' in r else self.name('teams',r.get('owner_team_id') or r.get('team_id'))
            r['created_at']=shown(r.get('created_at'))
            if category=='heroes':
                r['name']=catalog_hero(r['hero_id'])['name']
                r['forms']=', '.join(catalog_form(r['hero_id'],f)[1]['source_type'] for f in r['forms'])
        headings=[('name','Record'),('state','Status'),('teams','Team'),('created_at','Created')]
        if category=='heroes':headings=[('name','Hero'),('owner','Player'),('forms','Earned forms'),('total_experience','Lifetime XP')]
        elif category=='soldiers':headings=[('name','Soldier'),('owner','Player'),('unit_type','Form'),('xp','XP'),('state','Status')]
        elif category=='castles':headings=[('name','Castle'),('kind','Type'),('teams','Owner'),('roadworks','Roadworks')]
        elif category=='defenses':headings=[('name','Owner'),('teams','Team'),('state','Permission'),('bracket','Bracket')]
        elif category=='campaigns':headings=[('name','Campaign'),('state','State'),('next_checkpoint','Next checkpoint'),('created_at','Created')]
        for r in rows:
            for key,_ in headings:r[key]=shown(r.get(key))
        return self.listing(title,'Search current and historical records. Changes are recorded in the audit log.',headings,rows,filters,pagination)

    def record(self, category, identity):
        if category not in SPECS:abort(404)
        if category in ('plans','campaigns'):return redirect(url_for('run_detail',run_id=identity))
        col,base,_,fields,title=SPECS[category]
        extra={'contracts':('settings','armies','generation','approvals','finished_at','cancel_reason'),
               'soldiers':('preferences',),'defenses':('selection',),
               'history':('hero_rewards','soldier_rewards','team_rewards','wounds','replay_sha256','ledger_sha256','event_count'),
               'wars':('approvals','captain_ids'), 'castles':('neighbors','first_occupation_rewarded')}.get(category,())
        record=self.db[col].find_one({**base,'_id':identity},{key:1 for key in ('_id',*fields,*extra)})
        if record is None:abort(404)
        summary=[('Record',identity)]
        labels={'owner_id':'Player','account_id':'Player','owner_team_id':'Owner Team','team_id':'Team','governor_id':'Governor','target_id':'Target Castle','castle_id':'Castle'}
        for key in fields:
            value=record.get(key)
            if isinstance(value,dict) or key in ('participants',):continue
            if key in ('owner_id','account_id','governor_id'):value=self.name('accounts',value)
            elif key in ('owner_team_id','team_id'):value=self.name('teams',value)
            elif key=='team_ids':value=self.names('teams',value or [])
            elif key in ('castle_id','target_id'):value=self.name('world_castles',value)
            summary.append((labels.get(key,key.replace('_',' ').capitalize()),value))
        sections=[];controls=[]
        if category=='contracts':
            armies=[]
            for army in record.get('armies',[]):
                selection=army.get('selection',{})
                armies.append({'player':self.name('accounts',army.get('account_id')),'controller':army.get('controller','—'),
                               'hero':selection.get('hero_id') or '—','soldiers':len(selection.get('soldier_ids',[])),
                               'team':self.name('teams',army.get('team_id'))})
            sections.append(section('Frozen forces',[('player','Player'),('team','Team'),('controller','Controller'),('hero','Hero'),('soldiers','Soldiers')],armies))
            sections.append(self.settings(record.get('settings',{})))
            if record['state'] not in TERMINAL:
                from .admin_management import admin_record_revision
                controls.append(action('Cancel engagement','admin_cancel_record',{'kind':'world','record_id':identity},admin_record_revision(record),
                    'Releases only this engagement. No victory, reward or Castle transfer is awarded.'))
            receipt=self.db.world_settlements.find_one({'_id':identity},{'_id':1})
            if receipt:sections.append(section('Result',[('name','Settlement')],[{'name':'View verified settlement','detail_url':url_for('admin_record_detail',category='history',record_id=identity)}]))
        if category=='castles':
            sections.append(section('Routes',[('name','Adjacent Castle')],[{'name':self.name('world_castles',i),'detail_url':url_for('admin_record_detail',category='castles',record_id=i)} for i in record.get('neighbors',[])]))
            defenses=list(self.db.world_defenses.find({'castle_id':identity},{'username':1,'status':1,'approved':1}).limit(64))
            for d in defenses:d['detail_url']=url_for('admin_record_detail',category='defenses',record_id=d['_id'])
            sections.append(section('Defense permissions',[('username','Owner'),('status','Status'),('approved','Captain approved')],defenses))
        if category=='defenses' and record.get('status') not in ('withdrawn','withdraw_pending'):
            controls.append(action('Withdraw defense authorization','admin_defense_withdraw',{'record_id':identity},record['revision'],
                'Unlocked forces are released now. A committed defense keeps its frozen control until that engagement settles or is cancelled.'))
        if category=='history':
            reward_fields={
                'hero_rewards':('account_id','hero_id','experience'),
                'soldier_rewards':('soldier_id','earned_xp','before_type','after_type','final_xp','dead','deployed'),
                'team_rewards':('team_id','experience'),
                'wounds':('owner_id','asset_kind','asset_id','kind','recover_at_round'),
            }
            for key in ('hero_rewards','soldier_rewards','team_rewards','wounds'):
                rows=[]
                for item in record.get(key,[]):
                    rows.append({k:shown(item.get(k)) for k in reward_fields[key]})
                if rows:sections.append(section(key.replace('_',' ').title(),[(k,k.replace('_',' ').title()) for k in rows[0]],rows))
            summary.extend([('Replay digest',record.get('replay_sha256')),('Recorded commands',record.get('event_count'))])
        return self.detail(record.get('name') or title.rstrip('s'),title,url_for('admin_records',category=category),summary,sections,controls)

    def settings(self, settings):
        labels={'gold':'Starting gold','base_income':'Effective income','turns':'Turn limit','fog':'Fog','shroud':'Shroud','observers':'Observers'}
        return section('Battle rules',[('name','Rule'),('value','Value')],[{'name':label,'value':'Unlimited' if key=='turns' and settings.get(key)==-1 else shown(settings.get(key))} for key,label in labels.items()])

    def companies(self):
        rows,filters,pagination=self.query('accounts',{'role':'player'},('username','status'),('username','_id'),'status')
        for r in rows:
            company=self.db.companies.find_one({'_id':r['_id']},{'warband':1})
            r.update(detail_url=url_for('admin_company_detail',account_id=r['_id']),
                     heroes=self.db.account_heroes.count_documents({'account_id':r['_id']}),
                     soldiers=self.db.company_soldiers.count_documents({'owner_id':r['_id'],'retired':False}),
                     company='Enlisted' if company else 'Not enlisted')
        return self.listing('Companies & heroes','Personal armies, earned progression, wounds and commitments.',
            [('username','Player'),('company','Company'),('heroes','Heroes'),('soldiers','Soldiers'),('status','Account')],rows,filters,pagination)

    def company(self, identity):
        account=self.db.accounts.find_one({'_id':identity,'role':'player'},{'username':1,'status':1})
        if account is None:abort(404)
        company=self.db.companies.find_one({'_id':identity},{'revision':1,'warband':1,'location':1})
        soldiers=list(self.db.company_soldiers.find({'owner_id':identity,'retired':False},{'name':1,'unit_type':1,'xp':1,'total_earned':1}).sort('_id',1).limit(12))
        for s in soldiers:s.update(detail_url=url_for('admin_record_detail',category='soldiers',record_id=s['_id']))
        heroes=owned_heroes(self.db,identity)
        for hero in heroes:hero['forms']=', '.join(catalog_form(hero['hero_id'],form)[1]['source_type'] for form in hero['forms'])
        wounds=list(self.db.company_wounds.find({'owner_id':identity},{'asset_kind':1,'asset_id':1,'kind':1,'recover_at_round':1}).limit(129))
        locks=list(self.db.company_asset_locks.find({'owner_id':identity},{'run_id':1,'assignment_id':1}).limit(129))
        sections=[section('Earned heroes',[('name','Hero'),('hero_level','Level'),('experience','XP'),('total_experience','Total XP'),('forms','Earned forms')],heroes),
                  section('Permanent soldiers',[('name','Soldier'),('unit_type','Form'),('xp','XP'),('total_earned','Lifetime XP')],soldiers),
                  section('Wounds',[('asset_kind','Unit'),('asset_id','Record'),('kind','Recovery'),('recover_at_round','Recovery round')],wounds),
                  section('Commitments',[('run_id','Battle'),('assignment_id','Standing defense')],locks)]
        controls=[]
        if company:
            selection=company.get('warband',{})
            hero_name=catalog_hero(selection['hero_id'])['name'] if selection.get('hero_id') else '—'
            form_name=catalog_form(selection['hero_id'],selection['form_id'])[1]['source_type'] if selection.get('form_id') else '—'
            sections.append(section('Selected expedition',[('hero','Hero'),('form','Form'),('bracket','Bracket'),('soldiers','Soldiers')],
                [{'hero':hero_name,'form':form_name,'bracket':selection.get('bracket','—'),'soldiers':len(selection.get('soldier_ids',[]))}]))
            controls.append(action('Rest company','admin_company_rest',{'account_id':identity},company['revision'],
                'Clears eligible ordinary wounds only. Committed units remain locked and territorial wounds recover at the next eligible world round.',danger=False))
        return self.detail(account['username'],'Company management',url_for('admin_companies'),
            [('Company','Enlisted' if company else 'Not enlisted'),('Heroes',len(heroes)),('Soldiers',f'{len(soldiers)}/12'),
             ('Location',self.name('world_castles',company.get('location')) if company else None)],sections,controls)

    def runs(self):
        rows,filters,pagination=self.query('game_runs',{},('kind','state','map_id','campaign_id','mission_id','created_at'),('_id','map_id','campaign_id','mission_id'))
        for r in rows:r.update(title=r.get('campaign_id') or r.get('mission_id') or r.get('map_id') or 'Recorded game',created=shown(r.get('created_at')),detail_url=url_for('run_detail',run_id=r['_id']))
        return self.listing('All game runs','Story campaigns and Team plans; Company and territorial engagements have their own list.',
            [('title','Game'),('kind','Type'),('state','Status'),('created','Created')],rows,filters,pagination)

    def run(self, identity):
        from .admin_management import admin_record_revision
        fields=('kind','state','revision','map_id','mission_id','campaign_id','next_checkpoint','next_scenario_id','created_at','finished_at',
                'team_ids','participants','sides','slots','ready','approvals','settings','shared_room','cancel_reason','result')
        r=self.db.game_runs.find_one({'_id':identity},{k:1 for k in fields})
        if r is None:abort(404)
        players=[{'name':self.name('accounts',p['account_id']),'side':p.get('side','—'),
                  'hero':(p.get('selection') or {}).get('name') or (p.get('selection') or {}).get('hero_id','—'),
                  'ready':p['account_id'] in r.get('ready',[]),'detail_url':url_for('account_detail',account_id=p['account_id'])} for p in r.get('participants',[])]
        sections=[section('Participants',[('name','Player'),('side','Side'),('hero','Hero'),('ready','Ready')],players)]
        if r.get('slots'):
            occupants={p['side']:p for p in r.get('participants',[]) if 'side' in p}
            slot_names={'open':'Open member','reserved':'Reserved member','ai':'Computer','closed':'Closed'}
            slot_rows=[]
            for slot in sorted(r['slots'],key=lambda s:s['side']):
                occupant=occupants.get(slot['side']);selection=(occupant.get('selection') or {}) if occupant else {}
                human=slot['kind'] in ('open','reserved')
                leader=(selection.get('unit_type') or selection.get('name') or selection.get('hero_id') or 'Not selected') if human else '—'
                if slot['kind']=='ai':leader=slot['ai_faction']+' · '+slot['ai_leader']
                slot_rows.append({'side':slot['side'],'team':self.name('teams',slot['team_id']),
                    'kind':slot_names.get(slot['kind'],slot['kind']),
                    'reserved':self.name('accounts',slot['account_id']) if slot['kind']=='reserved' else '—',
                    'player':self.name('accounts',occupant['account_id']) if human and occupant else
                             ('Unclaimed' if human else 'Native AI' if slot['kind']=='ai' else 'No units'),
                    'leader':leader,'ready':('Ready' if occupant and occupant['account_id'] in r.get('ready',[]) else 'Not ready') if human else 'Not required'})
            sections.append(section('Plan slots',[('side','Side'),('team','Team'),('kind','Slot'),('reserved','Reserved for'),
                ('player','Occupant'),('leader','Hero / AI leader'),('ready','Readiness')],slot_rows,
                'Saved configuration and readiness; this battle is inactive.' if r['state'] in TERMINAL else 'Current side configuration and human readiness.'))
            approval_rows=[]
            frozen_captains=(r.get('shared_room') or {}).get('captains',{})
            for team_id in r.get('team_ids',[]):
                approved_by=r.get('approvals',{}).get(team_id)
                current=self.db.teams.find_one({'_id':team_id},{'captain_id':1}) or {}
                captain=((frozen_captains.get(team_id) or approved_by) if r['state'] in TERMINAL else
                    (frozen_captains.get(team_id) if r['state']=='running' else current.get('captain_id')))
                status=(('Approved (history)' if approved_by else 'Not approved (history)') if r['state'] in TERMINAL else
                    ('Approved' if captain and approved_by==captain else 'Captain changed; approval required' if approved_by else 'Awaiting approval'))
                approval_rows.append({'team':self.name('teams',team_id),'captain':self.name('accounts',captain),'status':status})
            sections.append(section('Captain approvals',[('team','Team'),('captain','Captain'),('status','Approval')],approval_rows,
                'Historical consent does not authorize another battle.' if r['state'] in TERMINAL else 'Both captains must approve the current configuration.'))
        if r.get('settings'):sections.append(self.settings(r['settings']))
        receipt=self.db.settlements.find_one({'_id':identity},{'result':1,'created_at':1})
        if receipt:
            sections.append(section('Settlement',[('result','Result'),('created','Recorded')],[{'result':shown(receipt.get('result',{}).get('outcome') or receipt.get('result',{}).get('winner_team_id') or ('Draw' if receipt.get('result',{}).get('draw') else 'Completed')),'created':shown(receipt.get('created_at'))}]))
        checkpoints=list(self.db.story_checkpoints.find({'run_id':identity},{'sequence':1,'result.outcome':1,'result.scenario_id':1,'created_at':1}).sort('sequence',-1).limit(25))
        if checkpoints:sections.append(section('Recent scenario checkpoints',[('sequence','Sequence'),('outcome','Outcome'),('created','Recorded')],[{'sequence':x['sequence'],'outcome':x.get('result',{}).get('outcome'),'created':shown(x.get('created_at'))} for x in checkpoints]))
        controls=[]
        if r['state'] not in TERMINAL:controls.append(action('Cancel run without rewards','admin_cancel_record',{'kind':'run','record_id':identity},admin_record_revision(r),
            'Cancels this run and releases its reservations. Saved campaign files and completed rewards are retained.'))
        room=r.get('shared_room')
        if room:
            review=self.domain._shared_review(r)
            sections.append(section('Result evidence',[('state','Review'),('reports','Player reports'),('captains','Captain approvals')],
                [{'state':review['review_state'],'reports':f"{review['reports_received']} / {review['required_reports']}",'captains':review['captains_approved']}]))
            reports=[]
            for player,report in room.get('result_reports',{}).items():
                reports.append({'player':self.name('accounts',player),'winner':self.name('teams',report.get('winner_team_id')),'draw':shown(report.get('draw')),'replay':shown(report.get('replay_sha256'))})
            sections.append(section('Human result reports',[('player','Player'),('winner','Winner'),('draw','Draw'),('replay','Replay digest')],reports))
            if r['state']=='running' and review['reports_received']==review['required_reports']:
                controls.append({'title':'Resolve reviewed result','description':'Ordinary Team battles only. Complete human reports are required; awards remain exactly once.',
                    'url':url_for('resolve_shared_result',run_id=identity),'fields':[field('revision',value=review['revision']),
                    field('result','Result',kind='select',required=True,options=[{'value':'','label':'Choose result'},*({'value':i,'label':self.name('teams',i)} for i in r.get('team_ids',[])),{'value':'draw','label':'Draw'}]),
                    field('reason','Evidence and reason',kind='textarea',required=True,minlength=3,maxlength=500)],'button':'Resolve and award fixed rewards','danger':True})
        return self.detail(r.get('campaign_id') or r.get('map_id') or r.get('mission_id') or 'Game run',r['kind'].capitalize(),url_for('runs'),
            [('Record',identity),('State',r['state']),('Teams',self.names('teams',r.get('team_ids',[]))),('Created',r.get('created_at')),('Cancelled because',r.get('cancel_reason'))],sections,controls)

    def audit(self):
        rows,filters,pagination=self.query('admin_audit',{},('actor_id','action','target_id','reason','created_at'),('action','reason','target_id'))
        for r in rows:r.update(actor=self.name('accounts',r.get('actor_id')),created=shown(r.get('created_at')))
        return self.listing('Audit log','Reasons and responsible administrators for recorded management changes.',
            [('created','Time'),('actor','Administrator'),('action','Action'),('target_id','Target'),('reason','Reason')],rows,filters,pagination)

    def operations(self):
        reservations=list(self.db.network_battle_reservations.find({}, {'account_id':1,'run_id':1,'kind':1,'expires_at':1}).sort('_id',1).limit(100))
        for r in reservations:r.update(player=self.name('accounts',r.get('account_id') or r['_id']),expires=shown(r.get('expires_at')))
        queued=list(self.db.world_contracts.find({'state':{'$nin':list(TERMINAL)}},{'kind':1,'state':1,'created_at':1}).sort('created_at',1).limit(100))
        for r in queued:r.update(detail_url=url_for('admin_record_detail',category='contracts',record_id=r['_id']),created=shown(r.get('created_at')))
        schema=self.db.schema_metadata.find_one({'_id':'alliance'},{'version':1}) or {}
        return self.detail('Operations','Recorded queue and reservations; browser views do not run native workers.',url_for('dashboard'),
            [('Schema',schema.get('version')),('Queue records shown',len(queued)),('Reservations shown',len(reservations))],
            [section('Engagement queue',[('kind','Activity'),('state','State'),('created','Queued')],queued),
             section('Player reservations',[('player','Player'),('kind','Activity'),('run_id','Battle'),('expires','Lease expiry')],reservations,
                'Cancel an abandoned battle from its detail page. Reservations are released through that battle’s rules.')])


def register_admin_console(app, db, domain, admin_required):
    console=AdminConsole(db,domain)

    @app.context_processor
    def navigation():
        entries=[('dashboard','Overview'),('accounts','Users'),('admin_rooms','Rooms'),('teams','Teams'),
                 ('admin_plans','Team battles'),('admin_companies','Companies'),('admin_campaigns','Campaigns'),
                 ('world_admin','World'),('admin_contracts','Engagements'),('runs','Game runs'),('admin_operations','Operations'),('areas','Areas'),('audit','Audit log')]
        icons={'dashboard':'grid','accounts':'users','admin_rooms':'swords','teams':'flag','admin_plans':'swords',
               'admin_companies':'hero','admin_campaigns':'book','world_admin':'castle','admin_contracts':'swords',
               'runs':'history','admin_operations':'settings','areas':'map','audit':'history'}
        selected=request.endpoint
        if request.path.startswith('/accounts'):selected='accounts'
        elif request.path.startswith('/teams'):selected='teams'
        elif request.path.startswith('/companies'):selected='admin_companies'
        elif request.path.startswith('/rooms'):selected='admin_rooms'
        elif request.path.startswith('/runs'):selected='runs'
        elif request.path.startswith('/areas'):selected='areas'
        elif request.endpoint in ('admin_records','admin_record_detail'):
            category=(request.view_args or {}).get('category')
            selected={'plans':'admin_plans','campaigns':'admin_campaigns','contracts':'admin_contracts','heroes':'admin_companies','soldiers':'admin_companies'}.get(category,'world_admin')
        return {'admin_nav':[{'label':label,'url':url_for(endpoint),'active':selected==endpoint,'icon':icons[endpoint]} for endpoint,label in entries]}

    def register(path, endpoint, view, methods=('GET',)):
        app.add_url_rule(path,endpoint,admin_required(view),methods=list(methods))

    register('/teams/<team_id>','admin_team_detail',lambda team_id:console.team(team_id))
    register('/companies','admin_companies',console.companies)
    register('/companies/<account_id>','admin_company_detail',lambda account_id:console.company(account_id))
    register('/plans','admin_plans',lambda:console.records('plans'))
    register('/campaigns','admin_campaigns',lambda:console.records('campaigns'))
    register('/engagements','admin_contracts',lambda:console.records('contracts'))
    register('/manage/<category>','admin_records',console.records)
    register('/manage/<category>/<record_id>','admin_record_detail',lambda category,record_id:console.record(category,record_id))
    register('/operations','admin_operations',console.operations)

    from .admin_rooms import AdminRooms
    rooms=AdminRooms(domain)

    def rooms_list():
        if set(request.args)-{'q','state','page'} or any(len(request.args.getlist(k))!=1 for k in request.args):abort(400)
        q=request.args.get('q','').strip();state=request.args.get('state','');page=request.args.get('page','1')
        if len(q)>80 or state not in ('','waiting','full','ready','playing','closed') or not re.fullmatch('[1-9][0-9]{0,2}',page):abort(400)
        snapshot=rooms.snapshot()
        source=snapshot['closed'] if state=='closed' else snapshot['rooms']
        selected=[dict(r) for r in source if (not state or r['status']==state) and (not q or q.casefold() in (r['name']+' '+r['map_name']).casefold())]
        number=int(page);start=(number-1)*PAGE_SIZE;display=selected[start:start+PAGE_SIZE]
        for r in display:r.update(detail_url=url_for('admin_room_detail',room_id=r['id']),seats=f"{r['members']}/{r['capacity']}",
            readiness=f"{r['ready']}/{r['capacity']}",state=r['status'] if snapshot['available'] or state=='closed' else 'Unconfirmed (lobby unavailable)',
            close_status=r.get('close_status') or '—')
        filters=[{'name':'q','label':'Room or map','value':q},{'name':'state','label':'Status','value':state,'options':[{'value':s,'label':s.title() if s else 'Open rooms'} for s in ('','waiting','full','ready','playing','closed')]}]
        pagination={'previous_url':url_for('admin_rooms',q=q,state=state,page=number-1) if number>1 else None,
            'next_url':url_for('admin_rooms',q=q,state=state,page=number+1) if len(selected)>start+PAGE_SIZE else None,'label':f'Page {number}'}
        note=('Native lobby connected. Last report: '+shown(snapshot['updated_at']) if snapshot['available'] else
              'Native lobby inventory unavailable or expired. Start the updated Room server; retained statuses are not live.')
        return console.listing('Individual Rooms',note,[('name','Room'),('map_name','Map'),('seats','Players'),('readiness','Ready'),('state','Status'),('close_status','Closure')],display,filters,pagination)

    def room_detail(room_id):
        r=rooms.detail(room_id)
        controls=[]
        if r['available'] and r.get('close_status')!='pending':
            controls.append(action('Close Room','admin_room_close',{'room_id':room_id},r['revision'],
                'Disconnects this Room through the native server. Players return to the lobby; no permanent rewards are awarded. Changes to the Room require a fresh review.',
                extra=[field('generation',value=r['generation'])]))
        seats=[{'side':s['side'],'player':s['username'] or 'Open seat','hero':s['unit_type'] or '—','ready':shown(s['ready'])} for s in r['seats']]
        return console.detail(r['name'],'Individual Room',url_for('admin_rooms'),
            [('Status',r['status'] if r['available'] or r['status']=='closed' else 'Unconfirmed; native lobby unavailable'),('Map',r['map_name']),
             ('Players',f"{r['members']}/{r['capacity']}"),('Ready',f"{r['ready']}/{r['capacity']}"),('Closure request',r.get('close_status')),('Updated',r['updated_at'])],
            [console.settings(r),section('Human seats',[('side','Side'),('player','Player'),('hero','Hero'),('ready','Ready')],seats)],controls)

    register('/rooms','admin_rooms',rooms_list)
    register('/rooms/<room_id>','admin_room_detail',room_detail)

    def form(keys, *, binding=False):
        expected={'csrf_token','revision','reason','confirmation',*keys}
        if request.args or request.files or set(request.form)!=expected or any(len(request.form.getlist(k))!=1 for k in expected):abort(400)
        if request.form['confirmation']!='confirmed':abort(400)
        revision=request.form['revision']
        if binding:
            if not re.fullmatch('[0-9a-f]{64}',revision):abort(400)
        else:
            if not re.fullmatch('0|[1-9][0-9]{0,18}',revision) or int(revision)>9223372036854775807:abort(400)
            revision=int(revision)
        if not 3<=len(request.form['reason'].strip())<=500:abort(400)
        if any(len(request.form[k])>128 for k in keys):abort(400)
        return revision

    def team_action(team_id):
        revision=form(('operation','value'))
        domain.admin_manage_team(g.admin['_id'],team_id,request.form['operation'],request.form['value'],request.form['reason'],revision)
        flash('Team updated. The change and reason were recorded.')
        return redirect(url_for('admin_team_detail',team_id=team_id))
    register('/teams/<team_id>/manage','admin_team_action',team_action,('POST',))

    def room_close(room_id):
        revision=form(('generation',))
        rooms.request_close(g.admin['_id'],room_id,revision,request.form['generation'],request.form['reason'])
        flash('Closure requested. Refresh after the native lobby acknowledges it; pending does not mean closed.')
        return redirect(url_for('admin_room_detail',room_id=room_id))
    register('/rooms/<room_id>/close','admin_room_close',room_close,('POST',))

    def create_player():
        values={'username':'','reason':''};error=None
        if request.method=='POST':
            expected={'csrf_token','username','password','password_confirmation','reason'}
            if request.args or request.files or set(request.form)!=expected or any(len(request.form.getlist(k))!=1 for k in expected):abort(400)
            if len(request.form['username'])>64 or len(request.form['reason'])>500:abort(400)
            values={k:request.form[k] for k in ('username','reason')}
            try:
                account=domain.admin_create_player(g.admin['_id'],values['username'],request.form['password'],request.form['password_confirmation'],values['reason'])
            except DomainError as exc:
                return render_template('account_create.html',values=values,error=exc.message),409
            flash('Player created with an empty hero collection. Campaign progress must be earned in the game.')
            return redirect(url_for('account_detail',account_id=account['_id']))
        return render_template('account_create.html',values=values,error=error)
    register('/accounts/new','admin_create_player',create_player,('GET','POST'))

    def cancel_record(kind,record_id):
        revision=form((),binding=True)
        if kind not in ('run','plan','world'):abort(404)
        domain.admin_cancel_record(g.admin['_id'],kind,record_id,request.form['reason'],revision)
        flash('Battle cancelled through its game rules. No rewards were awarded.')
        return redirect(url_for('admin_record_detail',category='contracts',record_id=record_id) if kind=='world' else url_for('run_detail',run_id=record_id))
    register('/manage-cancel/<kind>/<record_id>','admin_cancel_record',cancel_record,('POST',))

    def rest_company(account_id):
        revision=form(())
        domain.admin_rest_company(g.admin['_id'],account_id,request.form['reason'],revision)
        flash('Ordinary recovery applied. Territorial recovery rules remain in effect.')
        return redirect(url_for('admin_company_detail',account_id=account_id))
    register('/companies/<account_id>/rest','admin_company_rest',rest_company,('POST',))

    def defense_withdraw(record_id):
        revision=form(())
        domain.admin_withdraw_defense(g.admin['_id'],record_id,request.form['reason'],revision)
        flash('Defense withdrawal recorded. A committed engagement retains its frozen control until release.')
        return redirect(url_for('admin_record_detail',category='defenses',record_id=record_id))
    register('/manage/defenses/<record_id>/withdraw','admin_defense_withdraw',defense_withdraw,('POST',))

    def revoke_sessions(account_id):
        revision=form(())
        domain.admin_revoke_sessions(g.admin['_id'],account_id,request.form['reason'],revision)
        if account_id==g.admin['_id']:
            session.clear();flash('Your sessions ended. Sign in again.');return redirect(url_for('login'))
        flash('Account sessions revoked. The player must sign in again.')
        return redirect(url_for('account_detail',account_id=account_id))
    register('/accounts/<account_id>/sessions','admin_revoke_sessions',revoke_sessions,('POST',))

    # Live native Room routes are registered below; their publisher uses the
    # existing authenticated native-service interface, not browser credentials.
    return console
