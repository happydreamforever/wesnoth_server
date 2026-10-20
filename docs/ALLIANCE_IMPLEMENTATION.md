# Alliance Battle implementation checklist

Implementation authorized on 2026-10-19. Backend implementation and VPS verification are complete for the checked items. Windows cache preparation and isolated package installation pass. Actual MongoDB profile-location startup, journaled write/read and clean-restart persistence now pass; the user confirms WAN was disconnected while local Ethernet stayed connected for that run. The corrected profile initialization now passes with administrator Uni and owned database stopped. The returned Windows console now confirms profile database/service startup and transaction checks; the user confirms browser login as Uni, seeded Area 1 and WAN-disconnected operation. The first restart was blocked by a stale launcher marker after MongoDB logged completed storage shutdown. Returned process/listener metadata confirms the old owner absent. The OS-held launcher lock and guarded legacy recovery have been delivered. Returned Windows output now shows successful database and website re-launches using the same LOCALAPPDATA/WesnothAlliance/runtime; the user confirms WAN disconnected and an area created before the restarts. The user now reports the same area name, matching audit identifier and login page after sign-out, completing that browser acceptance at user-observed scope. Recovery backup output and exact shutdown exit codes were not supplied. The original partial repository runtime remains preserved. Android account integration is now implemented and VPS-tested; Windows/LDPlayer acceptance and team gameplay remain pending. Windows build and LDPlayer transport execution pass; the later device-only rerun also passes with WAN disconnected according to the user's corrected report. Standalone transport acceptance is complete; the new real-account delivery awaits Windows/LDPlayer acceptance. See [the runtime handoff](ALLIANCE_RUNTIME.md). This is the working specification and delivery checklist; unchecked items are not available in the installed game. Test only with LDPlayer. Preserve the completed1.19.26 game, OBB, native dependencies and guest LAN server.

Current Windows account checkpoint: registration, incorrect-password rejection, login/profile retrieval and explicit server logout/relogin all pass at user-observed scope with WAN disconnected. Repeat profile uses the same on-screen ID, Spearman, level1 and zero experience. NEXT_TEST.md quits and reopens only the logged-in game, checks saved trusted server and login-required state, then the same account/profile. Keep all backend windows running. No pull/build/reinstall/new account/profile import is needed. App/backend restart persistence, unavailable-service behavior and gameplay integration remain pending.

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

Use a separate Python service with local MongoDB 8.0.32 on the Windows game-server computer, an authenticated single-member replica set and a database-scoped application user. The user corrected the proposed shared connection: it is an internet server and must not be used for offline gameplay. Windows profile startup/persistence and authenticated administrator initialization now pass. Initial service/browser login and offline operation are user-confirmed; database/website re-launches also pass with WAN disconnected by user report. Same-area/audit persistence and browser sign-out now pass by user report. The user has deferred malware troubleshooting; preserve earlier runtime and diagnostic evidence. Multi-document transactions must atomically reserve players, award XP, update ratings and close a run. Single-member replication enables transactions, not redundancy.

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
- [x] Confirm authenticated service startup and transaction rollback on Windows: returned console passes MongoDB8.0.32/authenticated replica set/schema/administrator/rollback checks before serving; the user confirms WAN was disconnected with local Ethernet connected.

### 2. Accounts and operator website

- [x] Password hashing, revocable scoped sessions, expiry and login throttling.
- [x] Local admin login, player/team/area/run views and audited state changes with CSRF and authorization checks.
- [x] Explicit first-admin bootstrap; no default shared password or raw database editor.
- [x] Confirm admin startup and login on Windows: returned console supplies the local URL; user confirms Uni login, Area 1 visible and WAN-disconnected operation. Browser/connectivity observations are user-reported.
- [x] Confirm a newly created area and matching audit entry, sign-out requiring fresh login, and persistence of those records after website/database restart with WAN disconnected. User confirms prior creation, offline restarts, the same area name, matching audit identifier and the login page after sign-out; these are user-observed results.
- [x] Confirm the old launcher marker owner absent, implement permanent OS-held exclusion and a separate evidence-preserving guarded legacy-marker recovery; VPS checks cover contention/abrupt exit and recovery refusal paths.
- [x] Observe actual Windows database and website re-launches without the old marker error; repeated authenticated schema/administrator/rollback checks pass. User confirms WAN disconnected. Exact shutdown exit codes and latest pull heads were not supplied.
- [ ] Obtain the existing guarded-recovery report/backup path if available, without rerunning recovery against healthy applications. Do not infer exact Windows recovery API acceptance from Linux simulations or the later successful starts.

### 3. Native account integration

The 2026-10-20 delivery implements the portable server identity/public profile foundation and a Python loopback fixture; all five cases now pass on Windows by returned console evidence. A separate reusable C++ component now provides verified numeric-IP TLS, mandatory native TLS negotiation and bounded frames; VPS checks pass; the returned Windows transcript and JSON now confirm all 24 native cases using the existing executable. The user confirms WAN was disconnected while Ethernet stayed connected. Actual Windows Android compilation and all 22 LDPlayer loopback checks pass. The first run had WAN available. A later device-only rerun passes with identical file hashes, and the user's corrected report confirms WAN was disconnected during that rerun. Standalone transport acceptance is complete. The new account APK selects this component from the Alliance menu; the previously installed APK remains unchanged until the user installs the update. Preserve guest behavior and send no password/session token until server identity verification succeeds. The Python fixture does not complete native game integration.

