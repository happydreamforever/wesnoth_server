# Unified game implementation and acceptance

Release **1192619** includes the unified product, startup/input/session corrections and global individual battle rooms. The schema is 2 and the account/native protocol is 2. Windows/LDPlayer acceptance uses the combined A–Z in [NEXT_TEST.md](NEXT_TEST.md); it is not inferred from VPS tests. The individual-room implementation and evidence are in [INDIVIDUAL_BATTLES.md](INDIVIDUAL_BATTLES.md) and [VERIFICATION_1192619.json](VERIFICATION_1192619.json).

## Player flow

Start the game, sign up or log in once, then use **Campaigns, Heroes, Multiplayer and Teams** with the same account. New players have an empty hero collection. There is no starter choice and no second Alliance login. The saved trusted Windows connection remains in the existing Android application.

In **Campaigns -> Story campaigns**, play the supplied stories with their normal characters, objectives and authored strength. A confirmed victory unlocks the eligible named heroes who participated and their earned forms. Ordinary recruits remain part of that campaign save. The same canonical character shares progress across stories; distinct characters such as Konrad and KonradII remain distinct. The reviewed catalogue contains 117 heroes and 346 forms across 21 story campaign IDs (including both Deceivers' Gambit parts). World Conquest is ordinary multiplayer content, not a registered story reward source.

Each owned hero has permanent experience and level, shared by its forms. At level L the next level costs `5L² + 15`XP. Multiplayer, team battles and Hero training apply 2% of baseHP and 1% of base damage per strike for each additional permanent level, rounded half upward. Native unit tier, movement, number of strikes, resistances and innate abilities stay unchanged. Rounding means a particular attack need not gain a point at every level. Story playthroughs retain their original stats and progression. There is no designed level cap; arithmetic and storage bounds are checked.

A story victory credits actual combat and reviewed explicit scriptedXP plus 20 XP to each eligible participating hero. Defeat awards no permanentXP or unlocks. Saves, scenario checkpoints, recalls, branches and pending results are bound to the account, database generation and playthrough. A completed checkpoint is immutable and repeated delivery awards nothing. Each scenario grants XP once per playthrough; a legitimate later visit can unlock newly earned eligible heroes/forms without repeating its XP. A genuinely new playthrough can earn XP again. Pending results survive a temporary service outage and retry in order.

**Campaigns -> Hero training** integrates the three former progression missions into the same account and hero collection. Choose an owned hero/form. A confirmed training victory gives 20 XP to that hero only; local team practice gives no persistent rewards.

**Multiplayer** opens the native trusted lobby with the startup account. Maps, recruitment, turn flow, saves and computer opponents use the existing engine. Select an owned hero/form before Ready. One-use account tickets and pinned TLS replace guest nickname admission. Ordinary multiplayer gives no permanentXP or rating. Saved games retain their frozen hero and combat state when resumed.

**Individual rooms** are public standalone map battles in the Multiplayer dashboard, independent of permanent Teams/areas. Choose map, limits, gold and other reviewed rules; browse/filter live rooms and review before joining. Select an owned hero/form and explicitly Ready. Start is automatic only when all configured seats are filled and every player is Ready for the current revision. Settings, hero and membership changes invalidate consent. Standard manual/AI/saved multiplayer remains available. Individual battles grant no permanent XP/rating.

**Teams** keeps areas, captains, applications, orders and 2v2/3v3/4v4 plans. Each selected player chooses an owned hero/form before Ready. A selection change clears every Ready flag and both captain approvals. Individual practice needs your own Ready and both approvals; a shared battle needs all selected players Ready and both approvals. Shared admission, reconnect, captain surrender/draw, result agreement and replays use the selected immutable heroes. Only those heroes receive the battle's permanentXP. Other heroes in the account remain unchanged.

## Implementation checklist

- [x] Versioned hero catalogue and explicit story identities/forms.
- [x] Owned-hero schema, XP math including BSON Int64, generation binding and selected-hero settlements.
- [x] Startup authentication and unified menus without repeated login.
- [x] Story XP ledger, account-bound saves/recalls/branches and durable victory delivery.
- [x] Portable multiplayer hero definitions and level scaling.
- [x] Hero choice before Ready in fixed plans and ordinary multiplayer.
- [x] Strict-TLS native lobby admission through single-use account tickets.
- [x] Admin hero inspection/correction, fresh database and verified recovery.
- [x] Versioned Android/native delivery and checked five-service startup.
- [x] Final corrected Android build and preserved-artifact verification.
- [x] Coordinated implementation commits; delivery to both main branches.
- [ ] Actual Windows/LDPlayer functional acceptance from returned A–Z results.

## Database and preservation

After a verified private cold backup, the fresh-start helper creates schema 2 at `%LOCALAPPDATA%\WesnothAlliance\runtime-v2` and asks for a new administrator. It retains the old runtime and backup; old accounts and teams are not silently migrated or assigned to new users. Repeating a completed fresh initialization must keep the newly created database and progress. Routine later fixes do not repeat this fresh-start step.

The five services are MongoDB 27018, local admin 18765, account bridge 15001, shared teams 15002 and authenticated native multiplayer 15000. The supplied 1.19.26 game data/OBB, MSYS2, pinned dependencies and trusted identity stay in use. The internet MongoDB URL in `.env` is unused.

## Verification and remaining acceptance

VPS checks cover actual MongoDB transactions, native TLS protocols, the real game engine, shared battles/reconnect/settlement/replays, all 346 portable forms at four levels, and production UI controllers with scripted boundaries. Story engine fixtures exercise actual combat/advancement/save/replay behavior against a controlled HTTP boundary; separate backend tests exercise real persistence and reward transactions. They do not represent full playthroughs of every story, Windows execution or Android rendering. Detailed evidence is recorded in [BASELINE.md](BASELINE.md) and [VERIFICATION_1192617.json](VERIFICATION_1192617.json).

The local server enforces identity, owned selections, run/turn order and settlement rules. It does not independently simulate every combat action or provide a hostile-public-client anti-cheat system. The current product is the agreed full-strength local game.

## Report, fix and retest

Use the existing one LDPlayer instance. Record WAN status once per batch, retaining local Ethernet. Each A–Z step has an exact command or UI action, expected result and relevant report. At the first unexpected result, keep the existing state and send that step's message/log. We reproduce it on the VPS, fix and verify the affected behavior, commit/push, then give the exact pull/build/run commands and retest scope. Keep unrelated accepted results. Computer-controlled companion seats do not establish multiple-human usability.
