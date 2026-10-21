# Alliance account and team protocol 1

The native connection supports player registration/login/profile/logout, public team directory and creation, private membership application/decision management, captain transfer, team departure, area rankings and private battle planning. It remains separate from stock guest multiplayer. It cannot award XP, start campaigns/battles or settle results. APK1192604 added private application decisions. APK1192605 added three management/ranking operations and explicit archive consent. APK1192606 adds the seven planning operations below; it has no battle-start or result route. Existing account and earlier directory message shapes remain compatible.

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
| application_decisions | Empty object | decisions | 200 |
| ack_decision | decision_id | decision_id, status="read" | 200 |
| leave_team | team_id, allow_archive (JSON boolean) | team_id, account_id, status="left", archived (JSON boolean) | 200 |
| transfer_captain | team_id, account_id | team_id, account_id, status="transferred" | 200 |
| standings | area_id | area_id, teams, has_more (JSON boolean) | 200 |
| battle_maps | area_id | area_id, maps | 200 |
| my_battles | after | battles, next | 200 |
| battle_detail | battle_id | battle (detail) | 200 |
| propose_battle | team_id, opponent_team_id, map_id, lineups | battle (detail) | 201 |
| approve_battle | battle_id | battle (detail) | 200 |
| battle_ready | battle_id, ready (JSON boolean) | battle (detail) | 200 |
| cancel_battle | battle_id | battle (detail) | 200 |

Team/account IDs are lowercase UUID strings. Area IDs retain the existing bounded ASCII identifier format, including the seeded `area-1`. `after` is empty for the first page; later pages use the previous response's `next`. Non-area cursors are UUIDs. Directory/application pages contain at most 20 strictly increasing unique IDs, with `next` either empty or equal to the final ID of a full page. Neither server nor client automatically follows unbounded pages. There are at most 64 pending applicants per team and eight members.

## Explicit public and private projections

- Area: `id`, `name`.
- Team summary: `id`, `name`, `area_id`, `captain_id`, `level`, `experience`, `rating`, `member_count`.
- Team detail: summary fields except `member_count`, plus `area_name`, `capacity`, `members`.
- Member/applicant: `id`, `username`, `unit_type`, `level`.

Team detail must contain one to eight unique members, include its captain and report capacity eight. Team and applicant responses are matched to the requested team. Approval/rejection acknowledgements match the selected applicant; transfer acknowledgements match the selected new captain. Apply/withdraw/leave acknowledgements identify the authenticated actor; the game checks that ID against its captured current player profile. All management acknowledgements also match the selected team and exact operation status.

`my_applications` exposes only the current player's pending requests in active teams. A request to another team can remain pending after membership is granted elsewhere; it remains visible for withdrawal. `team_applicants` is available only to that team's current captain. Public directory/detail responses never contain applicants. Private views expose only the bounded display projection, never account hashes, session tokens, audits or arbitrary database documents.

Approval reuses the existing transaction: captain authorization, active-player/team checks, pending request, eight-seat capacity and one-team membership are checked together. Concurrent approval and active-run conflicts remain server decisions. Applying does not immediately join a team. Rejection/withdrawal remove pending applications and do not remove members. No membership operation awards personal or team experience. Schema and indexes are unchanged by this extension.

## Captain transfer, departure and rankings

transfer_captain requires another current member of the selected team. The transaction checks current captain authority and the actor, target and team are idle/eligible. Competing transfers or target departure cannot produce a captain outside the roster. The former captain remains a member. The new directory wrapper maps a suspended selected target to forbidden/HTTP403 so a valid caller is not logged out; the existing legacy domain transfer API keeps its suspended result. A genuine authentication401 still expires the caller session.

The exact leave_team body is {team_id, allow_archive:boolean}; missing, nonboolean and extra fields are rejected. The native Request defaults allow_archive to false, and the game only sets it true after explicitly confirming the sole-captain archive warning. The server finds the authenticated actor's active membership and checks the expected team within every transaction attempt. A captain with other members gets captain_transfer_required. A sole member with allow_archive:false gets conflict, without mutation. This prevents stale ordinary-leave confirmation from archiving a team after another member leaves or transfers captaincy. An authorized last-member departure archives the team, clears pending applications and removes it from active directory/rankings. The response identifies the actor and reports archived as a strict boolean. Client and bridge reject archived:true when consent was false; consent true with archived:false remains valid if the roster changed. The legacy leave API retains its original contract.

standings is a fixed top20 read, without a cursor. The server validates the enabled area, queries at most21 active teams and emits20 summaries with has_more indicating an additional result. Both bridge and client bind the response area to the request, require unique team UUIDs, rating descending and UUID ascending for equal ratings, and validate all existing summary bounds. has_more:true requires exactly20 returned teams. Archived teams are excluded. Larger directories remain accessible through teams paging.

