# Windows / LDPlayer product acceptance — 1192621

This is the new A–Z acceptance sequence for release 1192621. Windows/LDPlayer1192621 installation and gameplay are **pending**. Earlier 1192620 build/service observations remain historical evidence, not acceptance of this release. Use the existing `runtime-v2`, accounts, collections, Teams, public server identity, pinned tools and one LDPlayer. Keep completed old builds, journals, backups, saves and the existing OBB.

The update adds a bundled public server configuration, branded startup, login-first navigation, hero discovery and flexible Team plans. It explicitly migrates schema 2 to 3; it does not initialize a replacement database. Team plans may contain Open, Reserved, AI and Closed seats. Before preparation both teams need equal enabled counts, at least one human seat each, every human seat occupied, current captain approvals and all human players Ready. Individual rooms still require the full configured human room and every player Ready.

Record the WAN state once per batch. After C, disconnect WAN while keeping local Ethernet connected. Continue only until the first unexpected result; preserve its state and saved logs. A later step never makes an earlier failed step acceptable. Passwords, tokens, `.env` contents, private runtime files and cold backups stay on the Windows computer.

## A. Finish active work and stop the five services

Finish existing battles normally, or explicitly cancel a draft/running Team battle through its supported captain/administrator control if that is the intended outcome. Review any pending result before cancelling it; cancellation grants no rewards. Save campaign work, leave rooms, stop companions and Quit the app. Do not leave a live native individual room running during the service upgrade.

Stop native Multiplayer, shared battles, account bridge, backend and MongoDB with Ctrl+C in their existing windows. Wait for all five prompts. Keep the one LDPlayer instance available. Do not clear Android data, delete a saved profile, remove a journal or edit database records.

## B. Cold-backup the current runtime before pulling

Run in the PowerShell window you will retain for B–H:

```powershell
$ErrorActionPreference = 'Stop'
$productRuntime = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'
$productBackup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192621-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
    -Operation Backup -RuntimeRoot $productRuntime -DestinationPath $productBackup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. Stop and retain the diagnostic output.' }
Write-Host ('Retain this exact BackupPath for E: ' + $productBackup)
```

Expect `ALLIANCE BACKUP VERIFIED` and MA03 completion. A cold backup can report `schema_checked:false`; this does not mean schema validation passed. Keep this exact new backup privately; E binds its migration journal to it. Do not substitute an earlier 1192619 backup or repeat B after a migration interruption. If you later open another PowerShell window, restore `$productBackup` from B's exact recorded destination and `$productRuntime` to the existing runtime-v2 path.

## C. Pull both repositories, then disconnect WAN

