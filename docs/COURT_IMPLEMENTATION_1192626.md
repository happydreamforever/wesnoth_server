# Emerald Court replacement game — 1192626

This release replaces the former Company/strategic-round Team product. It uses
protocol 5 and a fresh schema-5 game. The approved Emerald Court presentation,
authored campaigns, account heroes, individual Room combat and native Wesnoth
engine remain the foundation. Prior schema-4 data is an isolated recovery archive,
not input to the new economy or territorial game.

## Navigation and geography

Team opens World for every player. Members can enter active Areas; other players
can find or create a Team. The regular path is World → Area → Castle. Team,
planning, review and Shop forms update within the workspace. Pinch, direct touch,
List, Centre and explicit zoom controls are available; no essential action relies
on hover, a shortcut or a long press.

The supplied map catalogue defines 128 Areas and one reusable 64-Castle layout.
Each Area has separate Castle identities and ownership. C028/C015 are Competition
Castles, C010/C055 are Plan Castles, and the other 60 are Normal Castles. The
source inventory and coordinate conversion are bound into the Android asset
manifest. The map is packaged separately from the existing OBB.

Automatic population rules open one Area initially and another per 16 Teams,
up to 128. An Area admits up to 30 Teams. It exposes at least four Normal Castles,
then two per local Team up to 60; Plan Castles open at two/ten Teams and Competition
Castles at four/twelve. Unused empty locations close only after the configured
24-hour delay. Administrators can select Auto/On/Off, with occupied/committed
locations protected from unsafe closure.

## Teams and combat

Teams have at most ten members and one home Area. Membership admission charges
only on captain acceptance; withdrawal, rejection and expiry release the hold.
Captains can rename the Team, remove uncommitted members, transfer leadership,
review applications and manage spending. Leaving or removal permanently withdraws
that membership's defense consent. Joining again does not reactivate it.

Normal Castles support one contest at a time and a maximum of three holdings per
Team, including pending captures. A successful capture protects the Castle for
one hour. An attacker reserves the Castle, capacity, daily trial and Team funds
together. The defender has two minutes to answer; otherwise the server runs the
approved frozen hero template or a standard garrison. A template's owner earns no
offline XP and their account/collection is not an executing player. A started
human side never silently converts to AI.

Plan Castles support agreed 1v1–4v4 native maps. A captain proposes map, common
gold, income, turns, visibility rules, hero cap, items and a 5/15/30/60/100-minute
delay. The opposing captain approves the exact revision within ten minutes.
Both Teams pay the agreed fee; members select a hero/faction and Ready. Lineup
or hero changes clear readiness. Published shared rules are immutable; different
rules require a new proposal and approval. Player reservations are separate from
Team membership, so disjoint Team battles can coexist. A player cannot claim
multiple Court seats or execute overlapping network battles.

Competitions admit 2–32 Teams. The administrator closes registration, freezes
settings and a random seed, and schedules rounds. The single-elimination bracket
has balanced byes. Every match in a round must resolve before advancing. A
technical cancellation refunds that match's applicable holds and creates a fresh
replacement requiring new seats/readiness and explicit administrator scheduling;
it does not silently award the bracket or cancel unrelated matches.

The existing battle service supervises native workers. Queued work has no tactical
loading countdown until a worker is available. Native command evidence, stable
controllers, durable replay and idempotent receipts govern completion. Worker
failure pauses play. Missing uploads, a dead process or incomplete evidence alone
cannot manufacture a victory. Same-account reconnection is supported. Existing
ordinary Room combat is full-human and requires every configured seat Ready.

## Crowns, holds and rewards

Crowns are integer virtual game balances. There is no payment gateway or cash-out.
Players and Teams start at zero. Requests for 100/500/1000 Crowns become spendable
only after one administrator approval. Contributions transfer personal funds to
the Team one-for-one and cannot be withdrawn. Every mutation records balanced
ledger postings, an immutable binding and an idempotency receipt.

