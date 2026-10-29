# 1192624 mobile acceptance — I–Z

This is the Windows/LDPlayer acceptance checklist, not a claim that these checks
have passed. Complete the [coordinated A–H update](WORLD_ACCEPTANCE_1192624.md) first. Exact targeted recovery commands are in [WORLD_RECOVERY_ACCEPTANCE_1192624.md](WORLD_RECOVERY_ACCEPTANCE_1192624.md). Keep the five service
windows open and use the existing single LDPlayer instance. The battle service
starts its native worker; do not launch another copy of the Android app.

Carry the network state recorded once for this batch. Disconnecting WAN while
retaining the local network is different from disconnecting the required local
server. Report any change to that state. Never send passwords, runtime files,
private backups, machine tickets or session tokens.

Stop at the first unexpected result. Report the letter/substep, actual screen,
short error, account role, expected result and relevant saved diagnostic paths.
Keep the current saves, pending-action records and service logs. A failed command
must not be repeated with a new action identifier. If **Check pending action**
appears, it first checks the original server receipt; an explicit **Retry
original** reuses that same request. Do not remove its private journal.

Record PASS, FAIL or NOT RUN for each substep. A missing second eligible account,
missing advanced troop, unavailable wound, already-built Roadworks or unfinished
battle is NOT RUN, not a pass. Use actual earned heroes and soldiers. Do not alter
XP, ownership, clocks or database records to manufacture a test condition.

The accepted Emerald Court home remains the visual baseline. Historical 1192621
functional acceptance remains historical; its outstanding authored-campaign
reward/duplicate check N is not silently accepted by this new checklist. Preserve
and resume that check from the existing campaign saves separately. Company
expeditions are accessed from Team and do not replace the Campaign destination.

Workspace actions depend on the selected card and your role. If a named action
is not one of the two visible action buttons, open **Actions** to find it. A
disabled action is not permission to bypass its condition.

## I — Startup and existing account

**Accepted (2026-10-29):** The user reports I1, I2 and I3 PASS. This includes H's outstanding visible startup confirmation. Numerical account/hero values were not supplied and remain unrecorded; send the actual current values with the next report. Do not substitute historical examples. Keep the five services open and use the existing player account.

1. Open the game. Confirm the existing Emerald loading, Login and home remain
   intact, with no profile import. Sign in to the existing player.
2. Check the same account name, owned-character count, campaign saves and actual
   hero/form/level/XP values. Write down the current values for later comparison.
3. Enter Team. Confirm **World**, **Company**, **Battles**, **History**, **Roster**,
   **Team settings** (or **Find a team**) and **Back** are reachable by tap.

Expected: no new account, reset, altered home or automatic reward. An account
without a Team can still open its personal Company. It cannot issue Team orders. Its
Roster control is disabled and Team settings becomes **Find a team**; record
member-only inspection as NOT RUN rather than joining a Team for this check.
Inspect existing saves in the Load list without starting or overwriting them.
Record current hero/form/level/XP values rather than substituting historical
examples. Leave enlistment, recruitment, world enrollment and battles for later
steps.

## Current batch after I: prerequisite order

J2 requires soldiers, so run **K1–K2 → J1–J2 → K3** in this batch:

1. **K1–K2:** Team → Company → Enlist company, only if not already initialized
   and an earned hero is owned. Confirm the six-soldier grant, reopen/refresh and
   verify it is not repeated. An existing Company keeps its actual roster.
2. **J1–J2:** Visit World, Company, Battles and History using taps. In Company,
   search **Spearman** (or another existing soldier), select its card, tap Refresh
   and wait about ten seconds through a periodic update. Search, selection and
   the open workspace must remain stable. Clear search afterward. Check tap
   scrolling where content overflows; otherwise report that the list fits.
3. **K3:** Inspect the selected soldier's statistics, then Recruit → Spearman →
   Recruit once. Count the unfiltered roster: a fresh Company goes **6 → 7**, with
   two Spearmen. For an existing Company, use its actual starting count plus one.
   Existing soldiers' XP and the account's hero progress must remain unchanged.

No earned hero: Campaign guidance is expected; enlistment/search/recruitment
dependent on a roster are NOT RUN. At twelve soldiers, verify recruitment is
unavailable and mark the K3 addition NOT RUN. Do not retire anyone to make space.
K4 retirement and J3 World controls are deferred. Force selection, world
enrollment and battles remain later checks.