Temporarily connect to GitHub, leaving services stopped:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $productBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $productRepo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $productBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $productRepo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Preserve local changes and send the output." }
        & $productBash --noprofile --norc -c ('/usr/bin/git -C ' + $productRepo + ' rev-parse HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not verify $name commit." }
    }
}
```

Expect two successful fast-forward updates and both commit IDs from the release handoff. Do not reset unrelated README edits. Disconnect WAN and retain local Ethernet; record that actual state. Keep all services stopped through F. Do not update dependencies or regenerate the server certificate.

## D. Append the public profile reference without replacing `.env`

The existing public profile is `wesnoth_server\runtime\alliance-transport\public-profile.json`. It contains public endpoint/certificate information only. The build reads only `WESNOTH_PUBLIC_PROFILE_PATH`; unrelated well-formed assignments are ignored without interpolation or inclusion in the APK/receipt. A missing, duplicate or invalid public path/certificate is a build error.

This block preserves every existing byte, appending the public key only if absent. It prints no configuration values:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $productEnv = 'D:\Test\wesnoth-setup\wesnoth_client\.env'
    $productPublic = 'D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance-transport\public-profile.json'
    if (-not (Test-Path -LiteralPath $productPublic -PathType Leaf)) { throw 'The existing public profile is missing. Stop without regenerating identity.' }
    $productEncoding = New-Object System.Text.UTF8Encoding($false, $true)
    $productExisting = ''
    if (Test-Path -LiteralPath $productEnv) {
        $productItem = Get-Item -LiteralPath $productEnv -Force
        if ($productItem.PSIsContainer -or ($productItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'The existing .env path is not an ordinary file.' }
        try { $productExisting = $productEncoding.GetString([IO.File]::ReadAllBytes($productEnv)) }
        catch { throw 'The existing .env is not readable UTF-8. Preserve it and stop.' }
    }
    $productMatches = [regex]::Matches($productExisting.TrimStart([char]0xfeff), '(?m)^\s*WESNOTH_PUBLIC_PROFILE_PATH\s*=')
    if ($productMatches.Count -gt 1) { throw 'The public profile key is duplicated. Preserve .env and stop.' }
    if ($productMatches.Count -eq 0) {
        $productPrefix = if ($productExisting.Length -gt 0 -and -not $productExisting.EndsWith("`n")) { "`r`n" } else { '' }
        [IO.File]::AppendAllText($productEnv, $productPrefix + 'WESNOTH_PUBLIC_PROFILE_PATH=../wesnoth_server/runtime/alliance-transport/public-profile.json' + "`r`n", $productEncoding)
        Write-Host 'Public profile reference appended; existing configuration preserved.'
    } else { Write-Host 'Existing public profile reference retained; the build will validate it.' }
    Remove-Variable productExisting -ErrorAction SilentlyContinue
}
```

Do not paste `.env`, run it as a shell script, copy server-key.pem, or import anything in Android. Existing imported Android trust remains on disk unused; the signed APK's validated public profile is authoritative.

## E. Migrate the existing schema with B's exact backup

```powershell
$ErrorActionPreference = 'Stop'
if (-not $productBackup -or -not (Test-Path -LiteralPath (Join-Path $productBackup 'manifest.json') -PathType Leaf)) { throw 'Select the exact verified B backup first.' }
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Migrate-WindowsAllianceRuntime.ps1' `
    -RuntimeRoot $productRuntime -BackupPath $productBackup
if ($LASTEXITCODE -ne 0) { throw 'Migration stopped. Retain this same backup and both migration journals; send the saved log.' }
```

Expect `ALLIANCE SCHEMA 3 MIGRATION COMPLETE`, schema_version 3 and complete/already_complete status. The helper temporarily owns the database process, verifies its identity, updates schema metadata/validators/indexes and stops it. Existing draft plans become reserved-human plans with their IDs and original snapshots retained; both captain approvals and all Ready flags reset. Accounts, heroes, XP, Teams, database generation, completed/cancelled records, certificate and replay files stay intact. If interrupted, keep every journal and resume E with the **same** BackupPath; do not initialize or restore over the current runtime.

## F. Rebuild only the changed bridge, native Multiplayer and Android

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild failed. Retain both its old stage and logs.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Native Multiplayer rebuild failed. Retain its stages and logs.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Retain its stages, journals and logs.' }
}
```

Expect verified old bridge/native/account stages retained under unique names, `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`, `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` / `UNIFIED MULTIPLAYER BUILD PASSED`, and `ANDROID ACCOUNT ENGINE BUILD PASS` / `ANDROID ACCOUNT GAME BUILD PASS` / `ANDROID ACCOUNT GAME REBUILD COMPLETE`. The APK must be 1192621 with the original signing identity. All builds use existing offline dependencies; no fresh OBB is made or transferred. Stop at the first failure rather than repeating the whole sequence.

## G. Start and verify the five current services

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Return its saved workflow text/JSON and failing service log.' }
```

Expect W02–W06 PASS and W07 UNIFIED GAME SERVICES READY: database 27018, backend 18765, account bridge 15001, shared Teams 15002 and native Multiplayer 15000. Keep all five windows open. A healthy server probe is not proof of Android login or gameplay.

## H. Install in place

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
    -KeepSavedProfile
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Preserve app data and return the saved install log.' }
```

