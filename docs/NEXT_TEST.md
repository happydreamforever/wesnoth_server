# Windows / LDPlayer acceptance — interface 1192620

**Current progress (2026-10-24):** A's repository update and B's Windows Android1192620 rebuild are accepted. All45 native steps,33 Gradle tasks and package/original-signer checks passed; both prior stages were preserved. The user confirms WAN was disconnected with local Ethernet retained. Continue at **C** using the existing server67c31a6 checkout and runtime-v2; keep WAN disconnected/Ethernet connected. Return checked five-service startup before D installation. This documentation record needs no additional pull or rebuild. C–Z Windows/LDPlayer acceptance remains pending.

Restart the visible product tests with this checklist. Your completed 1192619 native server build, Android build and verified runtime-v2 backup remain accepted; the corrected five-service startup and later 1192619 installation/gameplay were not yet accepted. This update rebuilds Android only and preserves the completed 1192619 account stages, existing accounts/heroes/teams, trusted profile, OBB and pinned dependencies. It does not initialize or migrate a database.

Use the existing single LDPlayer. Record WAN status once after the pulls: disconnect internet/WAN while keeping local Ethernet connected. Continue until the first unexpected result, then send that step, expected/actual behavior and its saved diagnostic log. Keep passwords, tokens, private runtime files and backups locally. VPS checks do not establish Windows acceptance.

## A. Save, stop and update

Save/leave any game and quit the app. Stop any companion, then the multiplayer, shared-battle, account-bridge, admin and database windows with Ctrl+C; wait for their prompts. Temporarily connect to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit." }
    }
}
```

Expect successful updates and both commits. This includes the previously delivered server startup-check correction. Preserve local README edits; do not reset if a merge is refused. Disconnect WAN/retain Ethernet. Keep services stopped through B. The private `before-1192619-20261023-221741-136` backup remains retained; this UI-only update needs no repeated backup or native server/bridge build.

## B. Build Android 1192620

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send the saved rebuild and build logs.' }
}
```

Expect preserved previous account stages, ANDROID ACCOUNT ENGINE BUILD PASS, ANDROID ACCOUNT GAME BUILD PASS and ANDROID ACCOUNT GAME REBUILD COMPLETE. Keep interrupted stages/journals intact if it stops. Existing Java8/deprecated-API and unused CMake-option warnings are nonfatal. Continue with C before installation.

## C. Start the existing five services

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles
    if ($LASTEXITCODE -ne 0) { throw 'Startup stopped. Send the workflow text and JSON reports.' }
}
```

Expect W02–W06 PASS followed by W07 UNIFIED GAME SERVICES READY: MongoDB27018, admin18765, account bridge15001, shared Teams15002 and native Multiplayer15000. Keep all five windows open. Use runtime-v2, not the historical runtime folder.

## D. Install and retain trust

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Send the saved install log.' }
}
```

Expect ANDROID ACCOUNT GAME INSTALL COMPLETE, version1192620, and the existing Trusted server100.99.99.14:15001 plus Start game. Report missing/unusable trust without reimporting or resetting. No OBB transfer is required.

## E–H. Welcome, keyboard, heroes and navigation

| Step | Action | Expected |
| --- | --- | --- |
| E — Welcome | Start game; open Log in then Cancel; open Sign up then Cancel. | Only Log in, Sign up and Quit on Welcome; the previous modal is gone before credentials open. No usable main menu while signed out. |
| F — keyboard | Enable Show password and type harmless `aAzZ1!`; exercise Shift/Caps Lock, turn Caps Lock off and Reset keyboard modifiers. Clear and Cancel. Then log in normally. | Intended case/symbols, visible checkbox, one startup session. Never send a real password. |
| G — hero gallery | Heroes → My heroes; choose a card, search its name, view earned forms, compare portraits, permanent level, XP bar, HP and attacks, then Back. Try a search with no matches and clear it. | Search changes the list only. Explicit buttons open forms; Back is read-only. The same account collection remains. No heroes means a campaign instruction card, not an invented starter. Record actual values. |
| H — session and Quit | Multiplayer → Back; inspect Heroes; main-menu Log out; log in again. Quit from main menu, reopen, Start game, Quit from Welcome; reopen and log in. | Back retains login, Heroes has no logout, main-menu logout returns to opaque Welcome, both Quit actions close to LDPlayer's launcher. Saved trust remains; reopening needs login. |