Return K1/K2/J1/J2/K3 PASS, FAIL or NOT RUN, the final soldier count and the actual
account name, owned-character count, hero/form/level/current XP/total earned XP.
Stop at the first unexpected result and retain the exact screen/error. No new
build, installation or service restart is required. The existing WAN status
continues to apply unless the user reports a change.

## J — Persistent touch workspace

1. Visit all four tabs and return without changing data. Tap the list scrollbar's
   track or arrows; no keyboard shortcut, hover or drag operation is required.
2. In Company, search for an existing soldier and tap its card. Tap **Refresh**
   and wait about ten seconds through a periodic update. The search and selected card remain; the window does not
   repeatedly close and reopen. Clear the search.
3. Once O has opened the world, revisit World: tap each Castle, **+**, **−**,
   **Centre**, **List**, and **Map**. Centre restores all six Castles. Routes and
   Area boundaries stay geographical when Castle ownership later changes.

Expected: readable Emerald panels, clear selected tab, unclipped controls,
48-reference-pixel or larger action targets, and matching map/list selection.
J3 is NOT RUN until a world exists.

## K — First Company and permanent soldiers

1. With an owned hero, open Company and choose **Enlist company** once. Review
   the grant before confirming. Return/reopen and refresh.
2. Expect one Spearman, Bowman, Dwarvish Fighter, Elvish Shaman, Cavalryman and
   Mage. Existing initialized companies must retain their actual roster instead
   of receiving the grant again.
3. Inspect a soldier's native level, XP, health, movement and attacks. Use the
   visible **Recruit** button to recruit one basic soldier into an empty slot.
   Confirm the roster count increases by exactly one and existing XP is retained.
4. If a healthy, uncommitted, unselected disposable basic soldier is available, use
   **Actions → Retire soldier**, cancel once, then confirm only if you intend to
   retire it. Cancellation preserves it; confirmation removes that soldier with
   no sale/refund. Do not retire your earned advanced soldiers merely for testing.

Expected: basic mixed-faction recruitment only, maximum 12 permanent soldiers,
no trait reroll or advanced-unit purchase. At capacity Recruit is disabled. An
account with no earned hero instead gets **Campaign** guidance; verify that case
only with an existing suitable account, otherwise record NOT RUN.

## L — Choose company and bracket

1. Tap **Choose company**. Select an owned hero/form, then zero to four healthy
   soldiers. Page with **Previous** and **Next**; selections must survive paging. The four-slot deployment tray shows selected
   soldiers and empty spaces. Tap a filled slot to remove that selection, then
   select the soldier again; this edits only the unsaved draft.
2. Inspect Scout/Veteran/Champion using **Force bracket**. The point budget,
   effective hero level and tier restrictions must match the reviewed force.
   Invalid selections explain why **Save company** is unavailable.
3. Cancel with **Back** and verify the server selection did not change. Reopen,
   make a valid selection and use **Save company**. The Company summary shows
   the saved hero, bracket and soldier count.
4. If a soldier has a branching path, use **Actions → Advancement choices** and
   save its chosen native branch. This is a future AI advancement preference,
   not an immediate level or XP grant.

Expected: one hero, at most four different soldiers, no wounded/committed troop
in a new force, and no loss of collection XP when a bracket caps effective level.
Advanced-tier and exact budget-boundary checks remain NOT RUN until legitimately
available. Do not claim them from a level-1 force alone.

## M — Company expedition and native play

1. Record the selected hero and soldiers' current XP/types, Team XP/rating/Supply.
2. Choose visible **Expeditions**, review an available mission and tap
   **Start expedition**. Use a different mission on a later test, not concurrent
   copies of the same Company.
3. Battles shows **Queued** while waiting for the worker. When it becomes
   **Preparing**, tap **Enter battle**. Do not repeatedly submit Start expedition.
4. In the actual native map, recall selected personal soldiers using the normal
   recall control (20 tactical gold each), make legal moves/attacks, and observe
   enemy AI play. Temporary recruits must remain distinguishable from persistent
   company members by the final roster.
5. Finish the expedition normally. Save any local game/replay offered by the
   engine without replacing existing story saves.

