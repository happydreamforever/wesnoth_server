"""Court administration through real Flask routes and disposable MongoDB."""
from copy import deepcopy
from datetime import timedelta
from html import unescape
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from uuid import uuid4

from werkzeug.datastructures import MultiDict

import test_court_economy as fixture
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.court.admin_web import ADJUSTABLE_LIMITS, PRICE_LABELS, ZERO_LIMITS
from alliance.court.battle_schema import SCHEMAS as BATTLE_SCHEMAS, bootstrap_indexes
from alliance.court.battles import DEFAULT_BATTLE_SETTINGS
from alliance.web import create_app


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set')
class CourtEconomyWeb(unittest.TestCase):
    setUpClass = classmethod(fixture.CourtEconomy.setUpClass.__func__)
    tearDownClass = classmethod(fixture.CourtEconomy.tearDownClass.__func__)
    tearDown = fixture.CourtEconomy.tearDown
    player = fixture.CourtEconomy.player
    make_team = fixture.CourtEconomy.make_team
    command = fixture.CourtEconomy.command
    credit = fixture.CourtEconomy.credit
    tx = fixture.CourtEconomy.tx
    wallet = fixture.CourtEconomy.wallet

    def setUp(self):
        fixture.CourtEconomy.setUp(self)
        for name, validator in BATTLE_SCHEMAS.items():
            self.db.create_collection(name, validator=validator, validationLevel='strict')
        bootstrap_indexes(self.db)
        bootstrap_auth_schema(self.db)
        self.password = 'Disposable-host-password-123'
        self.password_hash = hash_password(self.password)
        self.db.accounts.update_many({}, {'$set': {'password_hash': self.password_hash}})
        self.db.court_settings.insert_one({'_id': 'population', 'revision': 0})
        for number in range(1, 3):
            self.db.court_areas.insert_one({'_id': f'A{number:03}', 'name': f'Area {number}',
                'number': number, 'realm_id': 'R001', 'realm_name': 'Emerald Realm',
                'enabled': number == 1, 'mode': 'auto', 'team_count': 1 if number == 1 else 0,
                'revision': 0, 'below_since': None})
        for number in range(1, 7):
            self.db.court_castles.insert_one({'_id': f'A001-C{({1: 10, 2: 55}.get(number, number)):03}', 'area_id': 'A001',
                'name': f'Castle {number}', 'role': 'competition' if number <= 2 else 'normal',
                'enabled': True, 'mode': 'on', 'owner_team_id': None, 'reservation_id': None,
                'event_id': None, 'protected_until': None, 'revision': 0, 'below_since': None})
        self.request_row = self.command('request_cash', kind='personal', package=100)['request']
        self.settings = SimpleNamespace(host='127.0.0.1', port=18765,
            secret_key='fixture-cookie-' + uuid4().hex, bridge_secret='fixture-bridge-' + uuid4().hex)
        self.app = create_app(self.settings, self.db)
        self.app.config['TESTING'] = True
        self.domain = self.app.extensions['alliance_domain']
        self.domain.clock = lambda: self.now
        self.http = self.app.test_client()
        self.login()

    def csrf(self, path='/court'):
        response = self.http.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
        return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)).group(1)

    def login(self):
        name = self.db.accounts.find_one({'_id': self.admin})['username']
        result = self.http.post('/login', data={'csrf_token': self.csrf('/login'),
            'username': name, 'password': self.password})
        self.assertEqual(result.status_code, 302)

    def form(self, path='/court', **payload):
        return {'csrf_token': self.csrf(path), 'command_id': str(uuid4()),
            'revision': '0', 'reason': 'Host reviewed this change', 'confirmation': 'confirmed', **payload}

    def snapshot(self):
        return {name: list(self.db[name].find().sort('_id', 1)) for name in self.db.list_collection_names()
            if name not in ('auth_sessions', 'auth_attempts') and not name.startswith('system.')}

    def export(self, name, response):
        destination = os.environ.get('COURT_ADMIN_RENDER_DIR')
        if not destination: return
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + '.html')).write_text(response.get_data(as_text=True))
        (target / 'static').mkdir(exist_ok=True)
        (target / 'static/admin.css').write_bytes((Path(__file__).resolve().parents[1] / 'alliance/static/admin.css').read_bytes())

    def cash_path(self):
        return '/court/cash/' + self.request_row['id']

    def test_pages_read_only_with_current_theme_and_no_credentials(self):
        self.db.accounts.update_one({'_id': self.actor}, {'$set': {'private_canary': 'DO-NOT-RENDER-ACCOUNT'}})
        paths = {'overview': '/court', 'cash': '/court/cash', 'cash-review': self.cash_path(),
            'areas': '/court/areas', 'area': '/court/areas/A001', 'castle': '/court/castles/A001-C010',
            'teams': '/court/teams', 'team': '/court/teams/' + self.team,
            'battles': '/court/battles', 'history': '/court/history', 'settings': '/court/settings',
            'competitions': '/court/competitions', 'competition-location': '/court/competitions/new',
            'competition-new': '/court/competitions/new?castle=A001-C010'}
        before = self.snapshot()
        for label, path in paths.items():
            with self.subTest(path=path):
                response = self.http.get(path)
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:400])
                body = response.get_data(as_text=True)
                self.assertIn('Emerald Court', body)
                self.assertIn('/static/admin.css', body)
                for secret in (self.password_hash, self.settings.secret_key, self.settings.bridge_secret,
                    'DO-NOT-RENDER-ACCOUNT', 'password_hash'):
                    self.assertNotIn(secret, body)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
                self.export(label, response)
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_player_and_nonlocal_access_denied(self):
        anonymous = self.app.test_client()
        for path in ('/court', self.cash_path(), '/court/settings', '/court/competitions/new'):
            self.assertEqual(anonymous.get(path).status_code, 302)
            self.assertEqual(self.http.get(path, environ_overrides={'REMOTE_ADDR': '10.0.0.10'}).status_code, 403)
        name = self.db.accounts.find_one({'_id': self.actor})['username']
        token = AuthService(self.db).authenticate(name, self.password, 'player')['token']
        with anonymous.session_transaction() as session: session['admin_token'] = token
        self.assertEqual(anonymous.get('/court').status_code, 302)
        self.assertEqual(self.db.court_wallets.count_documents({}), 0)

    def test_cash_approval_csrf_exact_fields_revision_and_command_replay(self):
        path = self.cash_path() + '/approve'
        values = self.form(self.cash_path())
        invalid = dict(values)
        invalid.pop('csrf_token')
        self.assertEqual(self.http.post(path, data=invalid).status_code, 400)
        self.assertEqual(self.http.post(path, data={**values, 'amount': '1000000'}).status_code, 400)
        self.assertEqual(self.http.post(path + '?amount=1000000', data=values).status_code, 400)
        duplicate = MultiDict(values)
        duplicate.add('revision', '0')
        self.assertEqual(self.http.post(path, data=duplicate).status_code, 400)
        self.assertEqual(self.http.post(path, data={**values, 'confirmation': 'no'}).status_code, 409)
        result = self.http.post(path, data=values)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.http.post(path, data=values).status_code, 302)
        self.assertEqual(self.wallet()['available'], 100)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'approve_crowns'}), 1)
        self.assertEqual(self.http.post(path, data={**values, 'command_id': str(uuid4())}).status_code, 409)
        self.export('cash-approved', self.http.get(self.cash_path()))

    def test_cash_rejection_changes_no_balance(self):
        self.assertEqual(self.http.post(self.cash_path() + '/reject', data=self.form()).status_code, 302)
        self.assertEqual(self.db.court_wallets.count_documents({}), 0)
        self.assertEqual(self.db.court_cash_requests.find_one()['state'], 'rejected')
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'reject_crowns'}), 1)

    def test_admin_role_revoked_after_opening_form_cannot_spend(self):
        values = self.form()
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'suspended'}})
        result = self.http.post(self.cash_path() + '/approve', data=values)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.headers['Location'], '/login')
        self.assertEqual(self.db.court_wallets.count_documents({}), 0)

    def test_retired_admin_and_internal_routes_cannot_reach_old_mutations(self):
        values = self.form()
        before = self.snapshot()
        retired = ('/teams/' + self.team + '/manage', '/teams/' + self.team + '/area',
            '/areas', '/areas/area-1/edit', '/world/command', '/companies/' + self.actor + '/rest',
            '/manage-cancel/run/previous-run', '/manage-cancel/plan/previous-plan',
            '/manage-cancel/world/previous-world', '/manage/defenses/previous-defense/withdraw',
            '/runs/previous-run/resolve', '/runs/previous-run/cancel')
        for path in retired:
            with self.subTest(path=path):
                self.assertEqual(self.http.post(path, data=values).status_code, 409)
        for path in ('/companies', '/plans', '/engagements', '/manage/defenses', '/operations', '/runs'):
            response = self.http.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], '/court')
        for suffix in ('world/command', 'company/enlist', 'progression/finish', 'shared/confirm',
                'product/battle_select_hero', 'team-directory/create_team', 'teams',
                'server/battles/previous-run/finish', 'server/campaigns/previous-run/finish'):
            response = self.http.post('/internal/v1/' + suffix, json={},
                headers={'Authorization': 'Bearer ' + self.settings.bridge_secret})
            self.assertEqual(response.status_code, 409, suffix)
            self.assertEqual(response.get_json()['error']['code'], 'unsupported_ruleset')
        self.assertEqual(self.snapshot(), before)

    def test_hero_management_catalog_and_campaign_entry_remain_available(self):
        response = self.http.get('/accounts/' + self.actor + '/heroes')
        self.assertEqual(response.status_code, 200)
        self.assertIn('117', response.get_data(as_text=True))
        self.assertEqual(self.http.get('/accounts/' + self.actor + '/heroes/abhai/grant').status_code, 200)
        self.assertEqual(self.http.get('/rooms').status_code, 200)
        username = self.db.accounts.find_one({'_id': self.actor})['username']
        token = self.app.extensions['alliance_auth'].authenticate(username, self.password, 'player')['token']
        headers = {'Authorization': 'Bearer ' + self.settings.bridge_secret, 'X-Player-Token': token}
        response = self.http.post('/internal/v1/product/hero_catalog', json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        catalog = response.get_json()
        self.assertEqual(len(catalog['heroes']), 117)
        self.assertTrue(catalog['campaigns'])
        me = self.http.get('/internal/v1/me', headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertIn('heroes', me.get_json()['account'])
        # The authored story route remains live: its own input validation,
        # rather than the retired-Team gate, rejects this incomplete request.
        response = self.http.post('/internal/v1/product/story_begin', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.get_json()['error']['code'], 'unsupported_ruleset')

    def test_search_pagination_and_malformed_query_guards(self):
        for index in range(3, 40):
            self.db.court_areas.insert_one({'_id': f'A{index:03}', 'name': f'Paging {index}',
                'realm_name': 'Emerald Realm', 'realm_id': 'R001', 'number': index,
                'mode': 'auto', 'enabled': False, 'team_count': 0, 'revision': 0})
        first = self.http.get('/court/areas?q=Paging')
        self.assertEqual(first.status_code, 200)
        self.assertIn('rel="next"', first.get_data(as_text=True))
        self.assertNotIn('Paging ', self.http.get('/court/areas?q=.*').get_data(as_text=True))
        second = self.http.get('/court/areas?q=Paging&page=2')
        self.assertNotIn('rel="next"', second.get_data(as_text=True))
        for query in ('?page=0', '?page=01', '?page=10000', '?page=1&page=2', '?q=a&q=b',
            '?state=unknown', '?extra=secret', '?q=' + 'x' * 81):
            self.assertEqual(self.http.get('/court/areas' + query).status_code, 400, query)
        for index in range(3):
            self.db.court_history.insert_one({'_id': str(uuid4()), 'team_id': self.team,
                'kind': 'battle', 'title': 'Chronology event ' + str(index),
                'created_at': self.now + timedelta(minutes=index), 'data': {}})
        body = self.http.get('/court/history').get_data(as_text=True)
        self.assertLess(body.index('Chronology event 2'), body.index('Chronology event 1'))
        self.assertLess(body.index('Chronology event 1'), body.index('Chronology event 0'))

    def test_area_activation_review_and_owned_castle_guard(self):
        path = '/court/activation/area/A002'
        self.assertEqual(self.http.post(path, data=self.form(mode='on')).status_code, 302)
        area = self.db.court_areas.find_one({'_id': 'A002'})
        self.assertEqual(area['mode'], 'on')
        self.assertTrue(area['enabled'])
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'court_activation'}), 1)
        self.db.court_castles.update_one({'_id': 'A001-C003'}, {'$set': {'owner_team_id': self.team}})
        self.assertEqual(self.http.post('/court/activation/castle/A001-C003',
            data=self.form(mode='off')).status_code, 409)
        self.assertTrue(self.db.court_castles.find_one({'_id': 'A001-C003'})['enabled'])

    def rule_form(self):
        settings = self.domain._settings()
        return {**self.form('/court/settings', revision=str(settings['revision'])),
            **{'price_' + key: str(settings['prices'][key]) for key in PRICE_LABELS},
            **{'limit_' + key: str(settings['limits'][key]) for key in ADJUSTABLE_LIMITS}}

    def test_prices_are_whole_numbers_and_stale_rule_form_cannot_overwrite(self):
        values = self.rule_form()
        invalid = {**values, 'price_create_team': '1.5'}
        self.assertEqual(self.http.post('/court/settings', data=invalid).status_code, 400)
        result = self.http.post('/court/settings', data={**values, 'price_create_team': '60'})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.domain._settings()['prices']['create_team'], 60)
        self.assertEqual(self.domain._settings()['limits']['team_members'], 10)
        self.assertEqual(self.http.post('/court/settings', data={**values, 'command_id': str(uuid4())}).status_code, 409)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'court_rules'}), 1)

    def test_zero_allowances_disable_economy_without_disabling_population_safety(self):
        body = self.http.get('/court/settings').get_data(as_text=True)
        for key in ZERO_LIMITS:
            self.assertRegex(body, 'name="limit_' + key + '"[^>]*min="0"')
        values = {**self.rule_form(), **{'limit_' + key: '0' for key in ZERO_LIMITS}}
        self.assertEqual(self.http.post('/court/settings', data=values).status_code, 302)
        self.assertTrue(all(self.domain._settings()['limits'][key] == 0 for key in ZERO_LIMITS))
        self.assertEqual(self.domain._settings()['limits']['team_members'], 10)
        invalid = {**self.rule_form(), 'limit_minimum_normal_castles': '0'}
        self.assertEqual(self.http.post('/court/settings', data=invalid).status_code, 409)
        self.assertEqual(self.domain._settings()['limits']['minimum_normal_castles'], 4)
        self.export('settings-zero', self.http.get('/court/settings'))

    def test_technical_battle_cancel_requires_current_review_and_preserves_other_plan(self):
        self.db.court_castles.update_one({'_id': 'A001-C003'}, {'$set': {'role': 'plan'}})
        opponent = self.make_team(self.outsider)
        self.credit(100, self.team, 'team')
        first, second = [self.command('create_plan', castle_id='A001-C003', opponent_team_id=opponent,
            settings=deepcopy(DEFAULT_BATTLE_SETTINGS), start_delay_minutes=5, price_revision=0)['match']['id']
            for _ in range(2)]
        path = '/court/battles/' + first
        other = self.db.court_matches.find_one({'_id': second})
        form = self.form(path, expected_revision='0')
        form.pop('revision')
        self.assertIn('Cancel battle for a technical issue', self.http.get(path).get_data(as_text=True))
        self.export('battle-cancel-review', self.http.get(path))
        bad = {**form, 'expected_revision': '999'}
        self.assertEqual(self.http.post(path + '/cancel', data=bad).status_code, 409)
        self.assertEqual(self.wallet(self.team, 'team')['held'], 20)
        self.assertEqual(self.http.post(path + '/cancel', data={**form, 'confirmation': 'no'}).status_code, 409)
        self.assertEqual(self.http.post(path + '/cancel', data=form).status_code, 302)
        self.assertEqual(self.http.post(path + '/cancel', data=form).status_code, 302)
        cancelled = self.db.court_matches.find_one({'_id': first})
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertEqual(self.db.court_matches.find_one({'_id': second}), other)
        self.assertEqual(self.wallet(self.team, 'team')['available'], 90)
        self.assertEqual(self.wallet(self.team, 'team')['held'], 10)
        self.assertEqual(self.db.court_battle_receipts.count_documents({}), 0)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'court_cancel_match'}), 1)
        self.assertNotIn('Cancel battle for a technical issue', self.http.get(path).get_data(as_text=True))
        form.update(command_id=str(uuid4()), expected_revision=str(cancelled['revision']))
        self.assertEqual(self.http.post(path + '/cancel', data=form).status_code, 409)
        self.export('battle-cancelled', self.http.get(path))

    def competition_form(self):
        result = self.form('/court/competitions/new?castle=A001-C010', castle_id='A001-C010',
            name='Emerald Cup', entry_fee='10', expected_revision='0', map_id='weldyn-channel',
            gold='100', base_income='2', turns='30', hero_cap='30', fog='true', shroud='false',
            observers='false', items='false')
        result.pop('revision')
        return result

    def create_competition(self):
        response = self.http.post('/court/competitions/new', data=self.competition_form())
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return response.headers['Location']

    def test_competition_form_freezes_rules_and_does_not_expose_private_seed(self):
        path = self.create_competition()
        row = self.db.court_competitions.find_one()
        self.assertEqual(row['settings']['map_id'], 'weldyn-channel')
        self.assertEqual(row['settings']['size'], 1)
        self.assertEqual(row['entry_fee'], 10)
        response = self.http.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(row['seed'], response.get_data(as_text=True))
        self.assertIn('Lock registration', response.get_data(as_text=True))
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'court_competition_create'}), 1)
        self.export('competition-registration', response)

    def test_competition_cancel_review_releases_location(self):
        path = self.create_competition()
        payload = self.form(path, expected_revision='0')
        payload.pop('revision')
        response = self.http.post(path + '/admin_cancel_competition', data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.court_competitions.find_one()['state'], 'cancelled')
        self.assertIsNone(self.db.court_castles.find_one({'_id': 'A001-C010'})['event_id'])
        self.export('competition-cancelled', self.http.get(path))

    def test_competition_unknown_fields_or_invalid_boolean_rejected(self):
        form = self.competition_form()
        self.assertEqual(self.http.post('/court/competitions/new', data={**form, 'seed': 'attacker-chosen'}).status_code, 400)
        self.assertEqual(self.http.post('/court/competitions/new', data={**form, 'fog': 'yes'}).status_code, 400)
        self.assertEqual(self.http.post('/court/competitions/new', data={**form, 'map_id': 'invented'}).status_code, 400)
        self.assertEqual(self.db.court_competitions.count_documents({}), 0)

    def test_long_names_full_roster_and_empty_lists_render(self):
        self.db.court_teams.update_one({'_id': self.team}, {'$set': {'name': 'Emerald Court Guardians of the Dawn Vale'}})
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'username': 'AdministratorWith24Chars'}})
        for index in range(8):
            actor = self.player()
            self.db.accounts.update_one({'_id': actor}, {'$set': {'username': 'LongPlayerName_0000000' + str(index)}})
            self.db.court_teams.update_one({'_id': self.team}, {'$push': {'members': {'account_id': actor, 'joined_at': self.now}}})
        response = self.http.get('/court/teams/' + self.team)
        self.assertEqual(response.status_code, 200)
        self.assertIn('10/10', response.get_data(as_text=True))
        self.export('team-full-long-names', response)
        empty = self.http.get('/court/cash?state=approved')
        self.assertEqual(empty.status_code, 200)
        self.assertIn('No matching records.', empty.get_data(as_text=True))
        self.export('cash-empty-long-admin', empty)

    def test_competition_lock_start_and_bracket_controls_follow_lifecycle(self):
        path = self.create_competition()
        identity = path.rsplit('/', 1)[-1]
        opponent_team = self.make_team(self.outsider)
        for actor, team in ((self.actor, self.team), (self.outsider, opponent_team)):
            self.credit(100, team, 'team')
            revision = self.db.court_competitions.find_one({'_id': identity})['revision']
            self.service.court_command(actor, {'version': 1, 'operation': 'enter_competition',
                'payload': {'command_id': str(uuid4()), 'competition_id': identity,
                    'expected_revision': revision, 'price_revision': 0}})
        values = self.form(path, expected_revision='2')
        values.pop('revision')
        response = self.http.post(path + '/admin_lock_competition', data=values)
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        locked = self.db.court_competitions.find_one({'_id': identity})
        self.assertEqual(locked['state'], 'round_ready')
        self.assertEqual(self.wallet(self.team, 'team')['available'], 90)
        self.assertEqual(self.wallet(self.team, 'team')['held'], 0)
        response = self.http.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Start next round', response.get_data(as_text=True))
        self.export('competition-bracket', response)
        values = self.form(path, expected_revision=str(locked['revision']))
        values.pop('revision')
        self.assertEqual(self.http.post(path + '/admin_start_round', data=values).status_code, 302)
        self.assertEqual(self.db.court_competitions.find_one({'_id': identity})['state'], 'playing')
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'court_competition_start_round'}), 1)
        self.export('competition-playing', self.http.get(path))
        match = self.db.court_matches.find_one({'competition_id': identity})
        review = self.form('/court/battles/' + match['_id'], expected_revision=str(match['revision']))
        review.pop('revision')
        self.assertEqual(self.http.post('/court/battles/' + match['_id'] + '/cancel', data=review).status_code, 302)
        refreshed = self.db.court_competitions.find_one({'_id': identity})
        self.assertEqual(refreshed['state'], 'playing')
        self.assertNotEqual(refreshed['rounds'][0]['matches'][0]['match_id'], match['_id'])
        self.assertEqual(self.wallet(self.team, 'team')['available'], 90)
        response = self.http.get(path)
        self.assertIn('Start replacement matches', response.get_data(as_text=True))
        self.export('competition-replacement', response)
        values = self.form(path, expected_revision=str(refreshed['revision']))
        values.pop('revision')
        self.assertEqual(self.http.post(path + '/admin_start_round', data=values).status_code, 302)
