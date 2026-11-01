"""Local, reviewed administration for the fresh Court product.

The console projects selected fields and dispatches ordinary domain commands.
It never edits balances directly or renders credentials, tickets or native logs.
"""
from uuid import uuid4
import re

from flask import abort, flash, g, redirect, render_template, request, url_for

from ..admin_console import columns, field, section, shown
from .base import identifier

PAGE_SIZE = 25
ADJUSTABLE_LIMITS = {
    'attacks_per_day': 'Attacks per player / UTC day',
    'extra_attacks_per_day': 'Purchased extra attacks / UTC day',
    'plans_per_day': 'Initiated approved plans per Team / UTC day',
    'extra_plans_per_day': 'Purchased extra plans / UTC day',
    'member_allowance': 'Member Team spending allowance',
    'battle_cash_per_day': 'Battle Crowns per player / UTC day',
    'castle_income': 'Crowns per held Castle / UTC day',
    'team_income_per_day': 'Castle Crowns per Team / UTC day',
    'campaign_cash': 'First scenario victory Crowns',
    'area_expansion_teams': 'Teams before another Area opens',
    'normal_castles_per_team': 'Active Normal Castles per Team',
    'minimum_normal_castles': 'Minimum active Normal Castles',
}
ZERO_LIMITS = frozenset(ADJUSTABLE_LIMITS) - {'area_expansion_teams',
    'normal_castles_per_team', 'minimum_normal_castles'}
PRICE_LABELS = {
    'create_team': 'Create Team · personal', 'join_team': 'Join Team · personal',
    'create_room': 'Create Room · personal', 'join_room': 'Join Room · personal',
    'hero': 'Hero · personal', 'item': 'Consumable · personal',
    'attack_neutral': 'Neutral Castle attack · Team',
    'attack_owned': 'Owned Castle attack · Team', 'plan': 'Accepted plan per side · Team',
    'relocate': 'Team relocation · Team', 'extra_attack': 'Extra attack trial · Team',
    'extra_plan': 'Extra plan trial · Team',
}
MAPS = (('weldyn-channel', 'Weldyn Channel · 1v1', 1),
        ('isars-cross', "Isar's Cross · 2v2", 2), ('hexcake', 'Hexcake · 3v3', 3),
        ('mokena-prairie', 'Mokena Prairie · 4v4', 4))


def _fields(required, integer_fields=()):
    permitted = {'csrf_token', *required}
    if request.args or request.files or set(request.form) != permitted or any(len(request.form.getlist(k)) != 1 for k in request.form):
        abort(400)
    result = {key: request.form[key] for key in required}
    for key in integer_fields:
        if not re.fullmatch(r'0|[1-9][0-9]{0,14}', result[key]):
            abort(400)
        result[key] = int(result[key])
    return result


def _review_fields(command_values, *, extra=()):
    return [field('command_id', value=str(uuid4())),
        *[field(key, value=value) for key, value in command_values.items()], *extra,
        field('reason', 'Reason', kind='textarea', required=True, minlength=3, maxlength=500),
        field('confirmation', 'I have reviewed this change.', 'confirmed', 'checkbox', required=True)]


def _control(title, endpoint, args, values, description='', *, extra=(), danger=False):
    return {'title': title, 'url': url_for(endpoint, **args), 'description': description,
        'fields': _review_fields(values, extra=extra), 'button': title, 'danger': danger}