Expected: real native combat; no synthetic outcome button, no permanent temporary
recruits, no Team XP/rating/Supply from PvE. Merely entering or closing a battle
must not grant a victory. Record the actual outcome rather than forcing a win.

## N — Return report, wounds and duplicate viewing

1. Open History and the completed expedition. Inspect the result, your hero XP,
   each soldier's earned XP/final type, and any wound/recovery status.
2. Reopen Company and My Heroes to compare with the pre-battle values. Victory
   awards 20 hero XP; defeat awards none. Verified native soldier XP and
   advancement persist. Native survivors recover ordinary HP between battles.
3. Refresh and reopen the same History result several times, then use
   **Watch replay**. XP and roster counts must stay unchanged by viewing.
4. If this battle produced nonterritorial wounds, tap visible **Rest**, review
   and confirm. Eligible wounds clear for free; accumulated XP/forms remain.
   If there are no wounds, Rest is disabled with the recovery condition visible.

Expected: one receipt and one settlement, read-only replay/history, and no reset
of soldier progression. Without an actual wound, the recovery mutation is NOT RUN.
Viewing checks do not substitute for backend concurrent-settlement evidence.

## O — Host world and enrollment

This step uses the Windows host browser, not a player privilege.

1. Open `http://127.0.0.1:18765/world` and sign in as the existing administrator.
   If no world exists, select two distinct existing founding Teams for Dawnreach
   and Mistvale, confirm the choices, and choose **Open world** once.
2. If a world already exists, inspect it; do not bootstrap a replacement.
3. Confirm each founding Team owns its capital and frontier; both supply Castles
   start neutral. Each founding treasury starts at 20 Supply only on the original
   bootstrap. An existing treasury must retain its actual value.
4. On the player, World → **Enter world** enrolls this player's Company with its
   current Team. Inspect the displayed station and the six-Castle map; finish J3.

Expected: two fixed geographical Areas, three Castles each, triangle routes and
one frontier-to-frontier route. Administrative Areas and existing Team IDs are
preserved. Additional Team enrollment in the host page grants no land or Supply.
If two suitable Teams do not exist, stop here for preparation guidance.

## P — Stationing, captain and governor

1. In planning, select a friendly adjacent Castle and choose **Station company**.
   Review the order. The host's **Apply deployment orders** applies deployment;
   compare the player's station after Refresh. This is not a teleport or attack.
2. As captain, open the Castle's **Actions → Appoint governor** and choose an
   eligible current member. An ordinary member must not gain captain actions.
3. With that governor account, **Propose Roadworks** sends a proposal without
   spending Supply. The captain reviews **Approve Roadworks** (or
   **Build Roadworks**) and the 15-Supply confirmation.
4. If intentionally purchased, exactly 15 Supply is deducted once and the Castle
   shows Roadworks. Reopening must not charge again. A two-edge friendly move
   needs a qualifying improved origin/destination and enough actual friendly
   Castles; record NOT RUN until that route exists.

Expected: governors propose/organize; only the captain spends or appoints. No one
can deploy another player's Company without that owner's consent.

## Q — First neutral Castle contest

1. In planning or deployment, use a friendly adjacent origin and select
   its neutral supply Castle. As captain choose **Plan attack**, inspect the
   origin and bracket, and confirm the proposal once.
2. In Battles inspect the fixed company and settings. The participating human
   chooses **Ready**; the captain chooses **Approve agreement** after review.
3. The host progresses deliberately: **Apply deployment orders → Lock
   engagements → Open tactical battles**. If P already applied deployment,
   continue from **Lock engagements** in the same round. Each control performs
   one global phase transition; refresh the browser between transitions. Resolve
   any missing consent before proceeding rather than clicking through errors.
4. Enter only when Preparing, play the native contest and report its actual
   result. A win captures only that Castle. A loss/cancel does not transfer land.

Expected: one attacking engagement per Team and one territorial engagement per
Company in the round. First successful neutral occupation grants its one-time
hero/Team bonus; a later repeat occupation must not create another first bonus.
Do not manufacture repeated captures just to mark this optional check passed.

## R — Human defense and captain-approved Area war

Requires a second eligible opposing account, operated by a separate human or the
explicitly authenticated companion described in the main delivery guide. After
Q, finish the settlement and next-round controls in V before proposing a new
territorial engagement; do not try to reuse a Company in its completed round.
With one LDPlayer, use the existing accounts sequentially to review their own
Company, join, Ready and captain approval. Then start the separate account
companion for its prepared seat and return LDPlayer to your playing account.
The companion does not perform those consent steps for the player.

