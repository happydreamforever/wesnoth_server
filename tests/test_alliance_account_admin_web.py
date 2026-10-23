"""Account edit/reset HTTP tests using an isolated real MongoDB replica set."""
import os
import io
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from pymongo import MongoClient
from werkzeug.datastructures import MultiDict

from alliance.auth import AuthError, AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService
from alliance.schema import bootstrap_schema
from alliance.web import create_app


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGO_URI"), "Requires an isolated loopback replica set.")
class AccountAdminWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ["ALLIANCE_TEST_MONGO_URI"]
        if urlsplit(uri).scheme != "mongodb" or urlsplit(uri).hostname != "127.0.0.1":
            raise RuntimeError("Only an isolated loopback MongoDB may run these tests.")
        cls.mongo = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        cls.database_name = "alliance_test_admin_web_" + uuid4().hex
        cls.db = cls.mongo[cls.database_name]
        bootstrap_schema(cls.db)
        bootstrap_auth_schema(cls.db)
        cls.password = "Original-dummy-password-123"
        cls.password_hash = hash_password(cls.password)
        cls.settings = SimpleNamespace(host="127.0.0.1", port=18765,
            secret_key="cookie-test-" + uuid4().hex, bridge_secret="bridge-test-" + uuid4().hex)

    @classmethod
    def tearDownClass(cls):
        cls.mongo.drop_database(cls.database_name)
        cls.mongo.close()

    def setUp(self):
        for name in ("accounts", "teams", "game_runs", "settlements", "admin_audit", "auth_sessions", "auth_attempts"):
            self.db[name].delete_many({})
        self.domain = AllianceService(self.db)
        self.admin = self.domain.register("Operator", self.password_hash)
        self.db.accounts.update_one({"_id": self.admin["_id"]}, {"$set": {"role": "admin"}})
        self.player = self.domain.register("PlayerOne", self.password_hash)
        self.auth = AuthService(self.db)
        self.app = create_app(self.settings, self.db)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.edit = "/accounts/" + self.player["_id"] + "/edit"
        self.reset = "/accounts/" + self.player["_id"] + "/password"

    def token(self, path="/login"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)).group(1)

    def login(self):
        response = self.client.post("/login", data={"csrf_token": self.token(), "username": "Operator", "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def edit_form(self, **changes):
        result = {"csrf_token": self.token(self.edit), "revision": str(self.domain.get_account(self.player["_id"])["revision"]),
                  "username": "PlayerOne", "status": "active", "reason": "Correct the account record"}
        result.update(changes)
        return result

    def reset_form(self, **changes):
        result = {"csrf_token": self.token(self.reset), "revision": str(self.domain.get_account(self.player["_id"])["revision"]),
                  "password": "New-dummy-password-456", "confirmation": "New-dummy-password-456", "reason": "Player requested recovery"}
        result.update(changes)
        return result

    def snapshot(self):
        return {name: list(self.db[name].find({}).sort("_id", 1)) for name in
                ("accounts", "teams", "game_runs", "settlements", "admin_audit", "auth_sessions", "auth_attempts")}

    def assert_blank_passwords(self, response):
        text = response.get_data(as_text=True)
        tags = re.findall(r'<input\b[^>]*type="password"[^>]*>', text)
        self.assertEqual(len(tags), 2)
        for tag in tags:
            self.assertNotRegex(tag, r'\bvalue=')
            self.assertIn('autocomplete="new-password"', tag)
            self.assertIn('spellcheck="false"', tag)
        return text

    def test_links_and_get_pages_are_read_only_and_secret_free(self):
        self.login()
        before = self.snapshot()
        for path in ("/accounts", "/accounts/" + self.player["_id"], self.edit, self.reset):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertNotIn(self.password_hash, text)
            self.assertNotIn(self.settings.bridge_secret, text)
            self.assertNotIn("password_hash", text)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            if path in ("/accounts", "/accounts/" + self.player["_id"]):
                self.assertIn(self.edit, text)
                self.assertIn(self.reset, text)
        self.assert_blank_passwords(self.client.get(self.reset))
        self.assertEqual(before, self.snapshot())

    def test_forms_require_admin_login(self):
        for path in (self.edit, self.reset):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/login")
        token = self.auth.authenticate("PlayerOne", self.password, "player")["token"]
        with self.client.session_transaction() as value:
            value["admin_token"] = token
        self.assertEqual(self.client.get(self.edit).headers["Location"], "/login")

    def test_posts_require_csrf_and_loopback(self):
        self.login()
        for path, form in ((self.edit, self.edit_form()), (self.reset, self.reset_form())):
            before = self.snapshot()
            missing = dict(form)
            missing.pop("csrf_token")
            self.assertEqual(self.client.post(path, data=missing).status_code, 400)
            response = self.client.post(path, data=form, environ_overrides={"REMOTE_ADDR": "192.168.1.2"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(before, self.snapshot())

    def test_rename_and_suspend_preserve_identity_progress_and_team(self):
        team = self.domain.create_team(self.player["_id"], "Saved team", "area-1")
        saved_team = self.db.teams.find_one({"_id": team["_id"]})
        player_token = self.auth.authenticate("PlayerOne", self.password, "player")["token"]
        original = self.domain.get_account(self.player["_id"])
        self.login()
        response = self.client.post(self.edit, data=self.edit_form(username="RenamedPlayer", status="suspended"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/accounts/" + self.player["_id"])
        changed = self.domain.get_account(self.player["_id"])
        self.assertEqual(changed["username"], "RenamedPlayer")
        self.assertEqual(changed["status"], "suspended")
        for key in ("_id", "role", "heroes", "training_completed", "database_generation", "active_run_id"):
            self.assertEqual(changed[key], original[key])
        self.assertEqual(self.db.teams.find_one({"_id": team["_id"]}), saved_team)
        self.assertEqual(self.db.accounts.find_one({"_id": self.player["_id"]})["password_hash"], self.password_hash)
        with self.assertRaises(AuthError):
            self.auth.validate_token(player_token, "player")

    def test_unchanged_edit_audits_without_revoking_sessions(self):
        token = self.auth.authenticate("PlayerOne", self.password, "player")["token"]
        self.login()
        form = self.edit_form()
        self.assertEqual(self.client.post(self.edit, data=form).status_code, 302)
        self.assertEqual(self.auth.validate_token(token, "player")["_id"], self.player["_id"])
        self.assertEqual(self.db.admin_audit.count_documents({"target_id": self.player["_id"]}), 1)
        self.assertEqual(self.client.post(self.edit, data=form).status_code, 409)

    def test_own_username_change_clears_browser_session(self):
        self.login()
        path = "/accounts/" + self.admin["_id"] + "/edit"
        form = {"csrf_token": self.token(path), "revision": str(self.domain.get_account(self.admin["_id"])["revision"]),
                "username": "OperatorNew", "status": "active", "reason": "Rename operator"}
        response = self.client.post(path, data=form)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_token", session)
        self.assertEqual(self.auth.authenticate("OperatorNew", self.password, "admin")["account"]["_id"], self.admin["_id"])

    def test_reset_exact_unicode_password_revokes_sessions_and_preserves_record(self):
        self.login()
        tokens = [self.auth.authenticate("PlayerOne", self.password, "player")["token"] for _ in range(2)]
        before = self.domain.get_account(self.player["_id"])
        new_password = "  New 漢字 e\u0301 😀 password  "
        response = self.client.post(self.reset, data=self.reset_form(password=new_password, confirmation=new_password))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/accounts/" + self.player["_id"])
        after = self.domain.get_account(self.player["_id"])
        before.pop("revision")
        after.pop("revision")
        self.assertEqual(before, after)
        for token in tokens:
            with self.assertRaises(AuthError):
                self.auth.validate_token(token, "player")
        self.assertEqual(self.auth.authenticate("PlayerOne", new_password, "player")["account"]["_id"], self.player["_id"])
        for rejected in (self.password, new_password.strip()):
            with self.assertRaises(AuthError):
                self.auth.authenticate("PlayerOne", rejected, "player")
        for material in (str(response.headers), response.get_data(as_text=True), str(list(self.db.admin_audit.find({})))):
            self.assertNotIn(new_password, material)
            self.assertNotIn(self.password_hash, material)

    def test_reset_128_non_bmp_characters_is_not_browser_capped_to_64(self):
        self.login()
        text = self.assert_blank_passwords(self.client.get(self.reset))
        self.assertNotIn('maxlength="128"', text)
        password = "😀" * 128
        self.assertEqual(self.client.post(self.reset, data=self.reset_form(password=password, confirmation=password)).status_code, 302)
        self.assertEqual(self.auth.authenticate("PlayerOne", password, "player")["account"]["_id"], self.player["_id"])

    def test_own_password_reset_signs_operator_out(self):
        self.login()
        path = "/accounts/" + self.admin["_id"] + "/password"
        password = "Another-admin-test-password"
        form = {"csrf_token": self.token(path), "revision": str(self.domain.get_account(self.admin["_id"])["revision"]),
                "password": password, "confirmation": password, "reason": "Operator recovery"}
        response = self.client.post(path, data=form)
        self.assertEqual(response.headers["Location"], "/login")
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_token", session)
            self.assertNotIn(password, str(dict(session)))
        self.assertEqual(self.client.get("/accounts").headers["Location"], "/login")
        self.assertEqual(self.auth.authenticate("Operator", password, "admin")["account"]["_id"], self.admin["_id"])

    def test_reset_suspended_account_does_not_enable_it(self):
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"status": "suspended"}})
        self.login()
        self.assertIn("will not restore sign-in access", self.client.get(self.reset).get_data(as_text=True))
        self.assertEqual(self.client.post(self.reset, data=self.reset_form()).status_code, 302)
        self.assertEqual(self.domain.get_account(self.player["_id"])["status"], "suspended")
        with self.assertRaises(AuthError):
            self.auth.authenticate("PlayerOne", "New-dummy-password-456", "player")

    def test_confirmation_error_keeps_only_nonsecret_fields(self):
        self.login()
        form = self.reset_form(confirmation="A different private dummy")
        before = self.snapshot()
        response = self.client.post(self.reset, data=form)
        self.assertEqual(response.status_code, 409)
        text = self.assert_blank_passwords(response)
        self.assertIn(form["reason"], text)
        self.assertIn('name="revision" value="0"', text)
        self.assertNotIn(form["password"], text)
        self.assertNotIn(form["confirmation"], text)
        self.assertEqual(before, self.snapshot())

    def test_invalid_passwords_return_empty_controls_and_preserve_data(self):
        self.login()
        for password in ("", "short", "x" * 129, "Null-embedded\x00-password"):
            with self.subTest(length=len(password)):
                form = self.reset_form(password=password, confirmation=password)
                before = self.snapshot()
                response = self.client.post(self.reset, data=form)
                self.assertEqual(response.status_code, 409)
                self.assert_blank_passwords(response)
                if password:
                    self.assertNotIn(password, response.get_data(as_text=True))
                self.assertEqual(before, self.snapshot())

    def test_required_audit_reason_is_an_inline_error(self):
        self.login()
        for path, form in ((self.edit, self.edit_form(reason="")), (self.reset, self.reset_form(reason=""))):
            before = self.snapshot()
            response = self.client.post(path, data=form)
            self.assertEqual(response.status_code, 409)
            self.assertIn('role="alert"', response.get_data(as_text=True))
            self.assertIn('name="reason"', response.get_data(as_text=True))
            self.assertEqual(before, self.snapshot())

    def test_duplicate_username_is_inline_and_preserves_values(self):
        self.login()
        response = self.client.post(self.edit, data=self.edit_form(username="operator"))
        self.assertEqual(response.status_code, 409)
        self.assertIn('value="operator"', response.get_data(as_text=True))
        self.assertIn('role="alert"', response.get_data(as_text=True))
        self.assertEqual(self.domain.get_account(self.player["_id"])["username"], "PlayerOne")

    def test_self_suspension_stays_forbidden_and_form_is_usable(self):
        self.login()
        path = "/accounts/" + self.admin["_id"] + "/edit"
        response = self.client.post(path, data={"csrf_token": self.token(path),
            "revision": str(self.domain.get_account(self.admin["_id"])["revision"]),
            "username": "Operator", "status": "suspended", "reason": "Cannot suspend self"})
        self.assertEqual(response.status_code, 403)
        self.assertIn('name="username"', response.get_data(as_text=True))
        self.assertEqual(self.domain.get_account(self.admin["_id"])["status"], "active")

    def test_strict_forms_reject_extra_duplicate_query_and_missing_fields(self):
        self.login()
        for path, valid in ((self.edit, self.edit_form()), (self.reset, self.reset_form())):
            forms = [dict(valid, role="admin"), dict(valid, leader="forged")]
            for key in valid:
                duplicate = MultiDict(list(valid.items()) + [(key, valid[key])])
                forms.append(duplicate)
            missing = dict(valid)
            missing.pop("revision")
            forms.append(missing)
            for form in forms:
                before = self.snapshot()
                self.assertEqual(self.client.post(path, data=form).status_code, 400)
                self.assertEqual(before, self.snapshot())
            self.assertEqual(self.client.post(path + "?username=Override", data=valid).status_code, 400)

    def test_file_uploads_and_json_are_not_account_forms(self):
        self.login()
        for path, form in ((self.edit, self.edit_form()), (self.reset, self.reset_form())):
            before = self.snapshot()
            upload = dict(form, file=(io.BytesIO(b"not a form field"), "unused.txt"))
            self.assertEqual(self.client.post(path, data=upload).status_code, 400)
            self.assertEqual(self.client.post(path, json=form,
                headers={"X-CSRFToken": form["csrf_token"]}).status_code, 400)
            self.assertEqual(before, self.snapshot())

    def test_malformed_revision_is_rejected_before_mutation(self):
        self.login()
        for revision in ("", "-1", "+1", "1.0", "01", " 0", "０", "9223372036854775808", "9" * 100):
            form = self.reset_form(revision=revision)
            before = self.snapshot()
            self.assertEqual(self.client.post(self.reset, data=form).status_code, 400)
            self.assertEqual(before, self.snapshot())

    def test_stale_edit_requires_explicit_reload_and_never_upgrades_revision(self):
        self.login()
        form = self.edit_form(username="StaleRename")
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$inc": {"revision": 1}})
        before = self.snapshot()
        response = self.client.post(self.edit, data=form)
        self.assertEqual(response.status_code, 409)
        text = response.get_data(as_text=True)
        self.assertIn("Reload account form", text)
        self.assertNotIn('name="revision"', text)
        self.assertNotIn('name="username"', text)
        self.assertEqual(before, self.snapshot())
        self.assertIn('name="revision" value="1"', self.client.get(self.edit).get_data(as_text=True))

    def test_stale_reset_drops_secret_and_requires_explicit_reload(self):
        self.login()
        form = self.reset_form()
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$inc": {"revision": 1}})
        before = self.snapshot()
        response = self.client.post(self.reset, data=form)
        self.assertEqual(response.status_code, 409)
        text = response.get_data(as_text=True)
        self.assertIn("Reload password form", text)
        self.assertNotIn('type="password"', text)
        self.assertNotIn('name="revision"', text)
        self.assertNotIn(form["password"], text)
        self.assertEqual(before, self.snapshot())

    def test_invalid_username_is_escaped_in_error_form(self):
        self.login()
        response = self.client.post(self.edit, data=self.edit_form(username='<script>alert(1)</script>'))
        self.assertEqual(response.status_code, 409)
        text = response.get_data(as_text=True)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_unknown_accounts_return_404_without_mutation(self):
        self.login()
        before = self.snapshot()
        for suffix in ("edit", "password"):
            response = self.client.get("/accounts/" + str(uuid4()) + "/" + suffix)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(before, self.snapshot())

    def test_unexpected_reset_exception_never_echoes_secret(self):
        self.login()
        form = self.reset_form()
        domain = self.app.extensions["alliance_domain"]
        with patch.object(domain, "admin_reset_password", side_effect=RuntimeError(form["password"])), self.assertLogs(self.app.logger, level="ERROR") as logs:
            response = self.client.post(self.reset, data=form)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(form["password"], response.get_data(as_text=True))
        self.assertNotIn(form["password"], str(response.headers))
        self.assertNotIn(form["password"], "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