class CourtAdmin:
    def __init__(self, db, domain):
        self.db, self.domain = db, domain

    def name(self, collection, identity):
        if not identity: return '—'
        column = 'username' if collection == 'accounts' else 'name'
        row = self.db[collection].find_one({'_id': identity}, {column: 1})
        return row.get(column, 'Unavailable record') if row else 'Unavailable record'

    def dispatch(self, operation, payload):
        result = self.domain.court_admin_command(g.admin['_id'],
            {'version': 1, 'operation': operation, 'payload': payload})
        flash('Change saved and recorded in the audit log.')
        return result

    def rows(self, collection, projection, *, base=None, search=(), states=(), state_field='state'):
        if set(request.args) - {'q', 'state', 'page'} or any(len(request.args.getlist(k)) != 1 for k in request.args):
            abort(400)
        q, state, page = request.args.get('q', '').strip(), request.args.get('state', ''), request.args.get('page', '1')
        if len(q) > 80 or not re.fullmatch(r'[1-9][0-9]{0,3}', page) or state not in ('', *states):
            abort(400)
        query = dict(base or {})
        if q:
            if not search: abort(400)
            query['$or'] = [{key: {'$regex': re.escape(q), '$options': 'i'}} for key in search]
        if state: query[state_field] = state
        page = int(page)
        ordering = [('created_at', -1), ('_id', -1)] if 'created_at' in projection else [('_id', 1)]
        result = list(self.db[collection].find(query, {key: 1 for key in ('_id', *projection)})
            .sort(ordering).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1))
        args = dict(request.view_args or {}, q=q, state=state)
        pages = {'label': f'Page {page}',
            'previous_url': url_for(request.endpoint, **args, page=page - 1) if page > 1 else None,
            'next_url': url_for(request.endpoint, **args, page=page + 1) if len(result) > PAGE_SIZE else None}
        filters = ([{'name': 'q', 'label': 'Search', 'value': q}] if search else [])
        if states:
            filters.append({'name': 'state', 'label': 'Status', 'value': state,
                'options': [{'value': '', 'label': 'All statuses'}] +
                           [{'value': value, 'label': value.replace('_', ' ').title()} for value in states]})
        return result[:PAGE_SIZE], filters, pages

    def listing(self, title, subtitle, headings, rows, filters=(), pagination=None, actions=()):
        return render_template('court_list.html', page={'title': title, 'subtitle': subtitle,
            'columns': columns(*headings), 'rows': rows, 'filters': filters, 'pagination': pagination,
            'primary_actions': list(actions), 'empty_message': 'No matching records.'})

    def detail(self, title, back, summary, sections=(), controls=(), subtitle=''):
        return render_template('court_detail.html', page={'title': title, 'subtitle': subtitle,
            'back_url': back, 'summary': [{'label': label, 'value': shown(value)} for label, value in summary],
            'sections': sections, 'actions': controls})

    def dashboard(self):
        definitions = (
            ('Players', 'accounts', {'role': 'player'}, 'accounts'),
            ('Active Teams', 'court_teams', {'status': 'active'}, 'court_admin_teams'),
            ('Pending Crown requests', 'court_cash_requests', {'state': 'pending'}, 'court_admin_cash'),
            ('Active Areas', 'court_areas', {'enabled': True}, 'court_admin_areas'),
            ('Active battles', 'court_matches', {'state': {'$nin': ['completed', 'cancelled']}}, 'court_admin_battles'),
            ('Open competitions', 'court_competitions', {'state': {'$nin': ['completed', 'cancelled']}}, 'court_admin_competitions'))
        metrics = [{'label': title, 'value': self.db[collection].count_documents(query),
            'url': url_for(endpoint)} for title, collection, query, endpoint in definitions]
        return render_template('court_dashboard.html', metrics=metrics)

    def cash(self):
        rows, filters, pages = self.rows('court_cash_requests',
            ('account_id', 'kind', 'owner_id', 'package', 'state', 'created_at'),
            search=('_id',), states=('pending', 'approved', 'rejected'))
        for row in rows:
            row.update(player=self.name('accounts', row['account_id']),
                owner=self.name('accounts' if row['kind'] == 'personal' else 'court_teams', row['owner_id']),
                created=shown(row['created_at']), detail_url=url_for('court_admin_cash_detail', identity=row['_id']))
        return self.listing('Crown requests', 'Virtual test currency. No payment or cash-out is processed.',
            [('player', 'Requester'), ('owner', 'Wallet owner'), ('kind', 'Wallet'), ('package', 'Crowns'),
             ('state', 'Status'), ('created', 'Requested')], rows, filters, pages)

    def cash_detail(self, identity):
        identifier(identity)
        row = self.db.court_cash_requests.find_one({'_id': identity}, {k: 1 for k in
            ('account_id', 'kind', 'owner_id', 'package', 'state', 'revision', 'created_at', 'reason', 'reviewed_at')})
        if row is None: abort(404)
        wallet = self.domain._wallet_public(row['kind'], row['owner_id'])
        controls = []
        if row['state'] == 'pending':
            for decision in ('approve', 'reject'):
                controls.append(_control(decision.title() + ' request', 'court_admin_cash_review',
                    {'identity': identity, 'decision': decision}, {'revision': row['revision']},
                    f"{row['package']} virtual Crowns to the {row['kind']} wallet.", danger=decision == 'reject'))
        return self.detail('Crown request', url_for('court_admin_cash'),
            [('Requester', self.name('accounts', row['account_id'])),
             ('Wallet owner', self.name('accounts' if row['kind'] == 'personal' else 'court_teams', row['owner_id'])),
             ('Package', str(row['package']) + ' Crowns'), ('Status', row['state']),
             ('Available', wallet['available']), ('Held', wallet['held']),
             ('Requested', row['created_at']), ('Reviewed', row.get('reviewed_at')), ('Reason', row.get('reason'))],
            controls=controls, subtitle='Approval credits the fixed package once. Rejection credits nothing.')

    def areas(self):
        rows, filters, pages = self.rows('court_areas', ('name', 'realm_name', 'mode', 'enabled', 'team_count'),
            search=('name', 'realm_name', '_id'), states=('auto', 'on', 'off'), state_field='mode')
        for row in rows:
            row.update(status='Active' if row['enabled'] else 'Inactive',
                detail_url=url_for('court_admin_area', identity=row['_id']))
        return self.listing('World Areas', '128 Areas; automatic population control with reviewed host overrides.',
            [('name', 'Area'), ('realm_name', 'Realm'), ('team_count', 'Teams'), ('mode', 'Control'), ('status', 'Status')],
            rows, filters, pages)

    def area(self, identity):
        identifier(identity, 'area')
        row = self.db.court_areas.find_one({'_id': identity}, {k: 1 for k in
            ('name', 'realm_name', 'mode', 'enabled', 'team_count', 'revision')})
        if row is None: abort(404)
        castles, filters, pages = self.rows('court_castles',
            ('name', 'role', 'mode', 'enabled', 'owner_team_id', 'reservation_id', 'event_id', 'protected_until'),
            base={'area_id': identity}, search=('name', '_id'), states=('normal', 'plan', 'competition'), state_field='role')
        for castle in castles:
            castle.update(owner=self.name('court_teams', castle.get('owner_team_id')),
                status=self.domain._castle_public({**castle, 'area_id': identity, 'revision': 0})['state'],
                detail_url=url_for('court_admin_castle', identity=castle['_id']))
        controls = [self.activation('area', row)]
        return render_template('court_area.html', area=row, castles=castles,
            headings=columns(('name', 'Castle'), ('role', 'Type'), ('owner', 'Owner'), ('status', 'Status'), ('mode', 'Control')),
            filters=filters, pagination=pages, control=controls[0])

    def activation(self, kind, row):
        return _control('Change activation', 'court_admin_activation', {'kind': kind, 'identity': row['_id']},
            {'revision': row['revision']}, 'Owned, occupied and committed locations cannot be forcibly closed.',
            extra=[field('mode', 'Activation policy', row['mode'], 'select', required=True,
                options=[{'value': k, 'label': label} for k, label in
                    [('auto', 'Automatic by Team population'), ('on', 'Host enabled'), ('off', 'Host disabled')]])])

    def castle(self, identity):
        identifier(identity, 'castle')
        row = self.db.court_castles.find_one({'_id': identity}, {k: 1 for k in
            ('name', 'area_id', 'role', 'mode', 'enabled', 'owner_team_id', 'reservation_id', 'event_id', 'protected_until', 'revision')})
        if row is None: abort(404)
        value = self.domain._castle_public(row)
        actions = [self.activation('castle', row)]
        sections = []
        if row['role'] == 'competition':
            sections.append({'title': 'Competition', 'columns': columns(('name', 'Action')), 'rows': [{
                'name': 'Organize competition', 'detail_url': url_for('court_admin_competition_new', castle=identity)}]})
        return self.detail(row['name'], url_for('court_admin_area', identity=row['area_id']),
            [('Area', self.name('court_areas', row['area_id'])), ('Type', row['role']), ('Status', value['state']),
             ('Owner', value['owner_team_name']), ('Protection ends', row.get('protected_until')),
             ('Activation', row['mode'])], sections, actions)

    def teams(self):
        rows, filters, pages = self.rows('court_teams', ('name', 'area_id', 'captain_id', 'members', 'status', 'level'),
            search=('name', '_id'), states=('active', 'archived'), state_field='status')
        for row in rows:
            row.update(area=self.name('court_areas', row['area_id']), captain=self.name('accounts', row['captain_id']),
                size=f"{len(row['members'])}/10", available=self.domain._wallet_public('team', row['_id'])['available'],
                detail_url=url_for('court_admin_team', identity=row['_id']))
        return self.listing('Teams', 'Roster, treasury, contributions and history.',
            [('name', 'Team'), ('area', 'Area'), ('captain', 'Captain'), ('size', 'Members'),
             ('available', 'Available Crowns'), ('status', 'Status')], rows, filters, pages)

    def team(self, identity):
        identifier(identity)
        row = self.db.court_teams.find_one({'_id': identity}, {k: 1 for k in
            ('name', 'area_id', 'captain_id', 'members', 'status', 'level', 'experience')})
        if row is None: abort(404)
        wallet = self.domain._wallet_public('team', identity)
        members = [{'name': self.name('accounts', member['account_id']),
                    'role': 'Captain' if member['account_id'] == row['captain_id'] else 'Member',
                    'joined': shown(member['joined_at']),
                    'detail_url': url_for('account_detail', account_id=member['account_id'])} for member in row['members']]
        ledger, filters, pages = self.rows('court_ledger', ('operation', 'binding', 'created_at'),
            base={'wallet_ids': 'team:' + identity}, states=('credit', 'hold', 'capture', 'release', 'refund', 'contribution'),
            state_field='operation')
        money = [{'operation': entry['operation'], 'amount': entry['binding'].get('amount', 0),
                  'created': shown(entry['created_at'])} for entry in ledger]
        return render_template('court_team.html', team=row, wallet=wallet,
            captain=self.name('accounts', row['captain_id']), area=self.name('court_areas', row['area_id']),
            members=members, ledger=money, filters=filters, pagination=pages)

    def history(self):
        rows, filters, pages = self.rows('court_history', ('team_id', 'kind', 'title', 'created_at'), search=('title', 'kind'))
        for row in rows:
            row.update(team=self.name('court_teams', row['team_id']), created=shown(row['created_at']))
        return self.listing('Territorial history', 'Preserved Team events and ownership changes.',
            [('title', 'Event'), ('team', 'Team'), ('kind', 'Activity'), ('created', 'Recorded')], rows, filters, pages)

    def battles(self):
        rows, filters, pages = self.rows('court_matches', ('kind', 'state', 'castle_id', 'team_ids', 'created_at'),
            search=('_id', 'castle_id'), states=('proposed', 'response', 'scheduled', 'queued', 'preparing', 'running', 'paused', 'disputed', 'completed', 'cancelled'))
        for row in rows:
            row.update(castle=self.name('court_castles', row['castle_id']),
                teams=' / '.join(self.name('court_teams', team) for team in row['team_ids']),
                created=shown(row['created_at']), detail_url=url_for('court_admin_battle', identity=row['_id']))
        return self.listing('Court battles', 'Immutable settings, participation, results and evidence status.',
            [('castle', 'Castle'), ('teams', 'Teams'), ('kind', 'Activity'), ('state', 'Status'), ('created', 'Created')],
            rows, filters, pages)

    def battle(self, identity):
        identifier(identity)
        row = self.db.court_matches.find_one({'_id': identity}, {k: 1 for k in
            ('kind', 'state', 'castle_id', 'team_ids', 'settings', 'seats', 'created_at', 'revision', 'start_at')})
        if row is None: abort(404)
        receipt = self.db.court_battle_receipts.find_one({'match_id': identity}, {k: 1 for k in
            ('winner_team_id', 'draw', 'reason', 'native_verified', 'created_at')})
        seats = [{'side': seat.get('side'), 'name': self.name('accounts', seat.get('account_id')),
            'team': self.name('court_teams', seat.get('team_id')), 'ready': shown(seat.get('ready', False))}
            for seat in row['seats']]
        settings = [{'name': key.replace('_', ' ').title(), 'value': shown(value)}
                    for key, value in row['settings'].items() if key in {'map_id', 'size', 'gold', 'base_income', 'turns', 'fog', 'shroud', 'observers', 'hero_cap', 'items'}]
        summaries = [('Castle', self.name('court_castles', row['castle_id'])), ('Kind', row['kind']),
            ('State', row['state']), ('Start', row.get('start_at')), ('Created', row['created_at'])]
        if receipt:
            summaries += [('Result', 'Draw' if receipt['draw'] else self.name('court_teams', receipt['winner_team_id'])),
                ('Native verified', receipt['native_verified']), ('Result policy', receipt['reason'])]
        controls = []
        if row['state'] not in ('completed', 'cancelled'):
            note = 'Cancels only this battle, releases its reservations and refunds its fees and items. No winner, experience or Castle is awarded.'
            if row['kind'] == 'competition':
                note += ' Its bracket slot receives a fresh match with the same Teams and rules. Participants must join and Ready again; the host explicitly starts the replacement. Other matches and the entry pool remain unchanged.'
            controls.append(_control('Cancel battle for a technical issue', 'court_admin_battle_cancel',
                {'identity': identity}, {'expected_revision': row['revision']}, note, danger=True))
        return self.detail('Battle record', url_for('court_admin_battles'), summaries,
            [section('Combat rules', [('name', 'Rule'), ('value', 'Value')], settings),
             section('Participants', [('side', 'Side'), ('name', 'Player'), ('team', 'Team'), ('ready', 'Ready')], seats)], controls)

    def settings(self):
        value = self.domain._settings()
        return render_template('court_settings.html', settings=value, prices=PRICE_LABELS,
            limits=ADJUSTABLE_LIMITS, zero_limits=ZERO_LIMITS, command_id=str(uuid4()))

    def competitions(self):
        rows, filters, pages = self.rows('court_competitions', ('name', 'castle_id', 'state', 'entry_fee', 'entries', 'round'),
            search=('name', 'castle_id'), states=('registration', 'round_ready', 'playing', 'completed', 'cancelled'))
        for row in rows:
            row.update(castle=self.name('court_castles', row['castle_id']), teams=len(row['entries']),
                detail_url=url_for('court_admin_competition', identity=row['_id']))
        return self.listing('Competitions', 'Single-elimination brackets; the host opens each round.',
            [('name', 'Competition'), ('castle', 'Castle'), ('state', 'Status'), ('teams', 'Teams'),
             ('entry_fee', 'Team entry Crowns'), ('round', 'Round')], rows, filters, pages,
            actions=[{'label': 'Organize competition', 'url': url_for('court_admin_competition_new')}])

    def competition(self, identity):
        identifier(identity)
        row = self.db.court_competitions.find_one({'_id': identity})
        if row is None: abort(404)
        # This domain projection excludes service secrets, tickets and raw native evidence.
        value = self.domain._competition_public(row)
        controls = []
        for state, operation, label, description in (
            ('registration', 'admin_lock_competition', 'Lock registration and draw bracket', 'This freezes entrants, captures their held entry fees and reveals the committed draw seed.'),
            ('round_ready', 'admin_start_round', 'Start next round', 'Eligible participants receive their match and attendance window.')):
            if row['state'] == state:
                controls.append(_control(label, 'court_admin_competition_action', {'identity': identity, 'operation': operation},
                    {'expected_revision': row['revision']}, description))
        if row['state'] == 'playing' and any(r['number'] == value['round'] and
                any(m['state'] == 'scheduled' and not m.get('bye') for m in r['matches']) for r in value['rounds']):
            controls.append(_control('Start replacement matches', 'court_admin_competition_action',
                {'identity': identity, 'operation': 'admin_start_round'}, {'expected_revision': row['revision']},
                'Starts only the scheduled replacements in this round. Other active matches continue unchanged.'))
        if row['state'] not in ('completed', 'cancelled'):
            controls.append(_control('Cancel competition', 'court_admin_competition_action',
                {'identity': identity, 'operation': 'admin_cancel_competition'},
                {'expected_revision': row['revision']}, 'The domain applies refunds and releases only this event.', danger=True))
        entrants = [{'name': entry['team_name'], 'detail_url': url_for('court_admin_team', identity=entry['team_id'])}
                    for entry in value['entries']]
        matches = []
        for round_value in value['rounds']:
            for match in round_value['matches']:
                matches.append({'round': round_value['number'],
                    'teams': ' / '.join(self.name('court_teams', team) for team in match['team_ids']),
                    'state': 'Bye' if match.get('bye') else match['state'],
                    'winner': self.name('court_teams', match.get('winner_team_id')),
                    **({'detail_url': url_for('court_admin_battle', identity=match['match_id'])} if match.get('match_id') else {})})
        rules = [{'name': key.replace('_', ' ').title(), 'value': shown(val)} for key, val in value['settings'].items()]
        summary = [('Castle', self.name('court_castles', row['castle_id'])), ('State', value['state']),
            ('Entry fee', str(value['entry_fee']) + ' Team Crowns'), ('Teams', len(entrants)), ('Round', value['round'])]
        if value.get('winner_team_id'): summary.append(('Winner', self.name('court_teams', value['winner_team_id'])))
        if value.get('seed_commitment'): summary.append(('Draw commitment', value['seed_commitment']))
        if value.get('revealed_seed'): summary.append(('Revealed draw seed', value['revealed_seed']))
        return self.detail(value['name'], url_for('court_admin_competitions'), summary,
            [section('Entrants', [('name', 'Team')], entrants),
             section('Bracket', [('round', 'Round'), ('teams', 'Match'), ('state', 'Status'), ('winner', 'Winner')], matches),
             section('Rules', [('name', 'Rule'), ('value', 'Value')], rules)], controls)


