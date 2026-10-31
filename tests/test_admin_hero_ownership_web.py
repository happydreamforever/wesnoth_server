"""Hero ownership HTTP acceptance against an isolated real replica set.

Rendered exports are real Flask responses containing disposable fixture data;
they do not establish Windows browser or Android acceptance.
"""
from html import unescape
import os
from pathlib import Path
import re
import unittest
from uuid import uuid4

from werkzeug.datastructures import MultiDict

import test_admin_console as fixture
from alliance.admin_management import admin_hero_grant_form
from alliance.auth import AuthService
from alliance.heroes import load_catalog


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable replica set')
class AdminHeroOwnershipWebTests(unittest.TestCase):
    setUpClass = classmethod(fixture.AdminConsoleTests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.AdminConsoleTests.tearDownClass.__func__)
    tearDown = fixture.AdminConsoleTests.tearDown
    csrf = fixture.AdminConsoleTests.csrf
    login = fixture.AdminConsoleTests.login
    snapshot = fixture.AdminConsoleTests.snapshot

    def setUp(self):
        fixture.AdminConsoleTests.setUp(self)
        self.identity = self.player['_id']
        self.path = '/accounts/' + self.identity + '/heroes'
        self.hero_id = 'abhai'
        self.review = self.path + '/' + self.hero_id + '/grant'
        self.catalog, _ = load_catalog()

    def form(self, **changes):
        value = {'csrf_token': self.csrf(self.review),
                 'revision': str(self.domain.get_account(self.identity)['revision']),
                 'reason': 'Host approved this hero for the player', 'confirmation': 'confirmed'}
        value.update(changes)
        return value

    def grant_links(self, html):
        pattern = r'href="(' + re.escape(self.path) + r'/[a-z0-9_-]+/grant)"'
        return set(re.findall(pattern, html))

    def export(self, name, response):
        destination = os.environ.get('ADMIN_HERO_RENDER_DIR')
        if not destination:
            return
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + '.html')).write_text(response.get_data(as_text=True), encoding='utf-8')
        static = target / 'static'
        static.mkdir(exist_ok=True)
        (static / 'admin.css').write_bytes(
            (Path(__file__).resolve().parents[1] / 'alliance/static/admin.css').read_bytes())

    def seed(self, hero_id=None, *, total=64):
        hero_id = hero_id or self.hero_id
        form = admin_hero_grant_form(hero_id)
        row = {'_id': str(uuid4()), 'account_id': self.identity, 'hero_id': hero_id,
               'forms': [form['id']], 'total_experience': total, 'revision': 3,
               'private_canary': 'PRIVATE-HERO-NOT-FOR-HTML'}
        self.db.account_heroes.insert_one(row)
        return row

    def test_account_links_catalogue_and_review_are_read_only_and_secret_free(self):
        self.db.accounts.update_one({'_id': self.identity}, {'$set': {'private_canary': 'PRIVATE-ACCOUNT-NOT-FOR-HTML'}})
        before = self.snapshot()
        for name, path in (('account-empty', '/accounts/' + self.identity),
                           ('heroes-empty', self.path), ('grant-review', self.review)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                text = response.get_data(as_text=True)
                for private in (self.hash, self.settings.bridge_secret, self.settings.secret_key,
                                'PRIVATE-ACCOUNT-NOT-FOR-HTML', 'password_hash'):
                    self.assertNotIn(private, text)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
                self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
                self.export(name, response)
        account = self.client.get('/accounts/' + self.identity).get_data(as_text=True)
        self.assertIn('Manage heroes', account)
        self.assertIn('Owned heroes', account)
        self.assertIn(self.path, account)
        review = self.client.get(self.review).get_data(as_text=True)
        self.assertIn(admin_hero_grant_form(self.hero_id)['source_type'], review)
        self.assertIn('name="confirmation"', review)
        self.assertIn('name="reason"', review)
        self.assertEqual(before, self.snapshot())

    def test_catalogue_pagination_covers_all_117_once_and_preserves_filters(self):
        seen = set()
        for page in range(1, 11):
            response = self.client.get(self.path + '?state=locked&page=' + str(page))
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            links = self.grant_links(text)
            self.assertEqual(len(links), 12 if page < 10 else 9)
            self.assertFalse(seen & links)
            seen.update(links)
            if page < 10:
                next_link = re.search(r'<a\b[^>]*rel="next"[^>]*>', text)
                if next_link is None:
                    next_link = re.search(r'<a\b[^>]*href="[^"]+"[^>]*rel="next"[^>]*>', text)
                self.assertIsNotNone(next_link)
                self.assertIn('state=locked', unescape(next_link.group(0)))
                self.assertIn('page=' + str(page + 1), unescape(next_link.group(0)))
            else:
                self.assertNotIn('rel="next"', text)
        self.assertEqual(seen, {self.path + '/' + hero['id'] + '/grant' for hero in self.catalog['heroes']})

    def test_search_and_owned_locked_filters(self):
        self.seed()
        for query in ('?q=Abhai', '?q=aBhAi'):
            response = self.client.get(self.path + query)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Abhai', response.get_data(as_text=True))
        owned = self.client.get(self.path + '?state=owned')
        self.assertIn('Abhai', owned.get_data(as_text=True))
        self.assertFalse(self.grant_links(owned.get_data(as_text=True)))
        self.assertNotIn('PRIVATE-HERO-NOT-FOR-HTML', owned.get_data(as_text=True))
        self.export('heroes-owned', owned)
        locked = self.client.get(self.path + '?state=locked&q=Abhai')
        self.assertFalse(self.grant_links(locked.get_data(as_text=True)))
        literal = self.client.get(self.path + '?q=.*')
        self.assertFalse(self.grant_links(literal.get_data(as_text=True)))
        self.export('heroes-no-results', literal)

    def test_invalid_search_shape_is_rejected_without_writes(self):
        before = self.snapshot()
        for query in ('?page=0', '?page=-1', '?page=10000', '?page=01', '?page=1&page=2',
                      '?q=a&q=b', '?q=' + 'x' * 81, '?state=unknown', '?state=owned&state=locked',
                      '?extra=1'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.path + query).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_anonymous_and_player_sessions_cannot_manage_ownership(self):
        anonymous = self.app.test_client()
        for path in (self.path, self.review):
            response = anonymous.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], '/login')
        auth = AuthService(self.db)
        player_token = auth.authenticate('PlayerOne', self.password, 'player')['token']
        impostor = self.app.test_client()
        with impostor.session_transaction() as session:
            session['admin_token'] = player_token
        before = self.snapshot()
        for path in (self.path, self.review):
            self.assertEqual(impostor.get(path).status_code, 302)
        response = impostor.get('/login')
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)).group(1)
        with impostor.session_transaction() as session:
            session['admin_token'] = player_token
        denied = impostor.post(self.review, data={**self.form(), 'csrf_token': csrf})
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied.headers['Location'], '/login')
        self.assertEqual(before, self.snapshot())

    def test_remote_requests_and_missing_csrf_are_rejected(self):
        form = self.form()
        before = self.snapshot()
        for path in (self.path, self.review):
            self.assertEqual(self.client.get(path, environ_overrides={'REMOTE_ADDR': '192.168.1.2'}).status_code, 403)
        self.assertEqual(self.client.post(self.review, data=form, environ_overrides={'REMOTE_ADDR': '192.168.1.2'}).status_code, 403)
        missing = dict(form)
        missing.pop('csrf_token')
        self.assertEqual(self.client.post(self.review, data=missing).status_code, 400)
        self.assertEqual(self.client.post(self.review, data=missing, headers={'Origin': 'https://untrusted.invalid'}).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_confirmation_and_exact_form_shape_are_required(self):
        form = self.form()
        before = self.snapshot()
        malformed = []
        missing = dict(form)
        missing.pop('confirmation')
        malformed.append(missing)
        malformed.extend(({**form, 'confirmation': ''}, {**form, 'confirmation': 'true'},
                          {**form, 'hero_id': 'deoran'}, {**form, 'total_experience': '999'},
                          {**form, 'form_id': 'forged'}, MultiDict(list(form.items()) + [('reason', 'Second reason')]),
                          MultiDict(list(form.items()) + [('revision', form['revision'])])))
        for data in malformed:
            with self.subTest(data=list(data)):
                self.assertEqual(self.client.post(self.review, data=data).status_code, 400)
        self.assertEqual(self.client.post(self.review + '?hero_id=deoran', data=form).status_code, 400)
        self.assertEqual(self.client.post(self.review, json=form).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_invalid_revisions_and_reason_do_not_grant(self):
        form = self.form()
        before = self.snapshot()
        for revision in ('', '-1', '01', '1.0', 'true', '9223372036854775808'):
            with self.subTest(revision=revision):
                self.assertEqual(self.client.post(self.review, data={**form, 'revision': revision}).status_code, 400)
        for reason in ('', '  ', 'x', 'x' * 501):
            with self.subTest(reason=reason[:10]):
                self.assertEqual(self.client.post(self.review, data={**form, 'reason': reason}).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_confirmed_grant_is_visible_usable_audited_without_campaign_credit(self):
        token = AuthService(self.db).authenticate('PlayerOne', self.password, 'player')['token']
        account_before = self.db.accounts.find_one({'_id': self.identity})
        form = self.form()
        result = self.client.post(self.review, data=form)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.headers['Location'], self.path)
        hero = self.db.account_heroes.find_one({'account_id': self.identity, 'hero_id': self.hero_id})
        granted = admin_hero_grant_form(self.hero_id)
        self.assertEqual(hero['forms'], [granted['id']])
        self.assertEqual(hero['total_experience'], 0)
        profile = self.domain.get_account(self.identity)
        self.assertEqual(len(profile['heroes']), 1)
        self.assertEqual(profile['heroes'][0]['hero_level'], 1)
        selected = self.domain._selection(self.identity, self.hero_id, granted['id'])
        self.assertEqual(selected['unit_type'], granted['unit_type'])
        self.assertEqual(selected['hero_level'], 1)
        after = self.db.accounts.find_one({'_id': self.identity})
        expected = dict(account_before, revision=account_before['revision'] + 1)
        self.assertEqual(after, expected)
        for collection in ('story_checkpoints', 'settlements', 'companies', 'company_soldiers'):
            self.assertEqual(self.db[collection].count_documents({}), 0)
        audit = self.db.admin_audit.find_one({'action': 'grant_hero', 'target_id': self.identity})
        self.assertEqual(audit['actor_id'], self.admin['_id'])
        self.assertEqual(audit['reason'], form['reason'])
        self.assertEqual(audit['after']['hero_id'], self.hero_id)
        self.assertEqual(AuthService(self.db).validate_token(token, 'player')['_id'], self.identity)
        self.export('heroes-after-grant', self.client.get(self.path))
        self.export('account-after-grant', self.client.get('/accounts/' + self.identity))

    def test_duplicate_submit_and_existing_progress_are_not_reset(self):
        form = self.form()
        self.assertEqual(self.client.post(self.review, data=form).status_code, 302)
        before = self.snapshot()
        self.assertEqual(self.client.post(self.review, data=form).status_code, 409)
        self.assertEqual(before, self.snapshot())
        self.db.account_heroes.update_one({'account_id': self.identity, 'hero_id': self.hero_id},
                                         {'$set': {'total_experience': 164}, '$inc': {'revision': 2}})
        fresh = {**form, 'revision': str(self.domain.get_account(self.identity)['revision'])}
        before = self.snapshot()
        result = self.client.post(self.review, data=fresh)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'grant_hero'}), 1)
        self.export('hero-already-owned', result)

    def test_stale_review_retains_reason_without_rebinding_consent(self):
        form = self.form(reason='Reviewed <script>alert(1)</script>')
        self.db.accounts.update_one({'_id': self.identity}, {'$inc': {'revision': 1}})
        before = self.snapshot()
        response = self.client.post(self.review, data=form)
        self.assertEqual(response.status_code, 409)
        text = response.get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', text)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', text)
        hidden = re.search(r'name="revision"[^>]*value="([^"]+)"', text)
        # A stale form may keep its stale binding or remove the submission form;
        # it must never silently authorize the newly read account revision.
        if hidden:
            self.assertEqual(hidden.group(1), form['revision'])
        self.assertEqual(before, self.snapshot())
        self.export('hero-stale-review', response)

    def test_unknown_hero_missing_account_and_admin_target_are_rejected(self):
        before = self.snapshot()
        invalid = self.path + '/not_a_catalogue_hero/grant'
        self.assertEqual(self.client.get(invalid).status_code, 404)
        self.assertEqual(self.client.post(invalid, data=self.form()).status_code, 404)
        missing = '/accounts/' + str(uuid4()) + '/heroes'
        for path in (missing, missing + '/' + self.hero_id + '/grant'):
            self.assertEqual(self.client.get(path).status_code, 404)
        admin_path = '/accounts/' + self.admin['_id'] + '/heroes'
        for path in (admin_path, admin_path + '/' + self.hero_id + '/grant'):
            self.assertEqual(self.client.get(path).status_code, 403)
        admin_form = {**self.form(), 'revision': str(self.domain.get_account(self.admin['_id'])['revision'])}
        self.assertEqual(self.client.post(admin_path + '/' + self.hero_id + '/grant', data=admin_form).status_code, 403)
        self.assertEqual(before, self.snapshot())

    def test_filter_input_is_html_escaped(self):
        response = self.client.get(self.path, query_string={'q': '<img src=x onerror=alert(1)>'})
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertNotIn('<img src=x', text)
        self.assertIn('&lt;img', text)

    def test_full_collection_and_long_name_render_without_grant_actions(self):
        self.db.accounts.update_one({'_id': self.identity}, {'$set': {'username': 'LongPlayerName12345678901'}})
        for hero in self.catalog['heroes']:
            self.seed(hero['id'])
        before = self.snapshot()
        for name, path in (('heroes-full-collection', self.path + '?state=owned'),
                           ('heroes-full-locked-empty', self.path + '?state=locked'),
                           ('account-full-collection', '/accounts/' + self.identity)):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertFalse(self.grant_links(text))
            self.assertNotIn('PRIVATE-HERO-NOT-FOR-HTML', text)
            self.export(name, response)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
