# Emerald Court — Companies, Castles and Territorial Wars

Status: implementation and VPS verification complete; Windows dependency inventory and A-Z acceptance pending. Client 1192624, account protocol 4, schema 4 in the existing runtime-v2. See VERIFICATION_1192624.json for evidence and scope. Do not migrate Windows until the installed full-engine dependency audit passes.

## Approved product rules

- Preserve the accepted Emerald Court home and artwork. Team becomes a persistent
  touch workspace: World, Company, Battles, History; Roster and captain management
  remain available. No required hovering, hotkeys, drag or long press.
- One host-created world: two geographical Areas, each a capital, frontier and
  supply Castle connected as a triangle; frontiers connect across Areas.
- Geographical Areas are new records, never a reinterpretation of administrative
  Areas. Host selects two existing founding Teams; each initially owns its capital
  and frontier, while supply towns are neutral. Enrollment/bootstrap happens once.
- A Team controls an Area when it owns the capital and at least two of its three
  Castles. Capture transfers only the target, retaining buildings/history while
  clearing governor and former defense permissions. Land belongs to Teams;
  soldiers belong to players. Captains approve commitments/spending; governors
  organize defense/propose improvements, never deploy another owner's troops.
- First legitimate campaign hero unlocks Company. Enlist once grants one each of
  Spearman, Bowman, Dwarvish Fighter, Elvish Shaman, Cavalryman, Mage. Free basic
  recruitment from these six types into empty slots, maximum 12. No trait rerolls,
  advanced purchases, trade/sale/refunds. Only healthy uncommitted troops retire.
- Expedition force: one owned hero, zero to four personal soldiers. Soldiers use
  native recall at 20 tactical gold; temporary recruits remain temporary. Native
  XP/advancement events persist; terminal units do not gain unlimited AMLA stats.
  Offline advancement follows each owner's approved branch preferences.
- Three Company expeditions adapt Border Patrol, The River Crossing and The Old
  Fortress. They do not rewrite authored story campaigns or restore Hero training.

| Bracket | Company points | Max hero tier | Max soldier tier | Effective hero level cap |
| --- | ---: | ---: | ---: | ---: |
| Scout | 120 | 2 | 1 | 5 |
| Veteran | 240 | 3 | 3 | 15 |
| Champion | 420 | 5 | 4 | 30 |

Soldier points equal pinned native form cost. Hero base is
max(native cost, 20 * max(1, native tier)); points are the ceiling of
base * (100 + 2*(L-1)) * (100 + L-1) / 10000, with L capped by bracket.
Both sides use the same bracket. Actual collection XP/forms are unchanged.
Balance values are provisional versioned rules, not proven equivalence.

- Company victory grants 20 hero XP, defeat none; actual soldier XP persists.
  Company grants no Team XP/rating/Supply. Army skirmishes are custom/unranked,
  retain current hero/Team reward amounts and add approved soldier XP.
- Player-owned Castle battles grant hero XP 20/10/10 and Team XP 100/25/50 for
  win/loss/draw, no rating. Neutral first occupation grants 20 per participating
  hero and 100 Team XP once per Castle; no repeat bonus. Individual Rooms award
  no persistent army progression, wounds or territorial changes.
- Fallen personal heroes/soldiers retain progression. Nonterritorial wounds are
  cleared by free Rest after settlement. Territorial wounds recover only at the
  next host-authorized world-round boundary. Rest/recruit/reassignment/story
  rewards cannot bypass them. Survivors recover ordinary HP between games.
- Story campaigns retain authored units and their current rewards. Story XP may
  increase the live collection while a battle uses its immutable earlier snapshot.

## Rounds, authorization and evidence

- One persisted world round shared by all wars: planning, deployment, commitment,
  tactical engagements, settlement. One attacking engagement per Team and one
  territorial engagement per owner/company per round, including delegated defense.
- Normal stationing moves one friendly edge. Attack adjacent hostile/neutral
  targets from friendly origins. Freeze every contract before the first battle;
  capture cannot produce a same-round chain attack or redeployment.
- Separate Castle reservation, round participation, personal asset locks and
  active account execution leases. Disjoint contests can run concurrently.
- Five-minute preparation starts only when a tactical window/worker is available.
  Advance the global round only after all engagements settle or are explicitly
  cancelled. Peaceful rounds permit recovery but no income/XP. Clocks/downtime
  never advance strategic time or award ownership.
- Area wars span at most three global rounds, with captain-approved target sets
  and objectives. Evaluate only at completed round boundaries. Early declared
  Area control wins; otherwise capital scores 2, other targets 1, tie draws.
  War awards history/title, not unplayed land or duplicate battle rewards.