Expect `ANDROID ACCOUNT GAME INSTALL COMPLETE`, verified version 1192621 and a fresh startup-screen launch. `KeepSavedProfile` remains a compatible installer option; the bundled public configuration supplies the connection. Preserve existing app data, imported profile files, saves and OBB. The installer marker establishes launch only; observe loading and authentication in I–J.

## I. Branded loading and login entry

Observe a cold app launch after H. Expect the Wesnoth background/logo, percentage and measured progress bar, then Login directly. Routine filenames, preparation paragraphs and technical phases must not appear. The percentage can restart as validation moves to installation; 100% appears only after the complete preparation succeeds. There is no profile-import, server-selection or Start game setup page. The bundled endpoint must work with WAN disconnected and local Ethernet connected.

Check the actual emulator resolution for clipped text, overlapping controls and a blank or frozen loading screen. A failure must show a concise error with Retry and Close. Record that error and the last percentage if loading fails; Close must close the task. Do not deliberately corrupt the only local OBB or private data to manufacture a failure. If no failure occurs, mark that visible failure-path subcheck NOT RUN; VPS interruption/tampering fixtures are recorded separately. Do not reinstall, delete the OBB or clear app data to bypass an unexpected result.

## J. Authentication and physical keyboard

Login appears first. Choose Sign up, then Back without submitting; Login must replace it. The outer X closes the whole task; reopen to Login before continuing. Credential screens must cover the previous view; there must be no usable home behind a signed-out dialog. Check the password visibility controls, including signup confirmation. In a harmless test field type `aAzZ1!` with the physical keyboard, exercise Shift/Caps Lock, turn Caps Lock off, check the exact characters with the eye control, then clear/cancel. Never expose a real password in evidence.

Make one deliberate wrong-password attempt, then log in privately to an existing runtime-v2 player. The failed attempt must remain an authentication error; successful login opens that player's home. Signup, if an additional owned player is needed, starts with zero collected heroes and no starter choice. Earn that player's heroes through normal story play. Do not seed heroes or load another player's campaign save. Account changes in later tests use Quit, reopen and log in; there is no Logout menu action.

## K. The nine home destinations

Verify these nine labels and their behavior:

| Destination | Expected behavior |
| --- | --- |
| Campaign | Opens the native campaign browser with reward discovery. |
| Room | Opens the individual-room browser using the authenticated LAN session. |
| Team | Opens persistent Team membership and battle plans. |
| Load | Opens retained local saves/replays. It does not resume a network battle through a saved-game upload. |
| My Heroes | Opens the hero collection/discovery view. |
| Achievements | Opens achievements and returns cleanly. |
| Map Editor | Opens the editor and returns cleanly. |
| Preferences | Opens preferences and returns cleanly. |
| Quit | Closes the whole app; exercise the complete session/recovery checks in Z. |

Enter the first eight destinations and return with their native exit control: Campaign and Load use Cancel; Achievements and Preferences use Close; the new product screens use Back. They must retain the same signed-in player, readable native styling and clean screen boundaries. There is no Standard Multiplayer destination, guest network entry, profile-import action or Logout button. Network battles are entered through Room or Team. Record missing or extra destinations as failures.

## L. Hero discovery and owned collection

In My Heroes inspect the All heroes, Owned and Locked filters, search by a known name, try a no-match query, then clear it. Inspect a locked hero and an owned hero where available. Both show portrait/unit art, biography and source campaigns. Owned entries additionally expose earned forms, permanent level/XP, HP and attacks; locked entries explain discovery without presenting unearned forms or owned statistics. Empty collections give campaign guidance rather than inventing a starter.

Browsing, changing filters and opening details grant no hero, XP or form. Compare actual owned names/forms and XP with the retained account. Technical account/Team/run IDs belong in the local administrator tools when an operator check needs them; ordinary player screens use names and meaningful status.