def register_court_admin(app, db, domain, admin_required):
    console = CourtAdmin(db, domain)

    @app.get('/court')
    @admin_required
    def court_admin_dashboard(): return console.dashboard()

    @app.get('/court/cash')
    @admin_required
    def court_admin_cash(): return console.cash()

    @app.get('/court/cash/<identity>')
    @admin_required
    def court_admin_cash_detail(identity): return console.cash_detail(identity)

    @app.post('/court/cash/<identity>/<decision>')
    @admin_required
    def court_admin_cash_review(identity, decision):
        if decision not in ('approve', 'reject'): abort(404)
        payload = _fields(('command_id', 'revision', 'reason', 'confirmation'), ('revision',))
        console.dispatch(decision + '_cash', {'request_id': identity, **payload})
        return redirect(url_for('court_admin_cash_detail', identity=identity))

    @app.get('/court/areas')
    @admin_required
    def court_admin_areas(): return console.areas()

    @app.get('/court/areas/<identity>')
    @admin_required
    def court_admin_area(identity): return console.area(identity)

    @app.get('/court/castles/<identity>')
    @admin_required
    def court_admin_castle(identity): return console.castle(identity)

    @app.post('/court/activation/<kind>/<identity>')
    @admin_required
    def court_admin_activation(kind, identity):
        if kind not in ('area', 'castle'): abort(404)
        payload = _fields(('command_id', 'mode', 'revision', 'reason', 'confirmation'), ('revision',))
        console.dispatch('set_activation', {'kind': kind, 'id': identity, **payload})
        return redirect(url_for('court_admin_area' if kind == 'area' else 'court_admin_castle', identity=identity))

    @app.get('/court/teams')
    @admin_required
    def court_admin_teams(): return console.teams()

    @app.get('/court/teams/<identity>')
    @admin_required
    def court_admin_team(identity): return console.team(identity)

    @app.get('/court/battles')
    @admin_required
    def court_admin_battles(): return console.battles()

    @app.get('/court/battles/<identity>')
    @admin_required
    def court_admin_battle(identity): return console.battle(identity)

    @app.post('/court/battles/<identity>/cancel')
    @admin_required
    def court_admin_battle_cancel(identity):
        payload = _fields(('command_id', 'expected_revision', 'reason', 'confirmation'), ('expected_revision',))
        console.dispatch('admin_cancel_match', {**payload, 'match_id': identifier(identity)})
        return redirect(url_for('court_admin_battle', identity=identity))

    @app.get('/court/history')
    @admin_required
    def court_admin_history(): return console.history()

    @app.route('/court/settings', methods=['GET', 'POST'])
    @admin_required
    def court_admin_settings():
        if request.method == 'GET': return console.settings()
        numeric = ('revision', *('price_' + k for k in PRICE_LABELS), *('limit_' + k for k in ADJUSTABLE_LIMITS))
        payload = _fields(('command_id', 'reason', 'confirmation', *numeric), numeric)
        settings = domain._settings()
        prices = {key: payload.pop('price_' + key) for key in PRICE_LABELS}
        limits = {**settings['limits'], **{key: payload.pop('limit_' + key) for key in ADJUSTABLE_LIMITS}}
        console.dispatch('set_rules', {**payload, 'prices': prices, 'limits': limits})
        return redirect(url_for('court_admin_settings'))

    @app.get('/court/competitions')
    @admin_required
    def court_admin_competitions(): return console.competitions()

    @app.route('/court/competitions/new', methods=['GET', 'POST'])
    @admin_required
    def court_admin_competition_new():
        if request.method == 'POST':
            numeric = ('expected_revision', 'entry_fee', 'gold', 'base_income', 'turns', 'hero_cap')
            payload = _fields(('command_id', 'castle_id', 'name', 'map_id', 'reason', 'confirmation',
                'fog', 'shroud', 'observers', 'items', *numeric), numeric)
            map_id = payload.pop('map_id')
            map_spec = next((m for m in MAPS if m[0] == map_id), None)
            if map_spec is None: abort(400)
            settings = {'map_id': map_id, 'size': map_spec[2],
                **{key: payload.pop(key) for key in ('gold', 'base_income', 'turns', 'hero_cap')}}
            for flag in ('fog', 'shroud', 'observers', 'items'):
                value = payload.pop(flag)
                if value not in ('true', 'false'): abort(400)
                settings[flag] = value == 'true'
            result = console.dispatch('admin_create_competition', {**payload, 'settings': settings})
            return redirect(url_for('court_admin_competition', identity=result['data']['competition']['id']))
        if set(request.args) - {'castle'} or any(len(request.args.getlist(k)) != 1 for k in request.args): abort(400)
        chosen = request.args.get('castle', '')
        castles = list(db.court_castles.find({'role': 'competition', 'enabled': True,
            'event_id': None, 'reservation_id': None}, {'name': 1, 'area_id': 1, 'revision': 1}).sort('_id', 1).limit(256))
        selected = next((row for row in castles if row['_id'] == chosen), None)
        if chosen and selected is None: abort(404)
        # Location choice is a separate GET so the reviewed revision is exact,
        # without trusting client script to invent Castle revisions.
        return render_template('court_competition_new.html', castles=castles, selected=selected,
            maps=MAPS, command_id=str(uuid4()))

    @app.get('/court/competitions/<identity>')
    @admin_required
    def court_admin_competition(identity): return console.competition(identity)

    @app.post('/court/competitions/<identity>/<operation>')
    @admin_required
    def court_admin_competition_action(identity, operation):
        if operation not in ('admin_lock_competition', 'admin_start_round', 'admin_cancel_competition'): abort(404)
        payload = _fields(('command_id', 'expected_revision', 'reason', 'confirmation'), ('expected_revision',))
        console.dispatch(operation, {'competition_id': identity, **payload})
        return redirect(url_for('court_admin_competition', identity=identity))

    return console
