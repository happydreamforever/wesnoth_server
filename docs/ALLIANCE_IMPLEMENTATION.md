# Alliance Battle implementation checklist

Implementation authorized on 2026-10-19. Backend implementation and VPS verification are complete for the checked items. Windows cache preparation and isolated package installation pass. Actual MongoDB profile-location startup, journaled write/read and clean-restart persistence now pass; the user confirms WAN was disconnected while local Ethernet stayed connected for that run. The corrected profile initialization now passes with administrator Uni and owned database stopped. NEXT_TEST.md starts the same LOCALAPPDATA/WesnothAlliance/runtime database and local website for browser login; the original partial repository runtime remains preserved. Administrator website and Android account/team integration remain pending. See [the runtime handoff](ALLIANCE_RUNTIME.md). This is the working specification and delivery checklist; unchecked items are not available in the installed game. Test only with LDPlayer. Preserve the completed1.19.26 game, OBB, native dependencies and guest LAN server.

## Player experience and first-release rules

A player creates an account, chooses one personal leader, learns in three short connected campaign missions, joins a team, and brings that same leader to Alliance Battle. Experience belongs to that leader. Team experience belongs to the team. Captain is a responsibility transferred by the current captain, not a prize automatically awarded by level.

- One account owns one leader initially. Starter choices: human Spearman, Elvish Fighter, Orcish Grunt, Dwarvish Fighter, Drake Fighter or Skeleton. Use their actual 1.19.26 advancement trees and thresholds. No equipment system, invented stat multipliers or unlimited after-max-level advancement.
- Ordinary recruits belong to the current game. The personal leader's permanent advancement is selected between games. Its permanent type is locked during a game; battlefield defeat does not delete the account's leader.
- New custom campaign missions connect to the local server for progression. Existing campaigns remain practice with their existing saves; local save files cannot grant account XP.
- A team holds at most eight accounts, including its captain. Each account belongs to at most one team. Members apply; the captain accepts. Players can leave when their team is not in an active progression run. The captain transfers command before leaving.
- A team belongs to one area. Begin with Area 1; the administrator can add areas and move inactive teams. Area lists and rankings are separate. Race does not change an area's rules or environment.
- Fixed lineups: 2v2, 3v3 or 4v4, depending on the approved map. Both captains approve the map and lineups; every selected player marks ready. Start locks all participants and both teams. Each member controls their own army. The captain coordinates rather than taking teammates' turns.
- Existing map alliances must be preserved: Isar's Cross sides 1/4 vs 2/3; Hexcake 1/4/5 vs 2/3/6; Mokena Prairie 1/3/5/8 vs 2/4/6/7. Validate these against the packaged scenario definitions before game integration.
- Initial format uses full leader strength and displays both lineups' levels before acceptance. Brackets and equalized formats are later options. Do not split the small initial population into three queues.
- Reconnection returns a player to their existing side. No new army joins an ongoing battle. Win by defeating all opposing leaders or an explicit team surrender. A draw requires both captains' agreement. Disputed results wait for review.
- Proposed v1 reward constants: completed campaign victory 20 leader XP; Alliance win/loss/draw 20/10/10 leader XP and 100/25/50 team XP. Team level is 1 + floor(team XP / 500). Team rating starts at 1000, with Elo K=24. These constants are versioned and adjustable before balancing tests.
- Cancelled, interrupted and practice games award no XP. Repeating a completion request cannot duplicate rewards. Completed campaign missions can be replayed; they grant their fixed reward once per new completed run. A disconnected unfinished mission must restart in v1.

Mastery comes from advancing the leader, learning terrain and matchups, developing a reliable team and climbing the area's standings. Team level records long-term achievement; it does not secretly multiply combat damage.

## Storage and trust boundaries

Use a separate Python service with local MongoDB 8.0.32 on the Windows game-server computer, an authenticated single-member replica set and a database-scoped application user. The user corrected the proposed shared connection: it is an internet server and must not be used for offline gameplay. Windows profile startup/persistence and authenticated administrator initialization now pass; offline service/browser acceptance remains pending. The user has deferred malware troubleshooting; preserve earlier runtime and diagnostic evidence. Multi-document transactions must atomically reserve players, award XP, update ratings and close a run. Single-member replication enables transactions, not redundancy.

The existing `.env` remains private, unchanged and unused by the local game runtime. Its internet-hosted database was assessed read-only before the user corrected the deployment; no remote writes or external-mode implementation occurred. Do not continue external-database work or inspect its credentials for this task. New local runtime credentials are generated into an ignored, access-restricted directory. The Android application never receives MongoDB credentials.