Approval/rejection choice and confirmation, transfer choice/confirmation and leave confirmation start on Back without changes. Back/Escape or default Open sends no mutation. A confirmed management acknowledgement triggers a fresh My team read. A failed refresh is reported separately from the confirmed change. Timeout/cancel/connection/protocol ambiguity directs the player to read My team; no mutation is automatically retried. Existing create/apply/withdraw confirmation menus are unchanged. Management actions award no personal/team XP and do not alter rating or capacity. No database schema/index migration is required.

## Battle planning without gameplay start

The seven planning operations use the same authenticated POST directory routes and exact field rules. Only an active player may request the enabled area's approved catalog. It contains at most three maps, in the fixed catalog order below; response area matches the request. No downloaded map or replacement OBB is needed.

| Map id | Name / scenario id | Players per team | First team sides | Opponent sides |
| --- | --- | --- | --- | --- |
| isars-cross | Isar's Cross / multiplayer_Isars_Cross | 2 | 1, 4 | 2, 3 |
| hexcake | Hexcake / multiplayer_Hexcake | 3 | 1, 4, 5 | 2, 3, 6 |
| mokena-prairie | Mokena Prairie / multiplayer_8p_Mokena_Prairie | 4 | 1, 3, 5, 8 | 2, 4, 6, 7 |

Each map is exactly `id`, `name`, `scenario_id`, `size`, `sides`; sides is exactly two ordered arrays matching that approved map. Names, scenario IDs, sizes and side assignments are pinned together. The same values match the already packaged1.19.26 scenario/map files.

`my_battles` lists saved Alliance plans for the caller's current active team; a player without a team receives an empty page. It includes draft and historical states, uses UUID-ascending pages of at most20 unique plans and the existing bounded `after`/`next` rules. `battle_detail` is private to current members of either participating team. Neither the public directory nor unrelated players receive these lineups.

A summary contains exactly `id`, `area_id`, `map_id`, `state`, `created_at`, `teams`. Its two teams each contain exactly `id`, `name`, in proposer/opponent order. `state` is `draft`, `running`, `completed` or `cancelled`; the last three are readable existing states, not permission to launch gameplay through this protocol. IDs and UTC calendar timestamps use the existing bounds.

A detail contains exactly `id`, `area_id`, `state`, `created_at`, `map`, `validity`, `teams`. Each of its two teams is exactly `id`, `name`, `captain_id`, `approved`, `players`. Captain ID is the current active team's captain UUID or the empty string for an archived/unavailable team. Approval is a JSON boolean indicating whether the stored approval belongs to that current captain. Each ordered player is exactly `id`, `username`, `unit_type`, `level`, `side`, `ready`; the ready flag is a JSON boolean. Both lineups have exactly the selected map's size, unique player IDs across both teams and the pinned sides in lineup order. Displayed leader type/level come from the saved proposal snapshot; the server compares the complete stored leader with current state before approval or readiness.

`validity` is one of `valid`, `roster_changed`, `area_changed`, `map_unavailable`, `leader_changed`, `player_unavailable`, `team_unavailable`, `busy`, `rules_changed`. A readable stale draft is retained for inspection and authorized cancellation; it is never silently refreshed into a different lineup.

`propose_battle.lineups` is exactly two objects, each exactly `team_id`, `account_ids`. The two team IDs must match the acting captain's selected current team and distinct opponent. Each account array has exactly the map's2–4 unique current members; its order assigns that team's fixed sides. Both teams must be active, idle and in the same enabled area, the map must still be approved, and selected players and captains must remain active/idle. The server stores fresh immutable leader/name snapshots inside the transaction. The expected team is bound to the actor and reply; map, opponent and every ordered selected player/side are bound to the request. There may be only one draft involving either team. Draft creation touches revisions to serialize these checks but makes no active_run reservation.

A native proposal starts with **no captain approvals and no ready players**, including the proposer. `approve_battle` requires a current participating captain, a draft and a valid current roster/area/map/leader snapshot. Each captain explicitly approves independently. A captain change invalidates that team's prior approval by identity; the successor must approve. `battle_ready` changes only the authenticated selected current member's flag. Setting true requires a valid draft and both current-captain approvals; setting false permits withdrawal from a stale draft by a selected current member. `cancel_battle` requires a current participating captain and accepts draft or already-cancelled state. It can cancel stale drafts without requiring valid lineups; it cannot cancel running/completed games through this route. Cancellation awards nothing and makes the teams eligible for another draft.