Initial configurable prices are:

| Action | Crowns |
|---|---:|
| Create Team / relocate | 50 / 50 |
| Join Team on acceptance | 5 |
| Create Room / join Room | 5 / 2 |
| Buy one canonical hero / consumable | 100 / 5 |
| Neutral / owned Castle attack | 5 / 10 |
| Accepted Plan, per Team | 10 |
| Extra attack / Plan trial | 10 / 20 |

The Room creator is not charged a second join fee. Waiting Room fees are held,
captured once at full/Ready start, and released before start. Technical closure
refunds only the affected Room. Heartbeats renew Room and execution leases in
bounded batches. Leaving a running Room does not allow that account to bypass its
execution reservation while the battle is still active.

Initial limits are three attacks per player/day, three accepted initiating Plans
per Team/day, and up to two purchased extra trials of each kind. Members have a
20-Crown daily attack allowance unless the captain changes it or approves a
specific additional expense. Insufficient balance, quota or stale approval rolls
back the whole action. Fee and rule revisions are reviewed before spending.

Genuine Court battles retain hero XP 20/10/10 and Team XP 100/25/50 for
win/loss/draw. Personal battle Crowns are 10/0/5, capped at 50/day; repeated Plan
opponents on the same day do not generate repeat cash. Holdings yield five
Crowns per Castle/day, capped at 15 per Team, after an hour of ownership. A
Castle's daily receipt prevents transfer-based duplicate income. First distinct
story-scenario victories award 25 Crowns once per account/campaign/scenario.
Old or duplicate reports do not create new awards. Individual Rooms have no
persistent XP or cash reward.

The Competition entry pool is redistributed 70% to the winner and 30% to the
runner-up, with integer remainder assigned to the runner-up. Walkovers do not
mint XP or new reward cash. Cancellation without a surviving winner refunds the
entry pool. All new Team battles are unranked.

Healing draught restores 12 HP without cleansing; Remedy removes poison and slow.
An owned consumable is selected before Ready, held until use, and applied only to
the owner's living hero on their turn, at most once per battle. The native worker
verifies its use. Unused reservations are released and technical cancellations
refund consumed inventory. Items are available in supervised Court battles, not
unwitnessed individual Rooms or authored story campaigns. They are reachable by
the ordinary touch Actions menu.

## Authority, administration and retained data

`alliance/court/` owns the new collections and explicit player/admin operation
allowlists. The account bridge validates protocol-5 envelopes; service-only
native operations cannot be dispatched by players. Administrative changes require
an active administrator, CSRF, reviewed revisions, confirmation and reason.
Retired Company/old World mutation routes are unavailable in a Court game.
Existing user management, password reset, hero grants and campaign inspection
remain accessible through the current administration interface.

`Initialize-WindowsCourtGame.ps1` requires stopped services and a verified cold
backup matching the previous runtime. It creates `runtime-v3`, preserving
`runtime-v2`, its archive and connection identity. It neither deletes old data nor
imports old balances, accounts, heroes, Teams or battles. Interrupted setup is
resumable. A new administrator and new player accounts are required.

Campaign save/replay bytes, OBB, package identity, original signer, bundled public
profile, previous builds and recovery journals are preserved. Old signed-in
campaign saves remain on disk but cannot submit progression under the new
account/generation; begin a new campaign for new rewards. Old replays remain
available for local viewing. Isolated restoration supports the archived schema4
and the new schema5 runtime without replacing either active directory.

## Evidence and acceptance

Subsystem verification is recorded separately in the Court verification JSON
documents. Native protocol peers, actual native combat, native rendered fixtures,
browser layouts and Android compilation are distinct evidence categories; none
is labeled as Windows/LDPlayer or multiple-human acceptance. Follow
`COURT_WINDOWS_ACCEPTANCE_1192626.md` only after the coordinated release handoff.
Record WAN state once for that batch, stop at its first unexpected result, retain
reports and retest the correction plus affected regressions.