| Collection | Canonical ownership and constraints |
| --- | --- |
| accounts | Unique normalized username, password hash, role/status, one embedded leader, bounded campaign progress, active run, revision |
| auth_sessions | Hashed random session tokens, account and scope, explicit expiry; TTL is cleanup only |
| auth_attempts | Bounded-duration login failure counters; no passwords or raw tokens |
| teams | Unique normalized name, area, captain, up to eight members, XP/rating/revision and active run; unique membership across teams |
| areas | Name, enabled flag and approved maps |
| game_runs | Versioned rules, immutable map/lineups/leader snapshots, ready/approval states, results and status |
| settlements | One receipt per run; accepted outcome, exact awards and revisions for replay-safe settlement |
| admin_audit | Actor, action, target, reason and safe change details; never credentials |
| schema_metadata | Explicit supported schema version and migrations |

Wesnoth's guest relay does not independently simulate every combat action. The first custom release is for trusted local players, with validated membership, run state and result agreement. Stronger anti-cheat needs separate authoritative simulation. Do not describe client-reported combat as fully server-verified.

The admin website and internal bridge bind to loopback only. Native game account traffic requires a provisioned TLS server identity and downgrade refusal before any password/token is sent. Internal HTTP carries a separate bridge credential and validated player tokens. The current guest mode remains separate until that integration passes tests.

## Commit-sized implementation and acceptance checklist

### 1. Database and game rules

- [x] Record the agreed rules, database ownership, delivery order and remaining tests.
- [x] Pin Python 3.14.3 and all dependency wheels; provide a hash-verified offline Windows cache.
- [x] Provide isolated local MongoDB initialization, replica-set authentication and scoped runtime credentials without changing `.env` or Windows services.
- [x] Install explicit collection validators, unique indexes and a versioned schema.
- [x] Implement accounts, leader advancement, teams, membership approval, captain transfer, areas and standings.
- [x] Implement campaign runs and Alliance approvals/readiness/start/settlement state transitions.
- [x] Verify duplicate rewards, transaction rollback, simultaneous membership/start claims, invalid map/area/lineup and active-run changes using real MongoDB.
- [x] Confirm Windows cache verification, MongoDB executable version check and isolated installation of the 17 pinned Python packages. The user confirms WAN remained available during installation; this is local-cache installation evidence, not a physically disconnected installation test.
- [x] Identify the immediate startup failure from the returned log: Windows sharing violation during WiredTiger metadata rename/deletion, followed by WT_PANIC. This does not identify the holder or prove corruption.
- [ ] Identify the source of the file-sharing conflict and validate a safe startup fix while preserving the partial runtime. The scratch trace identifies svchost.exe PID4600 as a rename blocker; the current parent4196 hosts NetActvity. Service implementation and a safe startup remedy remain pending. The returned Stack leaves 13 callers unresolved; none of the complete module file's 76 ranges matches. The returned JSON places all 13 addresses in current private executable memory without identifying the software. The expanded Defender alert identifies C:\Windows\SysWOW64\netactive32.dll for Trojan:Win32/Wacatac.B!ml, Severe, Active, at 10/19/2026 3:36 PM; its relationship to the traced process and MongoDB crash is unverified. Containment outcome is unknown. On 2026-10-20 the user reports inability to delete it (method/error unspecified) and defers the malware investigation. Do not treat that as successful cleanup or a verified quarantine failure. The original conflict remains unresolved; profile-location startup now passes, allowing separate game database setup to proceed.
- [x] Confirm actual Windows MongoDB8.0.32 standalone startup, journaled write/read and clean-restart persistence in profile storage. Paired20261020-033530 reports pass all8 checks; both processes exit0 with no forced cleanup. Earlier D: failure and original partial runtime remain preserved.
- [x] Confirm WAN was disconnected during the successful profile-storage fixture: user explicitly confirms WAN disconnected and local Ethernet connected. This is user-observed connectivity; the reports do not contain an independent network trace.
- [x] Confirm actual Windows profile initialization with authenticated MongoDB8.0.32 replica set, schema, scoped application user and first administrator. Returned console shows corrected username-first ordering, Uni and ALLIANCE INITIALIZATION PASSED, with owned database stopped.
- [x] Record connectivity during successful administrator initialization: user confirms internet access was available. This is setup acceptance, not a disconnected-WAN initialization test; do not repeat initialization solely to change that evidence. Earlier offline standalone acceptance remains recorded separately.
- [ ] Confirm authenticated service startup and transaction rollback on Windows with WAN disconnected; the website launcher performs this check before serving.

### 2. Accounts and operator website

- [x] Password hashing, revocable scoped sessions, expiry and login throttling.
- [x] Local admin login, player/team/area/run views and audited state changes with CSRF and authorization checks.
- [x] Explicit first-admin bootstrap; no default shared password or raw database editor.
- [ ] Confirm admin startup, login, state persistence across restart and offline operation on Windows.

