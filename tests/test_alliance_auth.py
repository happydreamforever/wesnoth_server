"""Real MongoDB authentication tests; never load a deployment configuration."""
from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlsplit

from pymongo import MongoClient

from alliance.auth import AuthError, AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService
from alliance.schema import bootstrap_schema


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGO_URI"), "Isolated test MongoDB URI required")
class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ["ALLIANCE_TEST_MONGO_URI"]
        if urlsplit(uri).scheme != "mongodb" or urlsplit(uri).hostname != "127.0.0.1":
            raise RuntimeError("Tests require an isolated loopback database.")
        cls.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        cls.db = cls.client["alliance_test_auth_" + uuid4().hex]
        bootstrap_schema(cls.db)
        bootstrap_auth_schema(cls.db)
        cls.domain = AllianceService(cls.db)
        cls.auth = AuthService(cls.db)
        cls.password = "a long fixture password"
        cls.encoded = hash_password(cls.password)
        cls.admin = cls.domain.bootstrap_admin("Operator", cls.encoded)
        cls.player = cls.domain.register("PlayerOne", cls.encoded)

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database(cls.db.name)
        cls.client.close()

    def setUp(self):
        self.db.auth_attempts.delete_many({})
        self.db.auth_sessions.delete_many({})
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"status": "active"}})

    def test_password_policy_and_salted_argon2id(self):
        self.assertTrue(self.encoded.startswith("$argon2id$"))
        self.assertNotEqual(hash_password(self.password), self.encoded)
        for value in ("short", "x" * 129, None):
            with self.assertRaises(AuthError):
                hash_password(value)

    def test_login_scopes_tokens_and_casefold(self):
        result = self.auth.authenticate("PLAYERONE", self.password, "player")
        self.assertNotIn("password_hash", result["account"])
        self.assertEqual(self.auth.validate_token(result["token"], "player")["_id"], self.player["_id"])
        stored = self.db.auth_sessions.find_one()
        self.assertNotIn(result["token"], str(stored))
        with self.assertRaises(AuthError):
            self.auth.validate_token(result["token"], "admin")
        with self.assertRaises(AuthError):
            self.auth.authenticate("Operator", self.password, "player")

    def test_expiry_checked_before_ttl_cleanup(self):
        result = self.auth.authenticate("PlayerOne", self.password, "player")
        self.db.auth_sessions.update_many({}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        with self.assertRaises(AuthError):
            self.auth.validate_token(result["token"], "player")

    def test_logout_revocation_and_account_suspension(self):
        result = self.auth.authenticate("PlayerOne", self.password, "player")
        self.auth.revoke_token(result["token"])
        with self.assertRaises(AuthError):
            self.auth.validate_token(result["token"], "player")
        result = self.auth.authenticate("PlayerOne", self.password, "player")
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"status": "suspended"}})
        with self.assertRaises(AuthError):
            self.auth.validate_token(result["token"], "player")

    def test_rate_limit_and_generic_invalid_credentials(self):
        for _ in range(10):
            with self.assertRaises(AuthError) as raised:
                self.auth.authenticate("PlayerOne", "wrong password", "player")
            self.assertEqual(raised.exception.code, "invalid_credentials")
        with self.assertRaises(AuthError) as raised:
            self.auth.authenticate("PlayerOne", self.password, "player")
        self.assertEqual(raised.exception.code, "rate_limited")
        with self.assertRaises(AuthError) as missing:
            self.auth.authenticate("Missing", "wrong password", "player")
        self.assertEqual(missing.exception.code, "invalid_credentials")

    def test_random_tokens_and_account_wide_revocation(self):
        first = self.auth.authenticate("PlayerOne", self.password, "player")["token"]
        second = self.auth.authenticate("PlayerOne", self.password, "player")["token"]
        self.assertNotEqual(first, second)
        self.auth.revoke_account_sessions(self.player["_id"])
        for token in (first, second, "x", {}, None):
            with self.assertRaises(AuthError):
                self.auth.validate_token(token, "player")

    def test_suspension_between_password_check_and_session_issue(self):
        from alliance import auth
        original = auth._HASHER.verify
        def suspend_then_return(encoded, password):
            verified = original(encoded, password)
            self.domain.admin_set_account_status(self.admin["_id"], self.player["_id"],
                                                  "suspended", "Fixture suspension during login")
            return verified
        # PasswordHasher methods are read-only; wrap the hasher instance instead.
        with patch.object(auth, "_HASHER", wraps=auth._HASHER) as mocked:
            mocked.verify.side_effect = suspend_then_return
            with self.assertRaises(AuthError):
                self.auth.authenticate("PlayerOne", self.password, "player")
        self.assertEqual(self.db.auth_sessions.count_documents({}), 0)


if __name__ == "__main__":
    unittest.main()
