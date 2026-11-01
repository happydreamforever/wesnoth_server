# Emerald Court 1192626

This coordinated client/server release replaces the former Company and strategic-round Team game with World, Areas, Castles, planned battles, knockout competitions and Crowns. The accepted Emerald Court theme, campaign combat and individual Rooms remain.

The mobile path is **Team → World → Area → Castle**. The supplied artwork defines 128 Areas, each with its own 60 normal, two Plan and two Competition Castles. Population rules and reviewed administrator overrides control activation. Teams have ten seats, a home Area, treasury, membership decisions and captain controls.

Normal Castles have verified native battles, consented computer defense and one-hour capture protection. Captains propose timed battles; administrators organize single-elimination competitions. Player reservations, quotas and transactional spending prevent overlapping claims or duplicate charges. Native workers preserve replay evidence and support same-account recovery.

Shop offers reviewed Crown requests, hero purchases and consumables. Personal and Team wallets distinguish available and held funds. Administrators approve requests once; no payment gateway or real-money collection is implemented. Prices, limits, activation, competitions and technical cancellation have reviewed administrator controls and audit records.

## Update boundary

- Android **1192626**, account protocol **5**, fresh game schema **5**.
- Initialize **runtime-v3** only after a verified cold backup of **runtime-v2**. This is the requested fresh game: previous player accounts, heroes, balances and Teams are not imported.
- The old runtime and backup remain an isolated recovery archive. No production database was reset on the VPS.
- Keep the existing Python 3.12.10, pinned tools, Android package/signer, public connection identity, OBB, local save/replay files, earlier build stages and recovery journals.
- Old campaign saves remain on disk but cannot earn rewards under a new account/database generation. Begin a new campaign for new progression; local replay viewing remains available.

## Verification evidence

The subsystem reports record actual tests, retained failures and evidence limits:

| Evidence | Report |
|---|---|
| Economy, administrator HTTP/layouts, fresh setup and recovery | [Economy verification](COURT_ECONOMY_VERIFICATION_1192626.json) |
| Team/Room transactions and real native protocol peers | [Team and Room verification](COURT_TEAM_ROOM_VERIFICATION_1192626.json) |
| Native AI, witness, reconnect, crash recovery, items and replays | [Battle verification](COURT_BATTLE_VERIFICATION_1192626.json) |
| Preserving Windows-worker build/recovery helpers | [Worker delivery verification](COURT_WORKER_DELIVERY_VERIFICATION_1192626.json) |
| Native touch layouts, map assets and offline Android APK | [Mobile verification](COURT_MOBILE_VERIFICATION_1192626.json) |
| Exact PowerShell handoff syntax and source review | [Handoff verification](COURT_HANDOFF_VERIFICATION_1192626.json) |

Native fixtures, authenticated companions, browser layouts and offline Android compilation are distinct from Windows/LDPlayer acceptance. A single LDPlayer cannot establish simultaneous multiple-human Room usability. The Windows checklist marks unsupported or unobserved checks NOT RUN instead of inferring a pass.

## Windows handoff

Follow [the ordered A–Z update and acceptance checklist](COURT_WINDOWS_ACCEPTANCE_1192626.md). It contains exact commands, expected markers, diagnostic paths, default prices and single-LDPlayer account sequences.

**Start with A only:** finish active play, save campaigns, Quit, and stop all five service windows normally with Ctrl+C. Report A before making the private backup. Do not manually delete MongoDB files or clear Android app data.

After the coordinated pulls, record WAN disconnection once while retaining local Ethernet. Stop at the first unexpected result; return its exact step and logs. Fix and retest that step and affected regressions, preserving unrelated accepted results.

The detailed rules and interface boundary are in [Implementation](COURT_IMPLEMENTATION_1192626.md) and [Protocol](COURT_PROTOCOL_1192626.md).
