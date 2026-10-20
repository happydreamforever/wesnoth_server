# Alliance account protocol 1

Scope: player registration, login, personal-leader retrieval and logout. This connection is separate from stock guest multiplayer and cannot create games, alter teams, award XP or settle results.

## Connection and identity

The native Windows listener binds the existing numeric IP and port15001 from its public profile. Before any credentials, the client sends big-endian uint32 `1`, requires uint32 `0`, then completes TLS1.2 or TLS1.3 with certificate validity, numeric-IP SAN and SHA-256 DER certificate pin verification. There is no plaintext fallback. The app imports exactly the existing seven public-profile fields and requires explicit address/pin confirmation; private server keys and database/backend credentials are never transferred.

The bridge forwards only to `127.0.0.1:18765`, using the local protected runtime's bridge secret. MongoDB remains private on127.0.0.1:27018. This listener does not change guest `wesnothd` on15000.

## Bounded messages

Each encrypted frame is a big-endian uint32 byte length followed by one gzip member. Maximum compressed size65536, maximum decompressed UTF-8 JSON32768 bytes, maximum nesting depth8. Empty, truncated, trailing or concatenated gzip, invalid UTF-8, duplicate keys and unknown request fields/operations are rejected. Server responses use compact Boost.JSON serialization; the current client requires the same canonical serialization and exact response fields.

Each connection handles one request and one response. Client total deadline10seconds includes connection, TLS, send and receive; cancellation reaches the native worker. Server maximum32 connections, total10seconds per connection and six seconds for the private HTTP backend. No registration retry occurs automatically: after an ambiguous timeout the player is told to try logging in first, because the database may have committed the account already.

Request fields:

| Field | Contract |
| --- | --- |
| v | Integer1 |
| id | Fresh32lowercase-hex random request ID; must match response |
| op | `register`, `login`, `me` or `logout` |
| body | Operation-specific object below |
| token | Present only for `me`/`logout`; 43-character base64url session token |

| Operation | Body | Private backend route | Successful status |
| --- | --- | --- | --- |
| register | username, password, starter_id | POST /internal/v1/register |201 |
| login | username, password | POST /internal/v1/login |200 |
| me | Empty object | GET /internal/v1/me |200 |
| logout | Empty object | POST /internal/v1/logout |200 |

Usernames are3–24ASCII letters/digits/underscores. Registration passwords are12–128Unicode scalar values and at most512UTF-8bytes. The six starters use the existing backend IDs and advancement catalogue; arbitrary unit IDs are refused.

Responses contain exactly `v`, `id`, `ok`, `status`, and `data`. A successful register/me response includes `data.account`; successful login also includes `data.token`; logout includes `data.status="logged_out"`. Public account projection contains ID, username and leader (starter_id, unit_type, level, experience, total_experience). No password hash, role, backend configuration or database connection string is forwarded. Errors contain a bounded code/message projection; the game chooses fixed local messages and never displays arbitrary backend exception text. Authentication failure for an existing session clears that session and asks for login.

## Persistence and limitations

Passwords and session tokens are not written to game preferences, saves, history or diagnostics. The Android session is memory-only; app restart requires login. Successful logout revokes the token in MongoDB. A failed logout clears the local session and reports that server revocation was not confirmed. Registration creates one persistent starter leader at level1/XP0 through the existing transactional backend.

The account bridge does not integrate the persistent leader into campaigns or stock multiplayer. Existing campaign saves cannot grant account XP. Team menus, custom progression missions, match reservation and result settlement require later explicit protocol/game integration. The backend's gameplay integration readiness flags remain false.

VPS tests cover the production codec/client/bridge/backend and real disposable MongoDB, including Unicode credentials, duplicate registration, invalid password, revoked token and account/leader database restart persistence. The Windows bridge compile/link and artifact verification pass; actual listener startup and LDPlayer UI/LAN account tests remain pending in NEXT_TEST.md.