- [x] Implement offline server TLS identity/public connection profile preparation, preservation and validation; VPS-tested.
- [x] Confirm Windows identity creation for100.99.99.14 with Python3.14.3/OpenSSL3.6.3; user console output passes creation/validation.
- [x] Confirm all five Windows Python loopback fixture cases. The corrected run reuses the identity and passes TLS1.2/TLS1.3 payloads and all three rejection checks; physical WAN status for this run remains unconfirmed.
- [x] Implement exact public-profile import, explicit address/pin confirmation and app-private storage; native validation precedes credentials. VPS Java/codec checks pass. Actual LDPlayer import acceptance remains pending; private keys stay on Windows.
- [x] Implement a standalone native account transport component with numeric-IP certificate/pin verification, no plaintext fallback, bounded send/receive, deadlines and cancellation; VPS and Android cross-build verified.
- [x] Confirm the native component Windows build and first six checks using the existing public identity (returned console, 2026-10-20).
- [x] Complete all 24 native Windows checks after the expired-certificate fixture correction, using the successful existing probe without rebuilding. Both reports were reviewed; the user confirms WAN was disconnected.
- [x] Deliver the standalone Android loopback fixture plus offline build/device helpers; actual VPS NDK build, receipt/reuse and host failure checks pass. Existing transport, game, database and native dependencies are preserved.
- [x] Build the standalone Android transport check on Windows and verify its runtime in LDPlayer using existing Boost1.88/OpenSSL3.4.1/x86_64/API23 dependencies. Returned output completes4 build steps, receipt/hash checks and22 cases on API28/x86_64. WAN was available by user confirmation.
- [x] Confirm the same completed Android transport check passes with WAN disconnected: device log android-alliance-device-20261020-090606-658-6087fc882b734b81a7224fc83017118a.txt passes all 22 cases and matching hashes. The user corrects the initial connectivity answer to WAN disconnected. This is user-observed connectivity, not a network trace; do not request another unchanged rerun.
- [x] Route actual account screens through strict native TLS, bounded gzip JSON, cancellation and memory-only sessions. Guest fallback/allow_insecure cannot affect Alliance requests; VPS cross-build and real database flow pass.
- [x] Add the separate asynchronous account bridge: 32 connections, 10-second request deadline, six-second private backend deadline, four allowlisted operations, no settlement route. VPS real TLS/outage/concurrency checks pass; guest relay is unchanged.
- [x] Implement Android registration/login/logout and personal-leader view/refresh using existing engine UI and unchanged OBB layouts; actual APK cross-build verified.
- [x] Compile/link the separate account bridge with the existing Windows MINGW64 tools and verify its artifact (returned console, 2026-10-20).
- [x] Start the account listener against the existing Windows runtime and accept its ready marker. The returned console confirms READY100.99.99.14:15001 after backend health passed; the earlier failure cause and this run's WAN status remain unconfirmed.
- [x] Build the account-enabled APK on Windows using the existing cached prerequisites and preserve the original game/OBB. Returned log confirms six native steps, 33 Gradle tasks and final artifact checks; internet was available by user report, so WAN-disconnected build acceptance remains unverified.
- [x] Install the completed account APK in LDPlayer and confirm the Wesnoth Alliance setup screen. User confirms the install success marker and both buttons; raw install log/exact filename and installation WAN status are not supplied.
- [x] Import the transferred public profile, compare the address/fingerprint, then start the game and confirm its Alliance main-menu entry. User reports all steps done and explicitly confirms the menu; no new log or WAN status supplied.
- [x] Create the first separate player account in LDPlayer and verify its personal leader/level/experience confirmation. Returned UI shows UniPlayer, Spearman, level1 and both experience values0; user explicitly confirms WAN disconnected and Ethernet connected. Player ID transcription is ambiguous; compare the actual UI during login.
- [x] Log in correctly as the existing UniPlayer in LDPlayer. Returned Logged in dialog shows the expected Spearman/level1/zero-experience profile; user confirms WAN disconnected and Ethernet connected.
- [x] Confirm the single incorrect-password attempt was rejected. User explicitly confirms Invalid username or password; do not repeat it.
- [x] Retrieve the same personal leader using the separate View personal leader operation. User explicitly confirms matching on-screen ID and all leader values with WAN disconnected.
- [x] Confirm explicit server logout acknowledgement, then repeat login/profile retrieval for the same player. User confirms the exact server-revoked message, matching on-screen ID/leader and WAN disconnected throughout. No direct old-token replay was performed.
- [ ] Quit/reopen the logged-in game, retain the trusted server profile, require fresh login and retrieve the same player/leader. This is the current test step; leave backend windows running.
- [ ] Accept public-profile import and the complete account flow in LDPlayer against Windows with WAN disconnected.
- [ ] Add team screens and their authenticated bridge operations after account acceptance.
- [x] Verify rejected identity/downgrade in the accepted transport; verify malformed account messages, backend outage, total deadlines, cancellation and revoked sessions on VPS.
- [ ] Complete remaining Android app restart and unavailable-service acceptance on actual Windows/LDPlayer. Explicit server logout/relogin is now separately accepted above.

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
