"""Password hashing and revocable, purpose-scoped database sessions."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError, VerifyMismatchError
from pymongo import ReturnDocument


class AuthError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                       hash_len=32, salt_len=16, type=Type.ID)
_DUMMY_HASH = _HASHER.hash(secrets.token_urlsafe(32))
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise AuthError("invalid_password", "Use a password of 12 to 128 characters.")
    return _HASHER.hash(password)


def bootstrap_auth_schema(db):
    """Initialization only; normal runtime uses a database-scoped readWrite user."""
    validators = {
        "auth_sessions": {"$jsonSchema": {
            "bsonType": "object", "required": ["_id", "account_id", "scope", "expires_at"],
            "properties": {"_id": {"bsonType": "string"},
                "account_id": {"bsonType": "string"},
                "scope": {"enum": ["admin", "player"]},
                "expires_at": {"bsonType": "date"}, "revoked": {"bsonType": "bool"}}}},
        "auth_attempts": {"$jsonSchema": {
            "bsonType": "object", "required": ["_id", "count", "expires_at"],
            "properties": {"_id": {"bsonType": "string"},
                "count": {"bsonType": "int", "minimum": 1},
                "expires_at": {"bsonType": "date"}}}},
    }
    for name, validator in validators.items():
        if name not in db.list_collection_names():
            db.create_collection(name, validator=validator, validationLevel="strict")
        else:
            db.command("collMod", name, validator=validator, validationLevel="strict")
        db[name].create_index("expires_at", expireAfterSeconds=0)
    db.auth_sessions.create_index("account_id")


class AuthService:
    def __init__(self, db):
        self.db = db

    def authenticate(self, username, password, scope, *, observer=None):
        # Only an explicitly armed local diagnostic supplies this per-request
        # callback. It receives fixed outcomes, never authentication material.
        def observe(outcome):
            if observer is not None:
                try:
                    observer(outcome)
                except BaseException:
                    pass  # Diagnostics must not alter authentication behavior.
        if scope not in ("admin", "player"):
            raise AuthError("invalid_scope", "Invalid session purpose.")
        if not isinstance(username, str) or not 1 <= len(username) <= 32:
            observe("invalid_input")
            raise AuthError("invalid_credentials", "Invalid username or password.")
        if not isinstance(password, str) or len(password) > 128:
            observe("invalid_input")
            raise AuthError("invalid_credentials", "Invalid username or password.")
        now = datetime.now(timezone.utc)
        # A fixed fifteen-minute bucket bounds work even under simultaneous requests.
        # TTL lag cannot extend/shorten the check; every request uses an explicit bucket.
        bucket = int(now.timestamp()) // 900
        attempt_id = hashlib.sha256(f"{scope}:{username.casefold()}:{bucket}".encode()).hexdigest()
        attempts = self.db.auth_attempts.find_one_and_update(
            {"_id": attempt_id},
            {"$inc": {"count": 1}, "$setOnInsert": {
                "expires_at": datetime.fromtimestamp((bucket + 2) * 900, timezone.utc)}},
            upsert=True, return_document=ReturnDocument.AFTER)
        if attempts["count"] > 10:
            observe("rate_limited")
            raise AuthError("rate_limited", "Too many login attempts. Try again in 15 minutes.")
        account = self.db.accounts.find_one({"username_key": username.casefold()})
        encoded = account.get("password_hash", _DUMMY_HASH) if account else _DUMMY_HASH
        password_failure = "password_mismatch"
        try:
            verified = _HASHER.verify(encoded, password)
        except VerifyMismatchError:
            verified = False
        except InvalidHashError:
            verified = False
            password_failure = "invalid_stored_hash"
        except VerificationError:
            verified = False
            password_failure = "password_verification_failed"
        if (not verified or not account or account.get("status") != "active"
                or account.get("role") != scope):
            observe("account_missing" if not account else password_failure if not verified else "account_ineligible")
            raise AuthError("invalid_credentials", "Invalid username or password.")
        replacement_hash = _HASHER.hash(password) if _HASHER.check_needs_rehash(encoded) else encoded
        token = secrets.token_urlsafe(32)
        expires = now + timedelta(hours=1 if scope == "admin" else 8)
        def issue(session):
            current = self.db.accounts.find_one({"_id": account["_id"], "status": "active",
                "role": scope, "password_hash": encoded,
                "username_key": account["username_key"]}, session=session)
            if current is None:
                observe("session_state_changed")
                raise AuthError("invalid_credentials", "Invalid username or password.")
            # Conflict with simultaneous rename/suspension/password changes so a session
            # cannot appear after an administrator revoked that account's access.
            self.db.accounts.update_one({"_id": current["_id"]}, {
                "$set": {"password_hash": replacement_hash}, "$inc": {"revision": 1}}, session=session)
            self.db.auth_sessions.insert_one({"_id": self._digest(token), "account_id": current["_id"],
                "scope": scope, "created_at": now, "expires_at": expires, "revoked": False}, session=session)
            current["revision"] += 1
            return self._public(current)
        with self.db.client.start_session() as session:
            public = session.with_transaction(issue, max_commit_time_ms=10000)
        self.db.auth_attempts.delete_one({"_id": attempt_id})
        observe("login_accepted")
        return {"token": token, "account": public, "expires_at": expires}

    @staticmethod
    def _digest(token):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise AuthError("invalid_session", "Please sign in again.")
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    @staticmethod
    def _public(account):
        return {key: value for key, value in account.items()
                if key not in ("password_hash", "application_decisions")}

    def validate_token(self, raw_token, scope):
        if scope not in ("admin", "player"):
            raise AuthError("invalid_scope", "Invalid session purpose.")
        session = self.db.auth_sessions.find_one({"_id": self._digest(raw_token), "scope": scope,
            "revoked": False, "expires_at": {"$gt": datetime.now(timezone.utc)}})
        account = self.db.accounts.find_one({"_id": session["account_id"],
            "status": "active", "role": scope}) if session else None
        if not account:
            raise AuthError("invalid_session", "Please sign in again.")
        return self._public(account)

    def revoke_token(self, raw_token):
        self.db.auth_sessions.update_one({"_id": self._digest(raw_token)}, {"$set": {"revoked": True}})

    def revoke_account_sessions(self, account_id):
        self.db.auth_sessions.update_many({"account_id": account_id}, {"$set": {"revoked": True}})