## M. Campaign selection and reward preview

Open Campaign, select several campaigns and inspect Heroes to discover / View heroes before starting. Check readable descriptions and native artwork, including a campaign with several eligible heroes. The preview describes possible story rewards and branch dependence; it does not promise every listed form from the first scenario. Use Cancel without launching once and verify that the collection is unchanged.

Choose a normal campaign for the signed-in player. Campaign combat keeps the authored story units and statistics; permanent collected-hero bonuses do not rewrite story strength. Starting or previewing the campaign alone grants no unlock or XP.

## N. Scenario victory and earned heroes

Play or resume that player's own normal campaign save and finish a legitimate scenario while controlling an eligible named hero. Compare before/after collection, forms and permanent XP with the actual completed scenario. The reward boundary is scenario victory, not campaign selection, loading or an unfinished battle. Record the scenario and the actual changes; do not invent a reward for an enemy or a hero absent from the eligible controlled roster.

Open the recorded result again and, where the retained save permits the check, repeat loading the already acknowledged victory. The same checkpoint must not award twice. Save/leave cleanly. Keep this story save for W's check that an unfinished local story does not reserve a network seat.

## O. Room creation on one page

Open Room and Create room. On one page select a standalone map, inspect its preview and human capacity, then set the room name, common Gold, Base income, Turns, Fog, Shroud and Observers. Use the distinctive room name **1192621 acceptance** for Q. Gold accepts 0–1000; effective base income 0–20; turns accepts 1–1000 or Unlimited. These rules apply equally to every side; no per-side economy override is offered.

Back once before creating: no room should appear. Repeat with a two-player map, 125 gold, 4 base income and a finite turn limit sufficient for two rounds, then create it. All configured seats are human. There is no AI/Closed option or saved-network-game creation path in Room. Individual rooms require neither persistent Team membership nor an area.

## P. Live Room dashboard and rules

Creating O opens the host's waiting room. Inspect its name, occupancy, Ready count and rules. Gold, effective base income, turn limit and fog/shroud/observer choices must match O. Choose Hero & Ready → Choose hero, then Hero & Ready → Ready → Set Ready.

Select the visible player's owned hero/form. At 1/2, Ready cannot start the game. Change the hero and verify that old Ready consent clears and the live details refresh. Leave the waiting room as host once: it must close and return to the dashboard. Exercise map/name and availability filters there. For advanced filters select Filters, choose the Players, Starting gold or Turn limit row, choose Change, select a value and choose Apply filters. Players supports Any or 2–8. Clear limits also requires Apply filters. A no-match view must remain usable. Recreate **1192621 acceptance** with the reviewed settings before Q; reopening filters from a hosted waiting room requires leaving and closing that room first. Inspect a larger unfilled room if available; no partial room may start.

## Q. Full human occupancy and Ready