Use existing runtime-v2 players. If an existing account has no heroes, complete its own normal campaign scenario to unlock eligible named heroes/forms; do not seed/reset the database. A genuinely new second player may sign up once and play their own campaign. Story saves/results belong to their original account.

## I–N. Teams and plans

| Step | Action | Expected |
| --- | --- | --- |
| I — Teams hub | Open Teams. Select overview and member cards, scroll to the last member, inspect applications and management, then Back. | Team/area/level/rating/count and captain/member roles are readable together. Captain-only actions stay unavailable to members. No team shows useful Find teams/Create team choices. |
| J — directories | Teams → Find teams; browse areas, teams and rosters. Use search, a search with no matches, Previous/More where available and Refresh. Clear the search afterwards. Inspect applications/decisions. | Correct selected record; paging/Refresh still work with no matching card. Only explicit confirmation sends an application or acknowledges a decision. Back does not apply/join/leave. |
| K — propose | As a captain, New battle; preview the approved maps, select opponent and ordered lineups, then Back from final proposal once. Repeat and explicitly submit one valid plan. | Map art/2v2,3v3,4v4 capacity and selected seat order agree. Back creates no plan. A saved plan retains the reviewed teams/lineups. Only maps enabled in the current area appear. |
| L — plan details | Battle plans → Open plan. Select map overview, both team cards and every side card, including the last side. Log in sequentially as each selected player to choose their own hero/form. After every hero is saved, both captains approve the plan. Return to your selected player; try Back at Ready confirmation, then confirm Ready. | Portrait/form/permanent level and Ready status agree with the player. Own hero/Ready controls cannot edit another side. Both captain approvals and full selected readiness remain required for shared start. Other players may be Not ready for personal practice. |
| M — practice | With both captains approved and only your own side Ready, Practice. Review training mode/gold/turns/fog, Back once, then launch and play a turn. | Back launches nothing. Practice uses the chosen saved lineup, needs no other connected player and grants no persistent XP/rating. Ready alone never launches practice. Return to the same account. |
| N — inactive/history | Inspect a cancelled plan in the current runtime, if one exists; select its overview and side cards. Inspect a completed plan if one exists. | Cancelled state and saved-readiness history are clear; no Practice/shared start on cancelled plans. Watch completed battle replay requires a verified local recording. Eligible completed plans may instead offer Download completed battle replay; report an unavailable recording without claiming it played. Refresh keeps current server status. Do not cancel a running battle to manufacture this check. |

If the current runtime has no teams/plans, create the needed teams through normal player actions and approve memberships using existing owned accounts sequentially. Do not expect historical pre-runtime-v2 IDs to exist. An unavailable history/replay check is NOT RUN, not a UI failure. Leaving/rejoining clears the affected player's draft readiness; current membership and hero eligibility are checked again. It does not by itself erase the saved hero choice or both captain approvals. Changing a selected hero clears readiness and both approvals under the existing rules.

## O–Q. Individual rooms and hero readiness

| Step | Action | Expected |
| --- | --- | --- |
| O — dashboard | Multiplayer: use Individual rooms, Standard rooms, Open places, Running only, text name/map search and Gold & turns. Apply/clear limits and return to Individual rooms. | Visible controls, readable occupancy/status/map preview, no typed filter syntax needed. Zero rooms is valid. Open places plus Running only can legitimately match none. These rooms have no Team-area restriction. |
| P — create/review | Create room; choose a standalone two-player map and set a finite turn limit of10 in the native settings. Continue, choose Individual battle room, then100 starting gold. Back from Publish once; repeat and Publish. | The native settings screen and final map/seat/gold/turn preview agree. Back creates no room. Published room has1/2 human players and no usable manual Start. Record numeric Room ID, map/gold/turns; Room settings shows the full published rules. |
| Q — Hero & Ready | Click your side's hero control beside “Hero & Ready”. Choose a hero/form and inspect its stats; wait for the choice to appear in your side. Reopen Hero & Ready and choose Ready. Back from its settings review once, then repeat and choose Set Ready. Open Room settings. | Readable hero portrait/stats and full rules. Choosing a hero does not itself set Ready. Only your side changes. Ready with1/2 players does not start. Changing hero/settings invalidates prior consent; confirm the latest snapshot. |

Permanent team membership is unnecessary here. Map-defined temporary alliances still apply. Do not use a Team plan UUID as a numeric Room ID. Before P, record the permanent hero level, current XP and total XP for both intended players, then return to the visible host account. Never use the companion's account in the visible game while that companion is running.

## R. One-LDPlayer companion join and departure

