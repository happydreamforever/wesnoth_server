# Alliance account and team protocol 1

The native connection supports player registration/login/profile/logout, public team directory and creation, and private membership application management. It remains separate from stock guest multiplayer. It cannot award XP, start campaigns/battles or settle results. The membership extension is delivered in APK 1192603; existing account and directory message shapes remain compatible.

## Connection and identity

The Windows listener uses the numeric address and port in the saved public profile (currently 100.99.99.14:15001). Before credentials, the client sends big-endian uint32 `1`, requires uint32 `0`, then completes TLS 1.2 or 1.3 with certificate validity, numeric-IP SAN and SHA-256 DER certificate pin verification. There is no plaintext fallback. The app imports only the existing seven public-profile fields with explicit address/pin confirmation. Private server keys and database/backend credentials never enter the Android app.

The bridge compares the public profile with an in-memory CRLF-to-LF representation of the certificate file. Original identity bytes, DER pin, numeric-IP identity, validity and key matching are preserved. Startup diagnostics use fixed stage labels and numeric codes.

The bridge forwards only to `127.0.0.1:18765`, using the existing runtime's private bridge secret. MongoDB remains on `127.0.0.1:27018`. Guest `wesnothd` on port 15000 is unchanged.

## Bounded messages

Each encrypted frame is a big-endian uint32 length followed by one gzip member: at most 65,536 compressed bytes, 32,768 decompressed UTF-8 JSON bytes and nesting depth 8. Empty/truncated/trailing/concatenated gzip, invalid UTF-8, duplicate keys and unknown fields/operations are rejected. Responses use canonical compact Boost.JSON serialization and exact field sets.

Each connection handles one request/response. The native client's total deadline is 10 seconds and includes connect/TLS/send/receive; cancellation reaches the worker. The server permits at most 32 connections, with 10 seconds per connection and six seconds for the private HTTP backend. No mutation is automatically retried after an uncertain result.

| Request field | Contract |
| --- | --- |
| v | Integer 1 |
| id | Fresh 32 lowercase hexadecimal characters, echoed in the response |
| op | One exact operation below; maximum 24 bytes |
| body | Exact operation-specific object |
| token | Required for profile/logout and every team operation; absent for register/login; 43-character base64url session token |

| Account operation | Body | Private route | Success status |
| --- | --- | --- | --- |
| register | username, password, starter_id | POST /internal/v1/register | 201 |
| login | username, password | POST /internal/v1/login | 200 |
| me | Empty object | GET /internal/v1/me | 200 |
| logout | Empty object | POST /internal/v1/logout | 200 |

Usernames contain 3–24 ASCII letters/digits/underscores. Registration passwords contain 12–128 Unicode scalar values and at most 512 UTF-8 bytes. Starter IDs come from the six existing backend choices.

All team operations use POST `/internal/v1/team-directory/<operation>` and the authenticated player's identity. A caller cannot supply its own acting account ID, captain identity, XP, rating or capacity.

| Team operation | Exact body | Success data | Status |
| --- | --- | --- | --- |
| areas | after | areas, next | 200 |
| teams | area_id, after | teams, next | 200 |
| my_team | Empty object | team (detail or null) | 200 |
| team_detail | team_id | team (detail) | 200 |
| create_team | name, area_id | team (detail) | 201 |
| my_applications | after | teams, next | 200 |
| team_applicants | team_id, after | team_id, applicants, next | 200 |
| apply_team | team_id | team_id, account_id, status="applied" | 200 |
| withdraw_application | team_id | team_id, account_id, status="withdrawn" | 200 |
| approve_application | team_id, account_id | team_id, account_id, status="approved" | 200 |
| reject_application | team_id, account_id | team_id, account_id, status="rejected" | 200 |

Team/account IDs are lowercase UUID strings. Area IDs retain the existing bounded ASCII identifier format, including the seeded `area-1`. `after` is empty for the first page; later pages use the previous response's `next`. Non-area cursors are UUIDs. Pages contain at most 20 strictly increasing unique IDs, with `next` either empty or equal to the final ID of a full page. Neither server nor client automatically follows unbounded pages. There are at most 64 pending applicants per team and eight members.

## Explicit public and private projections

- Area: `id`, `name`.
- Team summary: `id`, `name`, `area_id`, `captain_id`, `level`, `experience`, `rating`, `member_count`.
- Team detail: summary fields except `member_count`, plus `area_name`, `capacity`, `members`.
- Member/applicant: `id`, `username`, `unit_type`, `level`.

Team detail must contain one to eight unique members, include its captain and report capacity eight. Team and applicant responses are matched to the requested team. Approval/rejection acknowledgements also match the selected applicant. Apply/withdraw acknowledgements identify the authenticated actor; the game checks that ID against its current player profile.

`my_applications` exposes only the current player's pending requests in active teams. A request to another team can remain pending after membership is granted elsewhere; it remains visible for withdrawal. `team_applicants` is available only to that team's current captain. Public directory/detail responses never contain applicants. Private views expose only the bounded display projection, never account hashes, session tokens, audits or arbitrary database documents.

Approval reuses the existing transaction: captain authorization, active-player/team checks, pending request, eight-seat capacity and one-team membership are checked together. Concurrent approval and active-run conflicts remain server decisions. Applying does not immediately join a team. Rejection/withdrawal remove pending applications and do not remove members. No membership operation awards personal or team experience. Schema and indexes are unchanged by this extension.

## Responses, sessions and uncertain outcomes

Responses contain exactly `v`, `id`, `ok`, `status`, `data`. Register/me include `data.account`; login also includes `data.token`; logout returns `data.status="logged_out"`. The account projection is ID, username and leader fields (`starter_id`, `unit_type`, `level`, `experience`, `total_experience`).

Errors use a bounded known code/message projection. The game displays fixed local text rather than arbitrary backend exception text. HTTP 401 invalidates the session; a team-operation 403 denies that action without logging the player out. Membership errors include `capacity`, `already_member`, `not_requested`, `busy`, `not_found` and `conflict` as applicable.

An uncertain registration is reconciled by login, team creation by My team, and membership changes by My applications, My team or Review applications. Mutating UI actions require explicit confirmation and are never automatically repeated. A subsequent read failure cannot undo a committed mutation or justify an automatic retry.

Passwords and tokens remain in memory only; app restart requires fresh login. Successful logout revokes the token in MongoDB. A failed logout clears local state but does not claim server revocation. The saved public trusted profile survives an in-place APK update.

## Acceptance limits

The original account and first team directory/creation slice are accepted on Windows/LDPlayer with WAN disconnected by user report, including stored team retrieval after all services restarted. Membership screens and APK 1192603 need their own Windows/LDPlayer acceptance. Current validation and delivery state are in BASELINE.md and NEXT_TEST.md.

Joining through an approved application is this extension's scope. Team leave/captain transfer screens, persistent-leader campaign integration, battle reservation/readiness and reward settlement remain later work. Existing local campaign saves cannot grant account XP; the backend gameplay-integration readiness flags remain false.