1. As a captain open World → **Actions → Area wars → Propose Area war**. Select
   the opposing Team. Tap one or more Castle objectives; optionally select an
   Area-control objective. **Review agreement** shows the exact targets.
2. Cancel the review once and confirm no proposal was sent. Recreate and
   **Propose war** only when both sides intend this test. Before the opposing
   captain approves, test **Withdraw proposal** or **Decline proposal** if both
   sides agree: cancellation stays in Area wars and changes no territory. Then
   create a new intended proposal. The opposing captain reviews and chooses
   **Approve agreement**. Only this active agreement permits its occupied targets
   to commit; active wars have no cancellation action.
3. Create an eligible adjacent attack in a planning round. Each human Company
   joins its own side using **Join with my company**, reviews the displayed
   force/rules, then selects **Ready**. Each required captain approves.
4. Before commitment, change a material Company/lineup condition through its
   permitted control and verify stale consent is rejected/cleared. Review and
   renew consent before the host locks the engagement.

Expected: no silent human-to-AI replacement, no attack outside agreed targets,
and no Castle forfeiture merely because a human is missing. With one LDPlayer,
sequential account consent is not evidence of simultaneous human gameplay.

## S — Standing computer defense and withdrawal

1. On a defender's friendly Castle, choose **Offer defense**. Review the exact
   hero, soldiers, bracket and advancement preferences. Only that owner can
   consent. A noncaptain's offer waits for the captain to use **Defense
   assignments → Review → Approve defense**. A captain's own newly offered
   Company is active immediately: the confirmed offer supplies both owner and
   captain consent. No separate approval click is needed for that new offer.
   If an existing offered/needs-review permission belongs to the current captain,
   its review allows **Approve defense** or **Withdraw defense**, followed by a
   separate confirmation; test that case only when it legitimately exists.
2. Reopen **My standing defense** and verify it remains active until withdrawal.
   Before any commitment, choose **Withdraw**; the Company becomes available
   without loss of troops/XP. Offer and approve again only for the next test.
3. With the owner away from the game, an eligible captain-approved war/attack
   may commit this standing defense. The Windows native worker executes its AI.
4. Request withdrawal while committed. Expect pending release, not an immediate
   controller switch or reuse of the same assets in another battle.
5. If enough distinct eligible owners are available, inspect the displayed
   defense capacity. A fifth offered company must stay pending when four
   permissions already reserve capacity; it must not silently replace one.
   Otherwise record this capacity case NOT RUN.

Expected: owner consent and captain authorization are both necessary. Advancement
beyond the approved bracket requires force review; test this only if legitimate
progress produces it. No silent downgrade/substitution is acceptable.

## T — Preparation queue and reconnect

1. With a real eligible contract, observe Queued before a worker/tactical window
   is available. Five-minute preparation must not expire merely while queued.
2. Once Preparing, all required human clients load the same battle before play.
   Missing attendance must not award a win or transfer a Castle.
3. During actual play, use the recovery guide's targeted interrupted-app test
   to disconnect only the required mobile client. Expect a pause, no simulated
   victory and no silent AI takeover. This is an app-disconnection test, not a
   claim that Android showed a live network-error warning. Reopen the game and
   log in as the same account; use **Resume battle**. WAN disconnection alone must not force logout.
4. Worker interruption/recovery and preparation timeout tests need the explicit
   retained-checkpoint procedure from the main guide. Do not kill arbitrary
   processes, delete locks, or invent a restart command.

Expected: fixed controller identity, continued synchronized state and one outcome.
If no second authenticated participant is available, multiplayer load/reconnect
checks remain NOT RUN; a single local expedition does not prove them.

## U — Concurrent Companies and exclusions

1. With different eligible owners, arrange disjoint contracts through the
   approved companion workflow. The default one-worker configuration may queue
   the second even though the assets are independently reserved.
2. Attempt to reuse an already committed hero/soldier/owner in another persistent
   deployment. It must be unavailable or rejected without changing the first run.
3. Cancel only an eligible waiting proposal through **Cancel proposal**, or the
   host's explicit **Cancel engagement** with a reason. The other engagement,
   its Company and its result must remain unchanged.

