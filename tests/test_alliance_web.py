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

    def test_bridge_health_reports_unintegrated_game_explicitly(self):
        response = self.client.get("/internal/v1/health", headers=self.bridge)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertFalse(response.json["game_bridge_integrated"])

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
            ('create_team', {'name': 'Good Name', 'area_id': 'area-1', 'captain_id': self.admin['_id']})):
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
            'team_detail': {'team_id': '12345678-1234-1234-1234-123456789abc'}}
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