Planning mutations use explicit confirmation with Back without changes as the default. Bound replies cannot acknowledge a different plan, lineup, captain approval or actor readiness. An uncertain result is reconciled through My battle plans and a fresh detail; there is no automatic retry. Proposal, approval, readiness and cancellation do not change personal/team XP, rating, roster capacity or the original game/OBB. There is no native Start command, combat launch, result submission, schema migration or database reinitialization in this batch.

## Persistent application decisions

Each notice contains exactly `id`, `team_id`, `team_name`, `status`, `created_at`, `unread`. IDs are lowercase UUIDs; team names follow the existing3–40-character ASCII team-name rules. Status is `approved` or `rejected`, unread is a JSON boolean, and created_at is a valid UTC calendar timestamp in seconds (`YYYY-MM-DDTHH:MM:SSZ`). At most50 unique notices are returned, newest committed insertion first. Equal or adjusted-clock timestamps do not reorder history. There is no pagination. The oldest entry is evicted when the limit is exceeded, even if it is unread.

The optional accounts.application_decisions array uses the existing schema-v1 allowance for additional properties; existing validators/indexes and initialization remain unchanged. Legacy accounts without the field return an empty history. Every real pending approval/rejection appends a snapshot within the same MongoDB transaction as the membership/request change. Failure rolls back both. A repeated absent rejection does not append another notice; a repeated approval remains not_requested. Withdrawal creates no captain decision. Earlier decisions are not inferred from empty queues or backfilled.

Fetching history does not mark anything read. ack_decision is owner-only and idempotently marks only the selected retained ID read; its response must match the request ID. Another account's, unknown or evicted ID returns not_found. The event remains in history after acknowledgement. History is excluded from generic account/login and public directory responses. Team removal/renaming or subsequent membership does not rewrite a saved decision; My team is the current-membership view.

After successful login and before displaying My applications, the game checks for unread decisions. Back leaves unopened notices unread. Opening a detail and choosing OK sends one acknowledgement, without automatic retry. Application decisions also exposes already-read history. An unconfirmed acknowledgement is reconciled by reading history; it never claims the update succeeded. Fetch/ack failures preserve a valid session except an actual401.

## Responses, sessions and uncertain outcomes

Responses contain exactly `v`, `id`, `ok`, `status`, `data`. Register/me include `data.account`; login also includes `data.token`; logout returns `data.status="logged_out"`. The account projection is ID, username and leader fields (`starter_id`, `unit_type`, `level`, `experience`, `total_experience`).

Errors use a bounded known code/message projection. The game displays fixed local text rather than arbitrary backend exception text. HTTP 401 invalidates the session; a team-operation 403 denies that action without logging the player out. Membership/management errors include `capacity`, `already_member`, `not_requested`, `not_member`, `captain_transfer_required`, `busy`, `not_found`, `forbidden` and `conflict` as applicable. Planning also uses `invalid_lineup`, `invalid_map`, `different_area`, `invalid_state`, `approval_required`, `stale_proposal` and `planning_exists`; these do not automatically revoke a valid session.

An uncertain registration is reconciled by login, team creation by My team, and membership changes by My applications, My team or Review applications. Mutating UI actions require explicit confirmation and are never automatically repeated. A subsequent read failure cannot undo a committed mutation or justify an automatic retry.

Passwords and tokens remain in memory only; app restart requires fresh login. Successful logout revokes the token in MongoDB. A failed logout clears local state but does not claim server revocation. The saved public trusted profile survives an in-place APK update.

## Acceptance limits

The original account and first team directory/creation milestones are accepted on Windows/LDPlayer with WAN disconnected by user report, including prior account/team restart checks. APK1192603 membership and1192604 persistent approval/Read-history checks remain accepted. Windows1192605 bridge/APK rebuild, in-place install/setup and fresh admin/bridge readiness pass in the returned logs. The user's later confirmation accepts all1192605 A–H management checks with WAN disconnected, including transfer/leave/archive/rankings, safe cancellation, fresh rejection/Back-unread/Read, restored Koichi and unchanged XP. The separate final full-service restart was not explicitly confirmed; restored membership/history persistence through that restart remains pending.

APK1192606 adds planning only. Server59-domain/36-HTTP/7-auth/34-TLS checks and the actual four-player native planning/restart flow pass on the VPS; final client TLS/UI/protocol/host checks and the actual offline1192606 APK/signature/receipt verification also pass, as recorded in BASELINE.md; actual Windows1192606 build/install and LDPlayer planning acceptance remain pending. NEXT_TEST.md uses one combined delivery and four-player2v2 planning/restart report, without requiring eight test accounts or repeating accepted management A–H. Larger format contracts are verified with backend fixtures and pinned-map proof. Persistent-leader campaign integration, actual Alliance gameplay/start reservations and reward settlement remain later work. Existing local campaign saves cannot grant account XP; backend gameplay-integration readiness flags remain false.