Expected: player/asset/Castle reservations, not team-wide exclusivity. Multiple
worker execution is NOT RUN unless the documented worker configuration and
separately authenticated owners are actually used.

## V — Territorial result and next global round

1. Inspect the completed Castle result in History and the host's Castle list.
   On capture, only that target changes owner; its building remains, former
   governor and standing permissions end, and the geographical Area is unchanged.
2. Compare actual hero and soldier returns, Team XP and rating. Player-owned
   contests award 20/10/10 hero XP and 100/25/50 Team XP for win/loss/draw;
   territorial contests do not award Elo rating. Neutral first occupation follows
   its separate one-time rule.
3. If territorial wounds exist, **Rest** cannot clear them early. The host can
   **Review round settlement**, then **Begin next round** only once engagements
   are settled or explicitly cancelled. Due territorial wounds then recover.
4. Review qualifying Supply production at the completed boundary. Peaceful or
   PvE-only rounds do not generate Supply; clock changes, downtime and reopening
   do not advance the round. Never edit Windows time for this check.

Expected: exactly one settlement, additive XP, no duplicate first-capture bonus,
and no same-round capture chain/redeployment. Record actual receipts and values.

## W — War resolution and landless recovery

1. Continue an approved Area war through legitimate rounds only as needed. The
   host closes each round after resolving its engagements. Inspect **Area wars**
   for the final outcome/title at early declared control or the three-round limit.
2. A tied result remains a draw; unplayed Castles do not transfer and the war
   itself does not duplicate individual battle rewards.
3. If normal play actually removes a Team's last Castle, inspect its **Recovery
   camp** station and fixed homeland-frontier return option. Otherwise mark this
   branch NOT RUN. Do not surrender/delete a Team merely to create this state.
4. A later Team change requires releasing old commitments and explicit new
   enrollment; personal soldier ownership/XP persists and grants no new land.

Expected: evacuation/landless recovery follows actual topology and the permanent
return objective. Team recreation is not a source of free land or Supply.

## X — Existing skirmishes with personal Companies

1. Battles → **Skirmishes** or **New skirmish** retains the existing plan editor.
   For a draft that has not prepared, a captain may choose **Use personal
   companies** and review its confirmation.
2. Confirm only on a plan intended for this check. The original draft becomes
   inactive history; the new Company contract requires fresh joins/readiness and
   captain approvals. It must not also auto-start the original native plan.
3. Complete the real Company skirmish. If it awaits captain confirmation,
   **Confirm result** displays the verified native outcome; both captains confirm
   before the existing skirmish permanent rewards settle.

Expected: custom/unranked Company skirmish, persistent native soldier returns,
existing hero/Team outcome amounts, and no double settlement or second live plan.
Ordinary individual Rooms keep their existing no-permanent-progression policy.

## Y — History, reports and authorization

1. Current Team members inspect completed/cancelled battle records and available
   **Watch replay** actions. **Older history** and **Latest history** retain the
   selected page during refresh; search must not rewrite any record.
2. If an actual recorded participant/captain later leaves a Team, verify access
   to that person's historical result/replay. An unrelated account must not gain
   access by copying an identifier into companion tooling.
3. Open an existing pre-update replay/save through Load without converting or
   overwriting it. Check the same campaign checkpoint and current hero values.
4. Repeated report/replay viewing changes no XP, wounds, ownership, rating or
   Supply. Report missing authorization cases as NOT RUN if no suitable account
   is available; do not create synthetic historical records.

## Z — Quit, persistence and report

1. Return home and **Quit**. The task closes; reopening requires Login. After
   signing in, compare Company soldiers/selection/preferences, owned heroes,
   Team/World state and historical results with the last recorded values.
2. Use only the main guide's coordinated stop/restart procedure to verify server
   persistence; never start competing copies against the same runtime.
3. Isolated backup restoration uses a separate destination under the maintenance
   guide. Never replace the live runtime to run a recovery test.
4. Send the I–Z PASS/FAIL/NOT RUN record, actual successful outcomes and the first
   unexpected result's diagnostic locations. State whether each multiplayer case
   used a second human or a separately authenticated companion. Do not describe
   companion evidence as multiple-human mobile acceptance.

After a fix, retest the failed substep and its affected regressions only. Keep
unrelated accepted results, campaign progress and the original recovery records.