Keep the visible host in its room. Run in a new PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $companionUser = Read-Host 'Second player username (not the visible player)'
    $roomNumber = Read-Host 'Numeric Room ID shown in Room settings'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidIndividualCompanion.ps1' `
        -Username $companionUser -RoomId $roomNumber
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'If deliberately cancelled before Ready, report that cancellation. Otherwise send the sanitized companion report.'
    }
}
```

The helper verifies1192620, asks `CONTROL <username>`, privately requests that other account's password, lets you select its owned hero/form, reviews rules and asks `JOIN <username>`. Join, but **press Enter at the first READY prompt** to cancel this first run. Expected: visible occupancy gains the second player, prior Ready is invalidated, then departure reopens the seat at1/2. No battle starts. Cancellation can return nonzero by design; only the owned companion session/process stops.

## S. Full room, explicit Ready and automatic start

Run R again with the same second player and room. Confirm CONTROL/JOIN and leave its READY prompt pending. In the visible client inspect2/2 players and both heroes, choose your hero if necessary, then Ready. The room must wait. Review the helper's latest snapshot and explicitly confirm READY. If its revision changed, review the new prompt; consent is not silently renewed.

Expect automatic normal-game entry and INDIVIDUAL COMPANION STARTED. Play at least two complete rounds, with each account controlling its own side, then reach the normal result or finite turn limit. No out-of-sync error; expect INDIVIDUAL COMPANION FINISHED, I05 completion and I06 session revocation. The companion is a separately authenticated computer player within the same emulator, not a second human.

## T–W. Completion and regressions

| Step | Action | Expected |
| --- | --- | --- |
| T — completion | Leave the ended room, inspect both players' permanent collections sequentially. | Closed room is no longer joinable. Individual play grants no permanent hero/team XP or rating. Native in-battle advancement and local replay/save rules remain separate. |
| U — closure/capacity | Publish a waiting room and leave as host. Then create a four-player map, inspect its4 seats and leave unfilled. | Host closure ends the waiting room; no early start at the observed1/4 occupancy. Report2/4 only if another player actually joined. A deliberately disconnected companion reports incomplete, not a successful battle. |
| V — Standard mode | Create Standard multiplayer (manual start), add computer opponents, choose owned hero/Ready and start manually. Play, save, leave, host that save and resume. | Standard manual/AI/save behavior remains. Individual full-room auto-start rules are not imposed on it. Back retains the account. |
| W — Campaigns | Resume a campaign owned by the signed-in account and inspect Heroes afterwards. Record any legitimate completed victory/reward. | Normal story UI remains; earned hero forms and permanent progression appear in the gallery. Merely opening a screen awards nothing. Do not claim a reward if the scenario was not completed. |

## X. Controlled network loss

Leave/save active games and stop companions. Idle signed in at the main menu. Stop only account bridge15001 with Ctrl+C. Expect automatic local sign-out and connection warning after the existing polling interval/request timeout, with no usable old menu behind Welcome. A login attempt while stopped must fail as a connection error. WAN loss alone must not sign out a healthy LAN game.

Restart the bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require READY, log in to the same account and inspect its same collection/team. Do not reimport trust or reset an account.

## Y. Shared Teams, replay and persistence

Continue the existing shared-battle acceptance in [UNIFIED_GAME_ACCEPTANCE_1192617.md](UNIFIED_GAME_ACCEPTANCE_1192617.md) using **current runtime-v2 accounts and the new UI**, not its historical initialization instructions. Use Run-AndroidAllianceCompanion.ps1 for fixed Team seats; the individual helper is different. Verify shared rounds, result settlement, actual completed replay and unchanged permissions. Report any prerequisite not yet available as NOT RUN. Save/quit, stop all five services cleanly, restart with C, reopen/login and confirm the same actual account/collection/team values.

One visible client cannot simultaneously show another person's live dashboard. The VPS covers published-room updates; multiple-human Android acceptance remains distinct. The UI release does not change server combat, reward or dispute rules.

## Z. Report and targeted retest

Return step letters with PASS / FAIL / NOT RUN, actual WAN status, room/plan ID where relevant, observed state and saved log name. For layout failures include screen resolution and the exact visible message; a screenshot without credentials is useful. Stop at the first unexpected behavior rather than repeating mutations.

We reproduce/analyze the report on the VPS, fix the responsible code, run affected verification, commit/push and provide a targeted retest. Retain unrelated accepted results and existing state. A build, service check or screenshot does not by itself prove every gameplay scenario passed.