With the visible host waiting in **1192621 acceptance**, run the separately authenticated companion in another PowerShell window. It resolves the exact room name through the authenticated lobby and refuses missing or ambiguous matches; no numeric Room ID is needed in the player UI.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $productIndividualUser = Read-Host 'Other owned player username (not the visible player)'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidIndividualCompanion.ps1' `
        -Username $productIndividualUser -RoomName '1192621 acceptance'
    if ($LASTEXITCODE -ne 0) { Write-Host 'For deliberate pre-Ready cancellation report CANCELLED; otherwise return the sanitized failure report.' }
}
```

Review CONTROL/JOIN/READY prompts; the password is hidden and never passed as an argument. Cancel the first READY prompt once. The departed seat must reopen and old consent must clear. Run again, review the latest room settings and explicitly consent. Ready the visible player against those same settings. Only full configured human occupancy and every player Ready may start automatically; there is no manual Start bypass.

Play at least two rounds and finish normally. Expect INDIVIDUAL COMPANION STARTED/FINISHED and successful helper cleanup for a completed run. Individual play awards no permanent hero/Team XP or rating. The companion occupies a human-account seat but plays it by computer in the one LDPlayer; this does **not** establish two-human interaction. Do not log its account into the visible app simultaneously. Started Individual rooms refuse new seats and rejoin; a lost run is reported as incomplete, not a successful Team-style reconnect or a fabricated completion.

## R. Publish an incomplete Team plan

Open Team and verify the retained roster, captain/member roles and area. Applications and Captain orders are under More. Use two real Teams in the same approved area. As one captain choose New battle, the real opponent and an approved map. Back before Save plan once, then publish a plan with empty Open human seats. Publication must succeed without choosing all players or filling the map. Both Teams can see the saved plan.

If an old draft existed before E, inspect that retained plan too: original teams, map, named human slots and hero choices remain, but approvals and Ready require fresh confirmation. A departed reserved member must not block their captain from repairing their own slots. Do not treat reset migration consent as lost account progress.

The opponent starts with Open slots and its own captain configures them later. There is no fictitious opponent or automatic creation of players. Ordinary members cannot publish or edit captain settings. Reopen the plan after Back and a clean app restart to verify persistence. Keep existing Teams and accounts; do not replace them merely to obtain a convenient fixture.

## S. Slots, map and common settings

Each captain edits only their own side slots: Open means any current member of that Team may join; Reserved names one current member; AI chooses a supported faction and leader; Closed removes that side from active play. Exercise a non-default AI leader choice and check that the saved faction/leader pair survives reopening. AI has native level 2 and no player account or permanent hero XP owner.

Map preview and common gold/income/turn/fog/shroud/observer settings are on one page. Changing a map resets the affected lineup for review. Keep at least one human slot per Team. Publish an unequal enabled-seat draft once: it remains editable, but it must not prepare. Then make enabled counts equal.

For the mixed-game checks use Hexcake with one human, one AI and one Closed side per Team, 125 gold and 4 base income. If practical choose Closed sides 1 and 6, human sides 4 and 2 and AI sides 5 and 3; this exercises skipped edge sides and gives human side 2 the engine-host role. Set a suitable finite turn limit and enable observers only if an eligible extra Team member is available. A separate 2-turn fixture can verify a natural draw in X.

## T. Join, owned hero selection and renewed consent

Using the owned players sequentially through Quit/reopen/login, join eligible Open or own Reserved slots, choose each player's own earned hero/form and set Ready. A different player cannot claim a Reserved slot, join the opposing Team's slot or change another player's hero/Ready. Unseated teammates cannot dismantle preparation through Leave seat. Both current captains approve the reviewed plan.

Change one material setting, slot, participant or hero before preparation, then refresh the other account. Earlier captain approvals and Ready marks must clear. A stale action requires refresh and fresh consent; it is not silently retried. An empty/unready human slot, missing approval or unequal enabled counts prevents preparation. Do not leave the last Ready action pending while changing accounts without accounting for U's preparation timeout.

## U. Automatic preparation and start

Complete the balanced mixed plan's remaining human joins, owned hero choices, Ready marks and both captain approvals. The final valid consent automatically prepares the battle and reserves its human accounts. There is no separate captain Start decision. Enter the prepared battle with the two authenticated participants; gameplay begins after all humans load the same frozen configuration. AI and Closed slots do not add human login or Ready requirements.

For one-LDPlayer execution, use the Team companion below for the other owned participant. Obtain its Team run UUID only from the local administrator's Game runs page at `http://127.0.0.1:18765/runs`, matching teams/map/time. Do not expose run UUIDs in ordinary plan screens. Keep the visible client on its intended player while the helper authenticates the other one.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $productCompanionUser = Read-Host 'Other owned player username (not the visible player)'
    $productBattle = Read-Host 'Team run UUID from the local administrator Game runs page'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidAllianceCompanion.ps1' `
        -Username $productCompanionUser -BattleId $productBattle
    if ($LASTEXITCODE -ne 0) { Write-Host 'Return the sanitized companion report; do not repeat a mutation automatically.' }
}
```

The helper requests CONTROL consent and a private password. Preparation is time bounded: if entry expires, refresh and reconfirm through the plan; no account may remain permanently busy. Withdrawing Ready or editing before start releases only that preparation and requires renewed consent. Frozen running configuration cannot be edited into a different battle.

## V. Native AI, host recovery and read-only observers

Play at least two full rounds. Check the selected AI leaders, native recruiting/combat, both alliances, skipped Closed sides, common gold/income and finite turns. The designated human engine host controls its own human side plus AI sides; it must never acquire another human's side. No out-of-sync error is acceptable.

In a controlled Team run, interrupt the engine host connection while the opponent remains connected, then use the same account's Reconnect action for the same retained run. Expect pause, replay catch-up and resumed ownership of the original human/AI controllers, with no duplicate run or reward. Do not cancel the run or replace the host with another account. If the available setup cannot isolate that connection without stopping the companion too, report this Windows subcheck NOT RUN; the VPS recovery test does not replace it.

Where an extra current member of either Team is available, use Watch on an observer-enabled running plan. The observer catches up through the live battle and ending, owns no side, cannot issue gameplay/captain commands or submit a result, and receives no participant XP. Disabled observers and outsiders must be rejected. Observer departure must not pause the humans. Report actual simultaneous scope; one visible app alone cannot establish multi-human spectator behavior.

## W. Multiple plans, concurrent battles and player exclusivity

Publish and reopen a second plan for the same real Teams while the first exists. Multiple saved plans must not replace one another. With enough distinct owned participants, prepare/run two plans concurrently for the same Teams: the Team itself is not locked to one run. Each player may occupy only one prepared or running network battle, across both Team and Room. An attempt to reserve the same player in another battle must fail without cancelling the first or another player's valid room.

Before either plan prepares, mark a shared participant Ready in both drafts. Preparation of one must clear only that participant's competing draft readiness, preserving unrelated players' consent and the other plan's settings. A failed preparation must not clear readiness elsewhere.

Changing/releasing an unstarted preparation and completing/cancelling the intended run must release only its own reservation. Native Individual connection/server loss has bounded lease cleanup; do not claim instant availability after an unconfirmed disconnect. An unfinished story save from N does not reserve a network seat. If the available accounts/one-LDPlayer setup cannot execute concurrent games, mark that subcheck NOT RUN and retain the separate multi-plan observations; computer companions are not multiple-human acceptance.

## X. Results, XP and ranked eligibility

Finish the mixed Team run normally, by an explicitly intended captain surrender/agreed draw, or by reaching its finite turn limit. Check Results/Send result, the human reports and both captain confirmations. Uploading a result is distinct from settlement. A disputed or incomplete result must not silently award progression; retry an existing pending upload through its offered action rather than creating a replacement run.

For an agreed Team result, each human participant's selected hero receives 20 XP for a win, 10 for a loss or 10 for a draw. Each Team receives 100/25/50 XP respectively, once per match. Other owned heroes remain unchanged. AI and observers receive no participant hero XP. Refresh, reopen and repeat an already acknowledged result check: there must be no duplicate award.

The mixed/custom battle changes no rating. Rated eligibility requires the full map's human slots and the approved balanced preset: 100 gold, 2 base income, Unlimited turns, Fog on, Shroud off, Observers off. AI, Closed or changed rules make the match unranked while retaining legitimate human hero/Team XP. Record actual before/after ratings for a fully exercised ranked match; do not infer its outcome from a custom test or claim it ran without enough participants. Room, browsing and local playback award no permanent XP/rating.

## Y. All-Team history and completed replays

Open Team → History as a current teammate who did not participate, if available. Completed history and verified completed replays for that Team must be visible, including other members' matches. Choose Open battle, inspect the actual map/rules/result, then choose Replay. If not cached, confirm Download replay, wait for completion, reopen the battle and choose Replay again. The download message may say Watch replay; the battle button is Replay. Play the completed recording through its end; it must not upload another result or award XP. An unrelated player must not gain access. Historical participants/recorded captains retain their authorized records.

Reopen existing format 1 history and a retained old shared replay where available. Load continues to read retained local saves/replays; it does not recreate a Standard network room or resume a Team battle by uploading a save. Live Team recovery uses the plan's Reconnect action. Unavailable historical fixtures are NOT RUN, not invented successes. Keep old saves and recordings after this check.

## Z. Quit, service recovery and mandatory isolated schema 2 restore

Finish/leave test games and stop companions. Quit from authenticated home: the whole app closes to the LDPlayer launcher, the local account session is cleared and reopening requires login through I–J. Check the signed-out authentication X too. No Logout button is needed. Server-side session revocation is only claimed when the request succeeds; loss of the LAN must not prevent local Quit.

For controlled session recovery, idle signed in and stop only account bridge 15001. Expect local sign-out after the monitor/request timeout, an opaque signed-out view and a connection error while the bridge is unavailable. Restart only that bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require READY, authenticate as the same player/database identity and verify the retained collection and Team. No mutation is automatically retried, and another account must not inherit a paused authenticated game. Quit and stop all five services cleanly. Retain current runtime-v2 and both migration journals.

**The isolated restore drill is a required Z acceptance check even when migration succeeded.** Restore B's exact verified schema 2 backup into a new destination, with all services stopped:

```powershell
$ErrorActionPreference = 'Stop'
if (-not $productBackup -or -not (Test-Path -LiteralPath (Join-Path $productBackup 'manifest.json') -PathType Leaf)) { throw 'Use the exact verified B backup path.' }
$productRecovery = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\recovery-1192621-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
    -Operation Restore -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -BackupPath $productBackup -DestinationPath $productRecovery
