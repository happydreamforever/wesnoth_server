# Alliance Battle implementation checklist

Implementation authorized on 2026-10-19. Backend implementation and VPS verification are complete for the checked items; Windows validation is pending. See [the runtime handoff](ALLIANCE_RUNTIME.md). This is the working specification and delivery checklist; unchecked items are not available in the installed game. Test only with LDPlayer. Preserve the completed 1.19.26 game, OBB, native dependencies and guest LAN server.

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

Use a separate Python service with local MongoDB 8.0.32, an authenticated single-member replica set and a database-scoped application user. Multi-document transactions must atomically reserve players, award XP, update ratings and close a run. Single-member replication enables transactions, not redundancy.

The existing `.env` remains private and unchanged. Its earlier read-only audit identified a remote standalone database and privileged credentials; this implementation must never initialize or migrate that database. New local runtime credentials are generated into an ignored, access-restricted directory. The Android application never receives MongoDB credentials.

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
- [ ] Confirm the new runtime on Windows with offline dependencies. VPS test success does not complete this box.

### 2. Accounts and operator website

- [x] Password hashing, revocable scoped sessions, expiry and login throttling.
- [x] Local admin login, player/team/area/run views and audited state changes with CSRF and authorization checks.
- [x] Explicit first-admin bootstrap; no default shared password or raw database editor.
- [ ] Confirm admin startup, login, state persistence across restart and offline operation on Windows.

### 3. Native account integration

- [ ] Provision a server TLS identity and public client connection profile.
- [ ] Fix numeric-IP TLS selection and reject plaintext fallback in custom account mode.
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
