"""HTTP/security integration checks against an isolated local MongoDB replica set.

Run with ALLIANCE_TEST_MONGO_URI; each class owns a fresh alliance_test_* database.
No production configuration or .env file is read.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from pymongo import MongoClient

from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService
from alliance.schema import bootstrap_schema
from alliance.web import create_app


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGO_URI"), "Set ALLIANCE_TEST_MONGO_URI to an isolated local replica set.")
class AllianceWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ["ALLIANCE_TEST_MONGO_URI"]
        parsed = urlsplit(uri)
        if parsed.scheme != "mongodb" or parsed.hostname != "127.0.0.1":
            raise RuntimeError("Web tests require an isolated loopback database.")
        cls.mongo = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        cls.database_name = "alliance_test_web_" + uuid4().hex
        cls.db = cls.mongo[cls.database_name]
        bootstrap_schema(cls.db)
        bootstrap_auth_schema(cls.db)
        cls.password = "Only-for-isolated-web-tests-123"
        cls.password_hash = hash_password(cls.password)
        cls.settings = SimpleNamespace(host="127.0.0.1", port=18765,
            secret_key="test-cookie-secret-" + uuid4().hex,
            bridge_secret="test-bridge-secret-" + uuid4().hex)

    @classmethod
    def tearDownClass(cls):
        cls.mongo.drop_database(cls.database_name)
        cls.mongo.close()

    def setUp(self):
        for name in ("accounts", "teams", "game_runs", "settlements", "admin_audit", "auth_sessions", "auth_attempts"):
            self.db[name].delete_many({})
        self.db.areas.delete_many({"_id": {"$ne": "area-1"}})
        self.domain = AllianceService(self.db)
        self.admin = self.domain.register("Operator", self.password_hash)
        self.db.accounts.update_one({"_id": self.admin["_id"]}, {"$set": {"role": "admin"}})
        self.player = self.domain.register("PlayerOne", self.password_hash)
        self.auth = AuthService(self.db)
        self.app = create_app(self.settings, self.db)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.bridge = {"Authorization": "Bearer " + self.settings.bridge_secret}

    def csrf(self, path="/login"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def login_admin(self):
        response = self.client.post("/login", data={"csrf_token": self.csrf(), "username": "Operator", "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        return response

    def player_headers(self):
        result = self.auth.authenticate("PlayerOne", self.password, "player")
        return {**self.bridge, "X-Player-Token": result["token"]}

    def test_bind_rejects_nonloopback_configuration(self):
        bad = SimpleNamespace(**vars(self.settings))
        bad.host = "0.0.0.0"
        with self.assertRaises(ValueError):
            create_app(bad, self.db)

    def test_remote_and_rebound_hosts_rejected_before_authentication(self):
        response = self.client.get("/login", environ_overrides={"REMOTE_ADDR": "192.168.1.10"})
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/login", headers={"Host": "attacker.example"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.auth_attempts.count_documents({}), 0)

    def test_public_admin_pages_require_session(self):
        for path in ("/", "/accounts", "/teams", "/areas", "/runs", "/audit"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], "/login")

    def test_login_requires_csrf_and_player_cannot_be_admin(self):
        response = self.client.post("/login", data={"username": "Operator", "password": self.password})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/login", data={"csrf_token": self.csrf(), "username": "PlayerOne", "password": self.password})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.db.auth_sessions.count_documents({"scope": "admin"}), 0)

    def test_login_cookie_and_security_headers(self):
        response = self.login_admin()
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("not yet call this service", response.get_data(as_text=True))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_cookie_is_revalidated_after_revocation(self):
        self.login_admin()
        self.auth.revoke_account_sessions(self.admin["_id"])
        self.assertEqual(self.client.get("/accounts").status_code, 302)

    def test_logout_is_post_and_revokes_session(self):
        self.login_admin()
        self.assertEqual(self.client.get("/logout").status_code, 405)
        response = self.client.post("/logout", data={"csrf_token": self.csrf("/")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.auth_sessions.count_documents({"account_id": self.admin["_id"], "revoked": False}), 0)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_admin_pages_never_render_password_or_session_hashes(self):
        self.login_admin()
        for path in ("/", "/accounts", "/accounts/" + self.player["_id"], "/teams", "/areas", "/runs", "/audit"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            text = response.get_data(as_text=True)
            self.assertNotIn(self.password_hash, text)
            self.assertNotIn(self.settings.bridge_secret, text)
            self.assertNotIn("password_hash", text)
        response = self.client.get("/static/admin.css")
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_area_creation_requires_csrf_and_is_audited(self):
        self.login_admin()
        self.assertEqual(self.client.post("/areas", data={"name": "Northern League"}).status_code, 400)
        response = self.client.post("/areas", data={"csrf_token": self.csrf("/areas"), "name": "Northern League"})
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.db.areas.find_one({"name": "Northern League"}))
        self.assertEqual(self.db.admin_audit.count_documents({"actor_id": self.admin["_id"]}), 1)

    def test_suspend_revokes_player_access_and_self_suspend_rejected(self):
        headers = self.player_headers()
        self.login_admin()
        response = self.client.post("/accounts/" + self.player["_id"] + "/status", data={
            "csrf_token": self.csrf("/accounts"), "status": "suspended", "reason": "Operator test"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/internal/v1/me", headers=headers).status_code, 401)
        response = self.client.post("/accounts/" + self.admin["_id"] + "/status", data={
            "csrf_token": self.csrf("/accounts"), "status": "suspended", "reason": "Cannot lock myself out"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.accounts.find_one({"_id": self.admin["_id"]})["status"], "active")

    def test_bridge_needs_bearer_even_with_player_token(self):
        headers = self.player_headers()
        response = self.client.get("/internal/v1/me", headers={"X-Player-Token": headers["X-Player-Token"]})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/internal/v1/me", headers=self.bridge).status_code, 401)
        response = self.client.get("/internal/v1/me", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["account"]["_id"], self.player["_id"])
        self.assertNotIn("password_hash", response.json["account"])

    def test_admin_session_is_rejected_by_player_interface(self):
        result = self.auth.authenticate("Operator", self.password, "admin")
        response = self.client.get("/internal/v1/me", headers={**self.bridge, "X-Player-Token": result["token"]})
        self.assertEqual(response.status_code, 401)

    def test_bridge_rejects_browser_origins_and_non_json(self):
        response = self.client.get("/internal/v1/health", headers={**self.bridge, "Origin": "http://localhost"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/internal/v1/login", headers=self.bridge, data="{}").status_code, 415)
        response = self.client.post("/internal/v1/login", headers=self.bridge, json=["not", "object"])
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/internal/v1/login", headers=self.bridge, json={"username": {"$ne": ""}, "password": self.password})
        self.assertEqual(response.status_code, 400)

    def test_bridge_health_reports_capability_without_claiming_native_runtime_probe(self):
        response = self.client.get("/internal/v1/health", headers=self.bridge)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertTrue(response.json["game_bridge_integrated"])
        self.assertEqual(response.json["health_scope"], "backend_only")
        self.assertFalse(response.json["native_runtime_checked"])
        self.assertEqual(response.json["implementation_release"], 1192615)

    def test_register_login_team_creation_and_logout(self):
        response = self.client.post("/internal/v1/register", headers=self.bridge, json={
            "username": "NewPlayer", "password": self.password, "starter_id": "spearman"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password_hash", response.json["account"])
        response = self.client.post("/internal/v1/login", headers=self.bridge, json={"username": "NewPlayer", "password": self.password})
        self.assertEqual(response.status_code, 200)
        headers = {**self.bridge, "X-Player-Token": response.json["token"]}
        response = self.client.post("/internal/v1/teams", headers=headers, json={"name": "Lantern Guard"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["team"]["name"], "Lantern Guard")
        response = self.client.get("/internal/v1/teams", headers=headers)
        self.assertEqual(len(response.json["teams"]), 1)
        self.assertEqual(self.client.post("/internal/v1/logout", headers=headers, json={}).status_code, 200)
        self.assertEqual(self.client.get("/internal/v1/me", headers=headers).status_code, 401)

    def test_bridge_rejects_client_supplied_rewards_and_identity(self):
        headers = self.player_headers()
        for body in ({"name": "Cheat", "experience": 99999}, {"name": "Cheat", "actor_id": self.admin["_id"]}):
            response = self.client.post("/internal/v1/teams", headers=headers, json=body)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.teams.count_documents({}), 0)

    def test_native_directory_create_read_and_recovery_contract(self):
        headers = self.player_headers()
        base = '/internal/v1/team-directory/'
        def post(operation, data):
            return self.client.post(base + operation, headers=headers, json=data)
        areas = post('areas', {'after': ''})
        self.assertEqual(areas.json, {'areas': [{'id': 'area-1', 'name': 'Area 1'}], 'next': ''})
        self.assertEqual(post('my_team', {}).json, {'team': None})
        response = post('create_team', {'name': ' Lantern Guard ', 'area_id': 'area-1'})
        self.assertEqual(response.status_code, 201)
        team = response.json['team']
        self.assertEqual(set(team), {'id', 'name', 'area_id', 'area_name', 'captain_id', 'level',
                                     'experience', 'rating', 'capacity', 'members'})
        self.assertEqual(team['name'], 'Lantern Guard')
        self.assertEqual(team['captain_id'], self.player['_id'])
        self.assertEqual(post('my_team', {}).json['team'], team)
        self.assertEqual(post('team_detail', {'team_id': team['id']}).json['team'], team)
        listing = post('teams', {'area_id': 'area-1', 'after': ''})
        self.assertEqual(listing.json['teams'][0]['member_count'], 1)
        self.assertNotIn('members', listing.json['teams'][0])
        self.assertNotIn('join_requests', str(listing.json))
        self.assertNotIn(self.password_hash, str(response.json))
        repeat = post('create_team', {'name': 'New Name', 'area_id': 'area-1'})
        self.assertEqual(repeat.status_code, 409)
        self.assertEqual(repeat.json['error']['code'], 'already_member')
        self.assertEqual(self.db.teams.count_documents({}), 1)

    def test_native_membership_cycle_scopes_projection_and_recovery(self):
        captain = self.domain.register('CaptainOne', self.password_hash)
        other = self.domain.register('OtherPlayer', self.password_hash)
        team = self.domain.create_team(captain['_id'], 'Application Team')['_id']
        player_headers = self.player_headers()
        captain_headers = {**self.bridge, 'X-Player-Token': self.auth.authenticate(
            'CaptainOne', self.password, 'player')['token']}
        other_headers = {**self.bridge, 'X-Player-Token': self.auth.authenticate(
            'OtherPlayer', self.password, 'player')['token']}
        def post(operation, data, headers=player_headers):
            return self.client.post('/internal/v1/team-directory/' + operation, headers=headers, json=data)
        apply = post('apply_team', {'team_id': team})
        expected = {'team_id': team, 'account_id': self.player['_id'], 'status': 'applied'}
        self.assertEqual(apply.status_code, 200)
        self.assertEqual(apply.json, expected)
        self.assertEqual(post('apply_team', {'team_id': team}).json, expected)
        self.assertEqual(post('my_applications', {'after': ''}).json['teams'][0]['id'], team)
        self.assertEqual(post('my_applications', {'after': ''}, other_headers).json['teams'], [])
        for headers in (player_headers, other_headers):
            self.assertEqual(post('team_applicants', {'team_id': team, 'after': ''}, headers).status_code, 403)
            self.assertEqual(post('approve_application', {'team_id': team, 'account_id': self.player['_id']}, headers).status_code, 403)
            self.assertEqual(post('reject_application', {'team_id': team, 'account_id': self.player['_id']}, headers).status_code, 403)
            self.assertEqual(post('my_applications', {'after': ''}, headers).status_code, 200)
        applicants = post('team_applicants', {'team_id': team, 'after': ''}, captain_headers)
        self.assertEqual(applicants.json, {'team_id': team, 'next': '', 'applicants': [{
            'id': self.player['_id'], 'username': 'PlayerOne', 'unit_type': 'Spearman', 'level': 1}]})
        self.assertNotIn(self.password_hash, str(applicants.json))
        # Withdrawal, rejection, and reapplication have distinct acknowledgements.
        self.assertEqual(post('withdraw_application', {'team_id': team}).json,
                         {**expected, 'status': 'withdrawn'})
        post('apply_team', {'team_id': team})
        self.assertEqual(post('reject_application', {'team_id': team, 'account_id': self.player['_id']},
                              captain_headers).json, {**expected, 'status': 'rejected'})
        self.assertEqual(post('my_applications', {'after': ''}).json['teams'], [])
        missing = post('approve_application', {'team_id': team, 'account_id': self.player['_id']}, captain_headers)
        self.assertEqual(missing.status_code, 409)
        self.assertEqual(missing.json['error']['code'], 'not_requested')
        post('apply_team', {'team_id': team})
        approved = post('approve_application', {'team_id': team, 'account_id': self.player['_id']}, captain_headers)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json, {**expected, 'status': 'approved'})
        # Read-only reconciliation after a lost acknowledgement finds the committed roster.
        self.assertEqual(post('my_team', {}).json['team']['id'], team)
        self.assertEqual(post('team_applicants', {'team_id': team, 'after': ''}, captain_headers).json['applicants'], [])
        self.assertEqual(len(post('team_detail', {'team_id': team}).json['team']['members']), 2)
        self.assertEqual(self.domain.get_account(self.player['_id'])['leader']['total_experience'], 0)
        self.assertEqual(self.domain._team(team)['experience'], 0)

    def test_native_application_decisions_are_owner_only_and_explicitly_acknowledged(self):
        captain = self.domain.register('DecisionCaptain', self.password_hash)
        team = self.domain.create_team(captain['_id'], 'Decision Team')['_id']
        headers = self.player_headers()
        captain_headers = {**self.bridge, 'X-Player-Token': self.auth.authenticate(
            'DecisionCaptain', self.password, 'player')['token']}
        base = '/internal/v1/team-directory/'
        def post(operation, data, supplied=headers):
            return self.client.post(base + operation, headers=supplied, json=data)
        self.assertEqual(post('application_decisions', {}).json, {'decisions': []})
        post('apply_team', {'team_id': team})
        self.assertEqual(post('reject_application', {'team_id': team, 'account_id': self.player['_id']},
                              captain_headers).status_code, 200)
        response = post('application_decisions', {})
        self.assertEqual(response.status_code, 200)
        notice = response.json['decisions'][0]
        self.assertEqual(set(notice), {'id', 'team_id', 'team_name', 'status', 'created_at', 'unread'})
        self.assertEqual(notice['status'], 'rejected')
        self.assertTrue(notice['unread'])
        self.assertEqual(post('application_decisions', {}).json, response.json)
        self.assertEqual(post('application_decisions', {}, captain_headers).json, {'decisions': []})
        denied = post('ack_decision', {'decision_id': notice['id']}, captain_headers)
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.json['error']['code'], 'not_found')
        self.assertTrue(post('application_decisions', {}).json['decisions'][0]['unread'])
        for _ in range(2):
            marked = post('ack_decision', {'decision_id': notice['id']})
            self.assertEqual(marked.status_code, 200)
            self.assertEqual(marked.json, {'decision_id': notice['id'], 'status': 'read'})
        self.assertFalse(post('application_decisions', {}).json['decisions'][0]['unread'])
        post('apply_team', {'team_id': team})
        post('approve_application', {'team_id': team, 'account_id': self.player['_id']}, captain_headers)
        decisions = post('application_decisions', {}).json['decisions']
        self.assertEqual([item['status'] for item in decisions], ['approved', 'rejected'])
        self.assertEqual([item['unread'] for item in decisions], [True, False])
        self.assertNotIn('application_decisions', self.client.get('/internal/v1/me', headers=headers).json['account'])
        login = self.client.post('/internal/v1/login', headers=self.bridge,
                                 json={'username': 'PlayerOne', 'password': self.password})
        self.assertEqual(login.status_code, 200)
        self.assertNotIn('application_decisions', login.json['account'])
        self.assertNotIn(self.password_hash, str(decisions))
        self.auth.revoke_token(headers['X-Player-Token'])
        self.assertEqual(post('application_decisions', {}).status_code, 401)
        self.assertEqual(post('ack_decision', {'decision_id': decisions[0]['id']}).status_code, 401)
        self.assertTrue(self.domain.directory_application_decisions(self.player['_id'])['decisions'][0]['unread'])

    def test_native_management_authorization_stale_selection_and_archive_contract(self):
        base = '/internal/v1/team-directory/'
        captain = self.domain.register('ManageCaptain', self.password_hash)
        stranger = self.domain.register('ManageStranger', self.password_hash)
        team = self.domain.create_team(captain['_id'], 'Managed Team')['_id']
        self.domain.request_join(self.player['_id'], team)
        self.domain.approve_member(captain['_id'], team, self.player['_id'])
        player_headers = self.player_headers()
        captain_headers = {**self.bridge, 'X-Player-Token': self.auth.authenticate(
            'ManageCaptain', self.password, 'player')['token']}
        def post(operation, body, headers=captain_headers):
            return self.client.post(base + operation, json=body, headers=headers)
        blocked = post('leave_team', {'team_id': team, 'allow_archive': False})
        self.assertEqual((blocked.status_code, blocked.json['error']['code']), (409, 'captain_transfer_required'))
        self.assertEqual(post('transfer_captain', {'team_id': team, 'account_id': captain['_id']},
                              player_headers).status_code, 403)
        nonmember = post('transfer_captain', {'team_id': team, 'account_id': stranger['_id']})
        self.assertEqual((nonmember.status_code, nonmember.json['error']['code']), (409, 'not_member'))
        transfer = post('transfer_captain', {'team_id': team, 'account_id': self.player['_id']})
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(transfer.json, {'team_id': team, 'account_id': self.player['_id'], 'status': 'transferred'})
        self.assertEqual(post('transfer_captain', {'team_id': team, 'account_id': captain['_id']}).status_code, 403)
        stale = post('leave_team', {'team_id': str(uuid4()), 'allow_archive': False})
        self.assertEqual((stale.status_code, stale.json['error']['code']), (409, 'conflict'))
        left = post('leave_team', {'team_id': team, 'allow_archive': False})
        self.assertEqual(left.status_code, 200)
        self.assertEqual(left.json, {'team_id': team, 'account_id': captain['_id'], 'status': 'left', 'archived': False})
        standings = post('standings', {'area_id': 'area-1'})
        self.assertEqual(standings.status_code, 200)
        self.assertEqual(set(standings.json), {'area_id', 'teams', 'has_more'})
        self.assertEqual(standings.json['area_id'], 'area-1')
        self.assertEqual(standings.json['teams'][0]['member_count'], 1)
        self.assertFalse(standings.json['has_more'])
        self.assertNotIn('join_requests', str(standings.json))
        self.assertNotIn('password_hash', str(standings.json))
        unconfirmed = post('leave_team', {'team_id': team, 'allow_archive': False}, player_headers)
        self.assertEqual((unconfirmed.status_code, unconfirmed.json['error']['code']), (409, 'conflict'))
        archived = post('leave_team', {'team_id': team, 'allow_archive': True}, player_headers)
        self.assertEqual(archived.json, {'team_id': team, 'account_id': self.player['_id'], 'status': 'left', 'archived': True})
        self.assertEqual(post('standings', {'area_id': 'area-1'}).json,
                         {'area_id': 'area-1', 'teams': [], 'has_more': False})
        self.assertEqual(self.domain.get_account(self.player['_id'])['leader']['total_experience'], 0)

    def test_native_management_busy_and_suspended_target_leave_membership_unchanged(self):
        captain = self.player['_id']
        member = self.domain.register('ManageTarget', self.password_hash)['_id']
        team = self.domain.create_team(captain, 'Busy Management')['_id']
        self.domain.request_join(member, team)
        self.domain.approve_member(captain, team, member)
        headers = self.player_headers()
        base = '/internal/v1/team-directory/'
        before = self.domain._team(team)
        for collection, identifier in ((self.db.accounts, captain), (self.db.accounts, member), (self.db.teams, team)):
            collection.update_one({'_id': identifier}, {'$set': {'active_run_id': str(uuid4())}})
            response = self.client.post(base + 'transfer_captain', headers=headers,
                                        json={'team_id': team, 'account_id': member})
            self.assertEqual((response.status_code, response.json['error']['code']), (409, 'busy'))
            collection.update_one({'_id': identifier}, {'$set': {'active_run_id': None}})
        self.db.accounts.update_one({'_id': member}, {'$set': {'status': 'suspended'}})
        suspended = self.client.post(base + 'transfer_captain', headers=headers,
                                    json={'team_id': team, 'account_id': member})
        self.assertEqual((suspended.status_code, suspended.json['error']['code']), (403, 'forbidden'))
        self.assertEqual(self.domain._team(team), before)

    def planning_fixture(self):
        players = [self.player] + [self.domain.register(name, self.password_hash)
                                  for name in ('PlanMember', 'PlanCaptain', 'PlanOpponent')]
        headers = [{**self.bridge, 'X-Player-Token': self.auth.authenticate(
            actor['username'], self.password, 'player')['token']} for actor in players]
        teams = []
        for index in (0, 2):
            team = self.domain.create_team(players[index]['_id'], 'Plan Team ' + str(index))['_id']
            self.domain.request_join(players[index+1]['_id'], team)
            self.domain.approve_member(players[index]['_id'], team, players[index+1]['_id'])
            teams.append(team)
        body = {'team_id': teams[0], 'opponent_team_id': teams[1], 'map_id': 'isars-cross',
            'lineups': [{'team_id': team, 'account_ids': [actor['_id'] for actor in players[index:index+2]]}
                       for team, index in zip(teams, (0, 2))]}
        return players, headers, teams, body

    def test_native_battle_planning_explicit_consent_and_cancel_without_gameplay(self):
        players, headers, teams, body = self.planning_fixture()
        base = '/internal/v1/team-directory/'
        def post(operation, data, actor=0):
            return self.client.post(base + operation, headers=headers[actor], json=data)
        maps = post('battle_maps', {'area_id': 'area-1'})
        self.assertEqual(maps.status_code, 200)
        self.assertEqual([item['size'] for item in maps.json['maps']], [2, 3, 4])
        created = post('propose_battle', body)
        self.assertEqual(created.status_code, 201)
        battle = created.json['battle']
        selector = {'battle_id': battle['id']}
        self.assertEqual([team['approved'] for team in battle['teams']], [False, False])
        self.assertEqual(post('my_battles', {'after': ''}, 1).json['battles'][0]['id'], battle['id'])
        self.assertEqual(post('battle_detail', selector, 3).json, created.json)
        early = post('battle_ready', {**selector, 'ready': True}, 1)
        self.assertEqual((early.status_code, early.json['error']['code']), (409, 'approval_required'))
        self.assertEqual(post('approve_battle', selector, 1).status_code, 403)
        self.assertEqual(post('cancel_battle', selector, 1).status_code, 403)
        self.assertEqual(post('approve_battle', selector, 0).status_code, 200)
        self.assertEqual(post('approve_battle', selector, 2).status_code, 200)
        for index in range(4):
            ready = post('battle_ready', {**selector, 'ready': True}, index)
            self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json['battle']['state'], 'draft')
        self.assertTrue(all(player['ready'] for team in ready.json['battle']['teams'] for player in team['players']))
        self.assertEqual(post('battle_ready', {**selector, 'ready': False}, 1).status_code, 200)
        self.assertEqual(post('start_battle', selector).status_code, 404)
        for player in players:
            self.assertIsNone(self.domain.get_account(player['_id'])['active_run_id'])
            self.assertEqual(self.domain.get_account(player['_id'])['leader']['total_experience'], 0)
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        cancelled = post('cancel_battle', selector, 2)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json['battle']['state'], 'cancelled')
        self.assertEqual(post('cancel_battle', selector, 2).json, cancelled.json)
        self.assertEqual(post('battle_ready', {**selector, 'ready': True}, 1).status_code, 409)

    def test_native_battle_planning_hides_former_members_and_cancels_stale(self):
        players, headers, teams, body = self.planning_fixture()
        base = '/internal/v1/team-directory/'
        created = self.client.post(base + 'propose_battle', headers=headers[0], json=body)
        selector = {'battle_id': created.json['battle']['id']}
        self.domain.leave_team(players[1]['_id'])
        for operation, data in (('battle_detail', selector), ('approve_battle', selector),
                                ('battle_ready', {**selector, 'ready': False}), ('cancel_battle', selector)):
            self.assertEqual(self.client.post(base + operation, headers=headers[1], json=data).status_code, 403)
        self.assertEqual(self.client.post(base + 'my_battles', headers=headers[1], json={'after': ''}).json,
                         {'battles': [], 'next': ''})
        detail = self.client.post(base + 'battle_detail', headers=headers[2], json=selector)
        self.assertEqual(detail.json['battle']['validity'], 'roster_changed')
        self.assertEqual(self.client.post(base + 'approve_battle', headers=headers[2], json=selector).status_code, 409)
        cancelled = self.client.post(base + 'cancel_battle', headers=headers[0], json=selector)
        self.assertEqual(cancelled.json['battle']['state'], 'cancelled')
        self.assertNotIn('password_hash', str(cancelled.json))
        self.assertNotIn('cancel_reason', str(cancelled.json))

    def test_native_battle_planning_strict_inputs_reject_identity_and_rewards(self):
        players, headers, teams, body = self.planning_fixture()
        base = '/internal/v1/team-directory/'
        cases = [('propose_battle', {**body, 'actor_id': players[1]['_id']}),
                 ('propose_battle', {**body, 'experience': 20}),
                 ('propose_battle', {**body, 'lineups': {'team': []}}),
                 ('battle_maps', {'area_id': {'$ne': ''}}), ('my_battles', {'after': 'bad'}),
                 ('battle_detail', {'battle_id': {'$ne': ''}}),
                 ('approve_battle', {'battle_id': str(uuid4()), 'account_id': players[1]['_id']}),
                 ('battle_ready', {'battle_id': str(uuid4()), 'ready': 1}),
                 ('battle_ready', {'battle_id': str(uuid4()), 'ready': 'false'}),
                 ('cancel_battle', {'battle_id': str(uuid4()), 'reason': 'caller detail'})]
        for operation, data in cases:
            with self.subTest(operation=operation, data=data):
                self.assertIn(self.client.post(base + operation, headers=headers[0], json=data).status_code, (400, 409))
        self.assertEqual(self.client.post(base + 'propose_battle?extra=1', headers=headers[0], json=body).status_code, 400)
        self.assertEqual(self.client.get(base + 'battle_maps', headers=headers[0]).status_code, 405)
        self.assertEqual(self.db.game_runs.count_documents({}), 0)

    def test_native_directory_rejects_extra_identity_rewards_selectors_and_query(self):
        headers = self.player_headers()
        base = '/internal/v1/team-directory/'
        for operation, data in (
            ('areas', {}), ('areas', {'after': {'$ne': ''}}), ('areas', {'after': '', 'limit': 1000}),
            ('teams', {'area_id': {'$ne': ''}, 'after': ''}),
            ('teams', {'area_id': 'area-1', 'after': 'not-a-uuid'}),
            ('my_team', {'actor_id': self.admin['_id']}),
            ('team_detail', {'team_id': 'not-a-uuid'}),
            ('create_team', {'name': 'Bad<Name', 'area_id': 'area-1'}),
            ('create_team', {'name': 'Good Name', 'area_id': 'area-1', 'experience': 99}),
            ('create_team', {'name': 'Good Name', 'area_id': 'area-1', 'captain_id': self.admin['_id']}),
            ('my_applications', {'after': {'$gt': ''}}),
            ('team_applicants', {'team_id': self.player['_id'], 'after': '', 'limit': 1000}),
            ('apply_team', {'team_id': self.player['_id'], 'account_id': self.admin['_id']}),
            ('withdraw_application', {'team_id': self.player['_id'], 'account_id': self.admin['_id']}),
            ('approve_application', {'team_id': self.player['_id']}),
            ('reject_application', {'team_id': self.player['_id'], 'account_id': {'$ne': ''}}),
            ('application_decisions', {'account_id': self.admin['_id']}),
            ('application_decisions', {'after': ''}),
            ('ack_decision', {'decision_id': {'$ne': ''}}),
            ('leave_team', {'team_id': self.player['_id'], 'account_id': self.admin['_id']}),
            ('leave_team', {'team_id': {'$ne': ''}}),
            ('leave_team', {'team_id': self.player['_id']}),
            ('leave_team', {'team_id': self.player['_id'], 'allow_archive': 1}),
            ('leave_team', {'team_id': self.player['_id'], 'allow_archive': 'false'}),
            ('transfer_captain', {'team_id': self.player['_id']}),
            ('transfer_captain', {'team_id': self.player['_id'], 'account_id': {'$ne': ''}}),
            ('standings', {'area_id': {'$ne': ''}}),
            ('standings', {'area_id': 'area-1', 'after': ''}),
            ('ack_decision', {'decision_id': self.player['_id'], 'account_id': self.admin['_id']})):
            with self.subTest(operation=operation, data=data):
                response = self.client.post(base + operation, headers=headers, json=data)
                self.assertIn(response.status_code, (400, 409))
        self.assertEqual(self.client.post(base + 'areas?after=ignored', headers=headers,
                                         json={'after': ''}).status_code, 400)
        self.assertEqual(self.client.get(base + 'areas', headers=headers).status_code, 405)
        self.assertEqual(self.db.teams.count_documents({}), 0)

    def test_native_directory_requires_live_player_scope_on_every_operation(self):
        base = '/internal/v1/team-directory/'
        operations = {'areas': {'after': ''}, 'teams': {'area_id': 'area-1', 'after': ''},
            'my_team': {}, 'create_team': {'name': 'Forbidden Team', 'area_id': 'area-1'},
            'team_detail': {'team_id': '12345678-1234-1234-1234-123456789abc'},
            'my_applications': {'after': ''},
            'team_applicants': {'team_id': self.player['_id'], 'after': ''},
            'apply_team': {'team_id': self.player['_id']},
            'withdraw_application': {'team_id': self.player['_id']},
            'approve_application': {'team_id': self.player['_id'], 'account_id': self.player['_id']},
            'reject_application': {'team_id': self.player['_id'], 'account_id': self.player['_id']},
            'application_decisions': {}, 'ack_decision': {'decision_id': self.player['_id']},
            'leave_team': {'team_id': self.player['_id'], 'allow_archive': False},
            'transfer_captain': {'team_id': self.player['_id'], 'account_id': self.player['_id']},
            'standings': {'area_id': 'area-1'}}
        operations.update({'battle_maps': {'area_id': 'area-1'}, 'my_battles': {'after': ''},
            'battle_detail': {'battle_id': self.player['_id']},
            'propose_battle': {'team_id': self.player['_id'], 'opponent_team_id': self.admin['_id'],
                               'map_id': 'isars-cross', 'lineups': []},
            'approve_battle': {'battle_id': self.player['_id']},
            'battle_ready': {'battle_id': self.player['_id'], 'ready': True},
            'cancel_battle': {'battle_id': self.player['_id']}})
        headers = self.player_headers()
        admin = self.auth.authenticate('Operator', self.password, 'admin')
        wrong_scope = {**self.bridge, 'X-Player-Token': admin['token']}
        for operation, data in operations.items():
            for supplied in (self.bridge, wrong_scope, {'X-Player-Token': headers['X-Player-Token']}):
                self.assertEqual(self.client.post(base + operation, headers=supplied, json=data).status_code, 401)
        for mode in ('expired', 'revoked', 'suspended'):
            headers = self.player_headers()
            if mode == 'expired':
                self.db.auth_sessions.update_many({'account_id': self.player['_id']},
                    {'$set': {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
            elif mode == 'revoked':
                self.auth.revoke_token(headers['X-Player-Token'])
            else:
                self.db.accounts.update_one({'_id': self.player['_id']}, {'$set': {'status': 'suspended'}})
            for operation, data in operations.items():
                with self.subTest(mode=mode, operation=operation):
                    self.assertEqual(self.client.post(base + operation, headers=headers, json=data).status_code, 401)
        self.assertEqual(self.db.teams.count_documents({}), 0)

    def test_campaign_settlement_is_server_only_and_idempotent(self):
        headers = self.player_headers()
        response = self.client.post("/internal/v1/campaigns/start", headers=headers,
            json={"mission_id": "alliance_training_1"})
        self.assertEqual(response.status_code, 201)
        run_id = response.json["run"]["_id"]
        response = self.client.get("/internal/v1/runs/" + run_id, headers=headers)
        self.assertEqual(response.status_code, 200)
        url = "/internal/v1/server/campaigns/" + run_id + "/finish"
        self.assertEqual(self.client.post(url, headers={"X-Player-Token": headers["X-Player-Token"]},
                                         json={"outcome": "win"}).status_code, 401)
        self.assertEqual(self.client.post(url, headers=self.bridge,
                                         json={"outcome": "win", "experience": 5000}).status_code, 400)
        first = self.client.post(url, headers=self.bridge, json={"outcome": "win"})
        self.assertEqual(first.status_code, 200)
        retry = self.client.post(url, headers=self.bridge, json={"outcome": "win"})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.json, retry.json)
        conflict = self.client.post(url, headers=self.bridge, json={"outcome": "loss"})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json["error"]["code"], "result_conflict")
        account = self.domain.get_account(self.player["_id"])
        self.assertEqual(account["leader"]["total_experience"], 20)
        self.assertIsNone(account["active_run_id"])
        self.assertEqual(self.db.settlements.count_documents({"_id": run_id}), 1)

    def test_unrelated_player_cannot_read_run_and_admin_can_cancel(self):
        self.domain.register("OtherPlayer", self.password_hash)
        result = self.auth.authenticate("OtherPlayer", self.password, "player")
        other_headers = {**self.bridge, "X-Player-Token": result["token"]}
        run = self.domain.start_campaign(self.player["_id"], "alliance_training_1")
        self.assertEqual(self.client.get("/internal/v1/runs/" + run["_id"], headers=other_headers).status_code, 403)
        self.login_admin()
        response = self.client.get("/runs/" + run["_id"])
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/runs/" + run["_id"] + "/cancel", data={
            "csrf_token": self.csrf("/runs"), "reason": "Interrupted game during test"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.domain.get_run(run["_id"])["state"], "cancelled")
        self.assertIsNone(self.domain.get_account(self.player["_id"])["active_run_id"])
        self.assertEqual(self.domain.get_account(self.player["_id"])["leader"]["total_experience"], 0)
        response = self.client.post("/internal/v1/server/campaigns/" + run["_id"] + "/finish",
                                   headers=self.bridge, json={"outcome": "win"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.settlements.count_documents({"_id": run["_id"]}), 0)

    def test_area_move_and_player_membership_permissions(self):
        team = self.domain.create_team(self.player["_id"], "Border Guard")
        self.login_admin()
        area = self.domain.admin_create_area(self.admin["_id"], "West")
        response = self.client.post("/teams/" + team["_id"] + "/area", data={
            "csrf_token": self.csrf("/teams"), "area_id": area["_id"], "reason": "Balance area membership"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.teams.find_one({"_id": team["_id"]})["area_id"], area["_id"])
        other = self.domain.register("Applicant", self.password_hash)
        login = self.auth.authenticate("Applicant", self.password, "player")
        applicant_headers = {**self.bridge, "X-Player-Token": login["token"]}
        self.assertEqual(self.client.post("/internal/v1/teams/" + team["_id"] + "/join",
                                        headers=applicant_headers, json={}).status_code, 200)
        self.assertEqual(self.client.post("/internal/v1/teams/" + team["_id"] + "/approve",
                                        headers=applicant_headers, json={"account_id": other["_id"]}).status_code, 403)
        response = self.client.post("/internal/v1/teams/" + team["_id"] + "/approve",
                                   headers=self.player_headers(), json={"account_id": other["_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["team"]["members"]), 2)

    def test_team_detail_hides_applicants_except_from_current_captain(self):
        team = self.domain.create_team(self.player["_id"], "Lantern Watch")
        applicant = self.domain.register("Applicant", self.password_hash)
        self.domain.request_join(applicant["_id"], team["_id"])
        login = self.auth.authenticate("Applicant", self.password, "player")
        headers = {**self.bridge, "X-Player-Token": login["token"]}
        path = "/internal/v1/teams/" + team["_id"]
        response = self.client.get(path, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("join_requests", response.json["team"])
        self.assertNotIn("applicants", response.json["team"])
        self.assertEqual(response.json["team"]["members"][0]["username"], "PlayerOne")
        self.assertEqual(response.json["team"]["members"][0]["leader"]["unit_type"], "Spearman")
        response = self.client.get(path, headers=self.player_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["team"]["join_requests"], [applicant["_id"]])
        self.assertEqual(response.json["team"]["applicants"][0]["username"], "Applicant")
        self.assertNotIn("password_hash", response.get_data(as_text=True))
        self.assertNotIn(self.password_hash, response.get_data(as_text=True))
        self.assertEqual(self.client.get(path, headers=self.bridge).status_code, 401)

    def test_captain_reject_and_applicant_withdraw_leave_roster_unchanged(self):
        team = self.domain.create_team(self.player["_id"], "Lantern Watch")
        applicant = self.domain.register("Applicant", self.password_hash)
        login = self.auth.authenticate("Applicant", self.password, "player")
        headers = {**self.bridge, "X-Player-Token": login["token"]}
        base = "/internal/v1/teams/" + team["_id"]
        self.assertEqual(self.client.post(base + "/join", headers=headers, json={}).status_code, 200)
        self.assertEqual(self.client.post(base + "/reject", headers=headers,
                                        json={"account_id": applicant["_id"]}).status_code, 403)
        captain_headers = self.player_headers()
        for _ in range(2):
            response = self.client.post(base + "/reject", headers=captain_headers,
                                       json={"account_id": applicant["_id"]})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["team"]["requested"])
        self.assertEqual(self.client.post(base + "/join", headers=headers, json={}).status_code, 200)
        response = self.client.post(base + "/withdraw", headers=headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["team"]["requested"])
        current = self.db.teams.find_one({"_id": team["_id"]})
        self.assertEqual(current["join_requests"], [])
        self.assertEqual([m["account_id"] for m in current["members"]], [self.player["_id"]])

    def test_unauthenticated_result_routes_reveal_no_existing_run(self):
        run = self.domain.start_campaign(self.player["_id"], "alliance_training_1")
        paths = ["/internal/v1/server/campaigns/" + run["_id"] + "/finish",
                 "/internal/v1/server/campaigns/does-not-exist/finish"]
        responses = [self.client.post(path, json={"outcome": "win"}) for path in paths]
        self.assertEqual([r.status_code for r in responses], [401, 401])
        self.assertEqual(responses[0].json, responses[1].json)
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        response = self.client.open(paths[0], method="OPTIONS")
        self.assertEqual(response.status_code, 405)

    def test_forged_forwarding_headers_cannot_bypass_loopback(self):
        response = self.client.get("/internal/v1/health", headers={**self.bridge,
            "X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost"},
            environ_overrides={"REMOTE_ADDR": "192.168.1.10"})
        self.assertEqual(response.status_code, 403)

    def test_changed_leader_snapshot_blocks_settlement_without_partial_rewards(self):
        run = self.domain.start_campaign(self.player["_id"], "alliance_training_1")
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"leader.experience": 1}})
        response = self.client.post("/internal/v1/server/campaigns/" + run["_id"] + "/finish",
                                   headers=self.bridge, json={"outcome": "win"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"]["code"], "snapshot_conflict")
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        self.assertEqual(self.domain.get_account(self.player["_id"])["leader"]["total_experience"], 0)
        self.assertEqual(self.domain.get_account(self.player["_id"])["active_run_id"], run["_id"])

    def test_oversized_requests_rejected(self):
        response = self.client.post("/internal/v1/login", headers=self.bridge, json={"username": "x" * 33000})
        self.assertEqual(response.status_code, 413)

    def test_unknown_failure_hides_sensitive_exception_text(self):
        with patch.object(type(self.db), "command", side_effect=RuntimeError("mongodb://secret:password@host")):
            with self.assertLogs(self.app.logger, level="ERROR") as captured:
                response = self.client.get("/internal/v1/health", headers=self.bridge)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.get_data(as_text=True))
        self.assertNotIn("mongodb", " ".join(captured.output))


if __name__ == "__main__":
    unittest.main()