- Standing AI defense needs Castle captain authorization AND owner consent for
  exact hero/soldiers, bracket and advancement preferences; it lasts until
  withdrawn. Unlocked withdrawal is immediate; locked withdrawal queues release.
  Fresh progression is frozen at commitment. An outgrown bracket becomes Needs
  force review, without silent substitution, downgrade or broadened consent.
- Delegated assets cannot also deploy persistently elsewhere. Owners may opt to
  defend personally before commitment; locked controller identity never switches
  implicitly. Missing human consent/attendance never forfeits a Castle.
- Capture ends old standing assignments; evacuate to the nearest friendly Castle
  by route distance, stable Castle-ID tie break, otherwise recovery camp. No extra
  movement/engagement entitlement or confiscation. Landless camp has an explicit
  attack edge only to the enrollment's fixed homeland frontier; normal consent
  and round limits still apply. Team recreation grants no new land or resources.
- Movement, attacks, defense and recovery cost no Supply. Initial Team Supply 20,
  cap 40. Combat-containing settled rounds produce capital/frontier/town 2/1/2,
  Team max 6. Disconnected from every friendly capital: half rounded down.
  Peaceful/PvE-only rounds and instant surrender/cancel grant no production.
  Qualifying production needs verified combat and one completed tactical round.
- Roadworks costs 15, bought atomically at current ownership. Allows one move
  across two friendly edges when improved Castle is origin/destination, no extra
  orders/attacks/stats/healing. Building survives capture; no refund; treasury
  remains with its Team.
- Existing battle service supervises a new full native Windows engine worker,
  default one active child with queued contests; configurable disjoint workers.
  It controls only assigned AI and witnesses the complete native command stream;
  human-only World battles use noncontrolling witness mode.
- Worker tickets are scoped machine authority, never volunteer credentials.
  Durable checkpoints, contiguous generation-bound commands, native terminal
  outcome, replay and troop ledger are required. Failure pauses, never wins.
  Complete worker evidence can settle despite withheld human upload; incomplete
  or conflicting evidence cannot settle. Old Team captain confirmation remains.
- Settlement is one Mongo transaction for receipt, progression, wounds, release,
  target ownership, permissions, Area control and history. Duplicate returns the
  same receipt. Add concurrent rewards to live XP rather than snapshot overwrite.

## Implementation and verification checklist

- [x] Company catalogue/model, recruitment, branches, brackets, wounds and ledger.
- [x] World/Area/Castle enrollment, permissions, movement, Supply and development.
- [x] Standing defense, wars, round scheduler, reservations and atomic settlement.
- [x] Native World/Company scenarios, worker/witness, AI, replay and reconnect.
- [x] Persistent mobile Team workspace, in-place refresh, conflict handling,
      return reports, 48 logical-unit targets, safe areas and no-Team/zero-hero states.
      Physical Android density/touch acceptance remains in the Windows checklist.
- [x] Protocol 4 backend, bridge, native client and worker interfaces together.
- [x] Resumable preserving schema 3-to-4 migration; cold backup and legacy restore.
- [x] Isolated MINGW64 worker dependency/DLL inventory and offline build tooling.
- [x] Real Mongo concurrency, native combat, worker failure/terminal evidence,
      replay authorization, clock/round and migration-interruption checks.
- [x] Actual GUI2 renders at 1280x720/1920x1080 with touch-role flows.
- [x] Offline Android build and independent package/version/original-signer check.
- [x] Preservation inventories for sources, OBB, signer, prior builds/journals,
      existing saves/runtime identity and unrelated README edits.
- [x] One coordinated Windows A-Z batch with exact commands, expectations and
      diagnostic paths. Single LDPlayer plus worker/authenticated companions,
      never described as multiple-human acceptance. WAN recorded once per batch.

Commit in coherent company, world, worker, UI and migration/delivery stages.
Stop Windows acceptance on first unexpected result; preserve logs, reproduce/fix
on VPS, retest the affected step/regressions without repeating accepted work.

## Remaining Windows gates

- [ ] Actual installed MINGW64 dependency inventory; prepare any missing pinned packages before the offline batch.
- [ ] Actual Windows full-engine worker compilation and DLL execution.
- [ ] A-Z Windows/LDPlayer acceptance, reported one group at a time.

The checked implementation items above are VPS/source evidence, not acceptance of the unchecked Windows gates. Native command validation is bounded; this release does not claim complete modified-client anti-cheat.