### 3. Native account integration

The 2026-10-20 delivery implements the portable server identity/public profile foundation and a Python loopback fixture; all five cases now pass on Windows by returned console evidence. A separate reusable C++ component now provides verified numeric-IP TLS, mandatory native TLS negotiation and bounded frames; VPS checks pass; the returned Windows transcript and JSON now confirm all 24 native cases using the existing executable. The user confirms WAN was disconnected while Ethernet stayed connected. Android cross-compilation was checked on the VPS; Android runtime execution is the next milestone. The installed game does not select this component yet. Preserve guest behavior and send no password/session token until server identity verification succeeds. The Python fixture does not complete native game integration.

- [x] Implement offline server TLS identity/public connection profile preparation, preservation and validation; VPS-tested.
- [x] Confirm Windows identity creation for100.99.99.14 with Python3.14.3/OpenSSL3.6.3; user console output passes creation/validation.
- [x] Confirm all five Windows Python loopback fixture cases. The corrected run reuses the identity and passes TLS1.2/TLS1.3 payloads and all three rejection checks; physical WAN status for this run remains unconfirmed.
- [ ] Import the public profile through a trusted route into the native client; private keys stay on the server.
- [x] Implement a standalone native account transport component with numeric-IP certificate/pin verification, no plaintext fallback, bounded send/receive, deadlines and cancellation; VPS and Android cross-build verified.
- [x] Confirm the native component Windows build and first six checks using the existing public identity (returned console, 2026-10-20).
- [x] Complete all 24 native Windows checks after the expired-certificate fixture correction, using the successful existing probe without rebuilding. Both reports were reviewed; the user confirms WAN was disconnected.
- [ ] Build the Android transport probe on Windows and verify its runtime in LDPlayer using the existing x86_64/API23 dependencies. A VPS cross-build is not Android runtime acceptance.
- [ ] Route the actual custom account screens through this strict component; stock guest fallback/allow_insecure must not affect Alliance mode.
- [ ] Add a bounded asynchronous native-server bridge; backend outage must not freeze the guest relay.
- [ ] Add Android registration/login/logout and leader/team screens using existing engine UI.
- [ ] Test invalid identity, downgrade, expired/revoked sessions, reconnect and unavailable backend.

### 4. Progression campaign

- [ ] Create three playable missions using existing assets in a separate custom add-on.
- [ ] Match immutable server run IDs, mission versions and selected leaders to games.
- [ ] Freeze permanent leader advancement until settlement; retain ordinary unit battle XP.
- [ ] Deliver result evidence through the native bridge, with durable pending-result retry.
- [ ] Verify mission order, replay rules, defeat, disconnect/restart, advancement choice and terminal unit behavior in LDPlayer.

### 5. Alliance Battle

- [ ] Build area/team listing, application approval, captain transfer and lineup selection in the game UI.
- [ ] Implement mutual map/lineup approval, readiness, fixed side assignment and start reservations.
- [ ] Integrate 2v2 first, then approved 3v3 and 4v4 maps with correct alliances.
- [ ] Implement captain coordination, surrender, mutual draw, result agreement and dispute review.
- [ ] Reconnect only to an existing side; no mid-game new army or leader substitution.
- [ ] Test at least two human-controlled LDPlayer instances, an AI-assisted full lineup, reconnect and duplicate completion without WAN access.
- [ ] Show settled leader XP, team XP/level and area rating in the app after reconnect/restart.

### 6. Recovery and release

- [ ] Maintenance-mode backup and restore of MongoDB plus managed replay/result files; verify a restore into a separate destination.
- [ ] Audited dispute resolution and controlled XP correction without unrestricted document edits.
- [ ] Versioned schema migration and compatibility rejection; Git rollback alone is not a database rollback.
- [ ] Return exact offline build/run/test commands for each client/server delivery and save logs.
- [ ] Final acceptance: fresh player -> campaign advancement -> team membership -> captain -> same leader in an offline Alliance match -> durable rewards after restart.

## Delivery discipline

Commit each tested unit of work separately and push through the existing repositories. Keep checked boxes specific: implemented and VPS-verified is different from Windows/LDPlayer-verified. The first handoff is the local database/service foundation; it does not add Alliance Battle to the currently installed Android menu. Test each dependent milestone before expanding the next Windows delivery.

Reference decisions: [MongoDB transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/), [authenticated replica sets](https://www.mongodb.com/docs/v8.0/tutorial/deploy-replica-set-with-keyfile-access-control/), [Waitress on Windows](https://flask.palletsprojects.com/en/stable/deploying/waitress/).