if ($LASTEXITCODE -ne 0) { throw 'Recovery verification failed. Preserve both destinations and return its sanitized log.' }
$productRecoveredSchema = Get-Content -LiteralPath (Join-Path $productRecovery 'restore-verified.json') -Raw | ConvertFrom-Json
if ($productRecoveredSchema.schema_version -ne 2) { throw 'The recovery receipt is not schema 2. Preserve it and stop.' }
Write-Host ('Recovered schema version: ' + $productRecoveredSchema.schema_version)
```

Expect `ALLIANCE RESTORE VERIFIED`, schema_checked true, recovered schema_version 2 and the temporary verification database stopped. Keep the recovered copy, original backup, retained old bridge/native builds, current schema 3 runtime and journals. This verifies recovery without activating it: no runtime selection change, no new services against the schema 2 copy, no overwrite of runtime-v2 and no copying individual database files between them.

Restart the current **runtime-v2** with G, reopen the installed app without reinstalling and log in. Confirm the same current account, earned results, Team plans and public identity. Do not repeat a pull, build, migration, trust import or OBB transfer for this restart. An actual rollback, if ever needed, requires a separate reviewed choice of the retained matching release and isolated runtime; this drill does not perform one.

Return A–Z as PASS / FAIL / NOT RUN, including actual WAN state, visible names, expected/observed behavior and exact diagnostic filenames. Record operator identifiers from administrator tools only where needed. Include the actual emulator resolution for visual observations and exclude credentials from screenshots. Build/service probes do not prove login; one-LDPlayer automation does not prove multiple-human behavior.

Sanitized outputs are under each repository's `diagnostics`: server `alliance-maintenance-*`, `alliance-migration-*`, bridge/native build logs, `alliance-workflow-*` text/JSON and W02–W06 logs; client account build/rebuild/install logs, `android-companion-*.json` and `android-individual-companion-*.json`. Send relevant helper reports or console output, never `.env`, private runtime/backups, passwords, tokens or raw app storage. Stop at the first unexpected result; fixes are reproduced on VPS and only failed/affected checks are repeated.
