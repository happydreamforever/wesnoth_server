# 1192619 — individual rooms and startup corrections: Windows A–Z

**Current user checkpoint (2026-10-24):** A–D are accepted, including the Windows Android1192619 rebuild. Before **E**, pull the server-only startup-check correction below: the original checker rejected the new individual-room greeting. The fix is verified on VPS; both completed Windows builds remain valid. After the pull, disconnect WAN/retain local Ethernet, start the five existing runtime-v2 services and return W07 readiness before F installation. No repeated backup, rebuild or initialization is needed. E–Z remain pending.

This is the current test sequence. It includes the untested 1192618 Welcome, keyboard, logout, network-loss and Quit corrections. It adds global individual rooms to the existing **Multiplayer** dashboard. The native server and Android app need rebuilding; MongoDB schema, account bridge, shared Team service, source data/OBB and dependencies are unchanged.

Use the existing **runtime-v2**, existing players and one LDPlayer. Do not rerun Initialize-WindowsUnifiedGame.ps1 or Initialize-WindowsAlliance.ps1. Do not reset the app, reimport trust, copy another OBB, upgrade tools or create replacement accounts. Existing README edits, backups and update journals stay in place. Record WAN status once for the batch; disconnect WAN after the Git pulls and retain local Ethernet. No result below is assumed passed until you report it.

Complete one step, report its result, and continue after review. The full list is supplied so you can see the whole test. At the first unexpected result, stop and send its step, exact message and relevant saved log. Never send passwords, tokens, private keys, `.env`, database files or private backups. A later fix repeats the failed step and affected regressions, not the entire setup.

## A. Save, stop and update both repositories

Save and quit any active game. Stop the five existing service windows with Ctrl+C, one at a time: native Multiplayer 15000, shared battles 15002, account bridge 15001, admin 18765, then MongoDB 27018. Wait for each prompt. If stopping is uncertain, report it; do not delete lock files or start duplicates.

Temporarily connect Windows to GitHub, then run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }
}
```

Expected: both fast-forward pulls and two printed commits. Existing local README edits are retained; if Git refuses the merge, stop instead of resetting or discarding them. Disconnect WAN again, retaining local Ethernet. Keep all services stopped through D.

## B. Cold backup of the current runtime-v2

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
    $backup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192619-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Backup -DestinationPath $backup `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2')
    if ($LASTEXITCODE -ne 0) { throw 'Backup stopped. Send the saved diagnostic log.' }
    Write-Host "Keep this private backup locally: $backup"
}
```

Expected: ALLIANCE BACKUP VERIFIED and MA03 completion. `schema_checked: false` is normal for this cold-copy check. Keep the exact path privately; no existing runtime is replaced or initialized.

## C. Build the native Multiplayer room server

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Multiplayer build failed. Send the saved build log.' }
}
```

Expected: the previous native Multiplayer stage is preserved, followed by UNIFIED MULTIPLAYER ARTIFACT VERIFIED and **UNIFIED MULTIPLAYER BUILD PASSED**. Log: `wesnoth_server\diagnostics\unified-multiplayer-build-*.txt`. No account-bridge or guest-server rebuild is required.

## D. Build Android 1192619 offline

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send the saved rebuild/build logs.' }
}
```

Expected: prior completed account stages are preserved, then ANDROID ACCOUNT ENGINE BUILD PASS, ANDROID ACCOUNT GAME BUILD PASS and ANDROID ACCOUNT GAME REBUILD COMPLETE. Original dependency/engine foundations are reused. Do not rename or remove interrupted stages/journals; send the first failure.

## E. Start the five existing services

Before this first E run, temporarily connect Windows to GitHub and pull the startup-helper correction. Keep the five services stopped while updating:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $bash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull failed. Stop and send the output.' }
    & $bash --noprofile --norc -c '/usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse --short HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the server commit.' }
}
```

Expected: successful server update including fix9e69d7b and its regression tests. Only the startup checker changes production behavior; the verified native server, Android APK, bridge and database remain valid. Do not repeat B, C or D. Disconnect WAN again while retaining local Ethernet, then run:

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

Expected W02–W06 PASS and **W07 UNIFIED GAME SERVICES READY**: database 27018, admin 18765, account bridge 15001, shared Teams 15002, native Multiplayer 15000. Keep all five windows open. Do not select the old `runtime` folder. Startup socket checks do not prove Android gameplay.

## F. Install without changing the saved profile

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Send the saved install log.' }
}
```

Expected: ANDROID ACCOUNT GAME INSTALL COMPLETE, installed **1192619**, then Trusted server **100.99.99.14:15001** and Start game. If trust is missing/unusable, report it without reimport/reset. No OBB transfer is needed.

## G–M. Startup, input and existing account preservation

| Step | Action | Expected |
| --- | --- | --- |
| G — clean Welcome | Start game. Open Log in and Cancel; open Sign up and Cancel. | Three direct Welcome buttons: Log in, Sign up, Quit. No extra OK, overlapping old credential modal or usable main menu behind it. Neither cancellation creates an account. |
| H — keyboard | In a login password field, enable Show password. Type the harmless sample `aAzZ1!`, deliberate Shift/Caps Lock changes, then turn Caps Lock off. Reset keyboard modifiers and append lowercase then deliberate uppercase. Clear the sample and Cancel. | Exact intended case/symbols. Reset changes only subsequent input, never existing text. Do not submit this sample or share a real password. |
| I — same account | Log in to the existing runtime-v2 player. Open Heroes -> Account details / My heroes, Campaigns and Teams. Record actual ID, hero count, forms/levels/XP and any team state. | One startup session, no extra Alliance login; existing collection/team preserved. No automatic starter hero. If no player has ever been created in runtime-v2, sign up once; otherwise reuse it. |
| J — Multiplayer Back | Open Multiplayer, then Back. | Same main-menu account remains signed in. Heroes has no Log out action; the main menu does. |
| K — logout | Main-menu Log out, Cancel one login, then log in to the same player. | Welcome covers the old UI; no gameplay access while signed out. Same ID/collection after login. |
| L — complete Quit | Main-menu Quit. Reopen from LDPlayer's app icon, Start game, then Welcome Quit. Reopen and log in again. | Both Quit actions close the whole app task to LDPlayer's launcher, not the trusted-server setup page. Reopening retains trust but requires login. |
| M — two owned players | Identify a second existing player you own. Sequentially log in and record each account's owned heroes, then return to the first player. | The accounts are distinct and each has at least one unlocked hero/form before room Ready. Do not replace accounts or seed heroes in the database. |

If either account has no heroes, complete a normal first story scenario through **Campaigns -> Story campaigns -> Heir to the Throne** on its easiest difficulty, following its victory objective. A confirmed victory unlocks eligible participating named heroes. Record its result and collection; this is a real progression action, not a diagnostic shortcut. For a genuinely new second player, sign up once, play its own story and return to the first account. Existing story saves belong to their original account and cannot be reused to claim another account's reward.

## N. Dashboard and room settings without publishing

Open Multiplayer. Expect Create room, Review and join, Room filters and Back. Default search is `type:individual`. Try Room filters -> Every room and Standard multiplayer, then All individual rooms. Typed room/map search can combine `type:individual`, `status:waiting`, `status:playing`, `slots:open`, `gold:100`, `turns:30` or `turns:unlimited`. An empty server legitimately shows zero rooms; it is not a failure.

Choose Create room, a standalone two-player map, and inspect its turn/fog/timer settings. Continue to Individual battle room and starting gold, then Back at the final Publish confirmation. Expected: no published room or battle. Map sides determine capacity; this does not use permanent Teams or areas.

## O. Publish a two-player room

Create a new room, e.g. `Individual test`, on a normal two-player map. Choose a finite turn limit such as 10 for this first test,100 starting gold, fog as preferred and no turn timer. Keep the map and its displayed rules for the report. Select Individual battle room and confirm Publish.

Expected: one host and one open human seat. No manual Start button can start it. Open your own side's hero control and Room settings. Record the **numeric Room ID**, map, capacity 2, gold 100 and turn limit. This Room ID is not a team-plan UUID. Room settings show side alliances, economy, fog/shroud/timer and occupancy. The normal map's temporary alliances do not require Teams membership.

## P. Choose hero; Ready alone must not start

Select an owned hero/form on your side. Wait for its confirmed label, then open the side again. Choose Set myself ready and review the settings; Back first must leave you Not ready. Reopen, agree to Ready, then inspect status.

Expected: your chosen hero/level,1/2 players, and no start while the other seat is empty. Set myself not ready, then Ready again. No permanent XP/rating changes. Individual rooms always wait for full capacity, even if everyone currently present is Ready.

## Q. Join a companion in the same LDPlayer; test departure

Keep the first player in the visible staging room. Open a **new normal PowerShell window** and run the following block. Enter the second player's username and the numeric Room ID when asked. Its password is requested privately by the helper, never in this command or a report.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $companionUser = Read-Host 'Second player username (not the visible player)'
    $roomNumber = Read-Host 'Numeric Room ID shown in Room settings'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidIndividualCompanion.ps1' `
        -Username $companionUser -RoomId $roomNumber
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'If you deliberately cancelled before Ready, report that cancellation. Otherwise stop and send the sanitized companion report.'
    }
}
```

The helper verifies the installed 1192619 APK, private app data and trust; asks `CONTROL <username>` before its one login; lets you choose an owned hero/form; displays current room rules; then asks `JOIN <username>`. Confirm Join. At its later `READY <username>` prompt, **press Enter to cancel this first run**. Cancellation is expected for this step and can return a nonzero exit. Only the helper's owned process/session should stop; the visible game stays open.

Expected: before cancellation, the visible room gains the second player and invalidates earlier Ready consent. After departure it returns to 1/2, the departed seat is open, and remaining players need fresh Ready. It must not start. Save the sanitized `diagnostics\android-individual-companion-*.json` report. Do not enter the visible player's credentials into the helper.

## R. Rejoin and consent to the current room

Run Q's block again with the same second account and current Room ID. Confirm CONTROL, choose its hero/form, review and confirm JOIN. Keep its new READY prompt pending. On the visible host, check the latest 2/2 roster and both hero labels; reselect the host hero only if it was lost, then open Set myself ready. Cancel that review once, confirm Not ready, then accept Ready.

Expected: full room but no start because the companion has not yet readied. Review the helper's current rules and type its exact READY confirmation. If the helper displays a newer revision and asks again after a genuine room/hero/readiness change, review and confirm that new snapshot explicitly. Consent is never silently renewed. Do not edit settings after final consent in this first battle.

## S. Automatic start and real play

With both players Ready, expect automatic entry into the normal native game; no manual Start action. The companion prints **INDIVIDUAL COMPANION STARTED** and controls only its own side. The visible first player controls only their own side, with the selected hero and reviewed gold/turn/fog settings.

Play at least two complete rounds: recruit, move and attack when possible; let the computer take its turns. Continue to normal victory/defeat or the chosen finite turn limit. Expect synchronized turn progression without an out-of-sync error. Finishing the native game should produce **INDIVIDUAL COMPANION FINISHED**, helper I05 completion and I06 confirmed session revocation. The helper is an additional authenticated computer player, not evidence of two humans or two emulator instances.

## T. Completion, history and no permanent rewards

Return to the dashboard after leaving the ended room. Its closed room should disappear, not remain joinable. Inspect Heroes on both accounts sequentially after the companion exits. Compare against M: individual battles award no permanent hero XP, team XP or rating. Native in-battle XP/advancement and local saves/replays use the usual engine rules and are separate from account progression. Record the final native outcome and both unchanged permanent collections.

## U. Host closure and map-defined capacity

Publish another room without making everyone Ready. Leave as its host. Expected: room closes, no battle/reward; any joined companion is disconnected and reports that its run did not complete. This is an expected incomplete companion result only when you deliberately close the room.

Create a four-player map next. Inspect 4 human slots and its temporary side alliances, then leave without filling them. Expected: it cannot start early with 1–2 players. VPS tests cover capacity through 8; additional Windows seats can be tested later using more owned-account companions in this same LDPlayer if resources allow. Another emulator or phone is not required.

## V. Live dashboard scope

The native server publishes occupancy, Ready count and waiting/full/starting/playing status to lobby clients. The VPS suite tests those pushes and stale/full joins, and the UI fixture renders the resulting dashboard/details. With one visible Android client hosting and a headless guest, the host can inspect live staging/settings but cannot simultaneously view a second human's dashboard. Report only what you observed; do not mark a second Android dashboard or multiple-human test passed. If another player is available later, use Review and join to test their room without changing this workflow.

## W. Standard multiplayer remains usable

Use Room filters -> Standard multiplayer when browsing manual rooms. Create a standard map, choose **Standard multiplayer (manual start)** in the mode prompt, keep your side human and add computer opponents. Select your owned hero, Ready and start manually. Play a round, save and leave. Host that saved game through the normal load path and resume.

Expected: legacy computer/manual/save behavior remains, with frozen saved hero/combat state and no permanent rewards. Individual automatic-start rules must not be imposed on this mode. Return with Back and retain the account session.

## X. Controlled account-network loss and recovery

Save/leave any active game and stop any companion first. Keep the visible app signed in and idle on its main menu. Stop only the **account bridge 15001** with Ctrl+C and wait for its prompt; leave the other four services running. Return focus to LDPlayer.

Expected: automatic local sign-out and a connection-lost/sign-in explanation over an opaque background, usually after the 3-second check interval plus up to 10 seconds request timeout and UI scheduling. No usable old menu behind it. One attempted login while the bridge is stopped must show a connection error, not quit the app or grant access. Cancel stays in authentication. This checks local network-service loss; disconnected WAN alone must not sign out a healthy LAN game.

Restart only the bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require READY, then log in to the **same player**. Expect the same ID/collection. Optional targeted foreground check: stop the bridge again and immediately choose Multiplayer before the periodic monitor reacts; expect connection error/authentication rather than app exit. If the monitor wins the timing race, report that honestly and restart/recover once; repeated racing clicks are unnecessary. An unreachable server cannot confirm revocation of the old session; the UI must still clear it locally.

## Y. Existing progression and Teams regression

Inspect Campaigns, Heroes and Teams with the recovered account; they must reuse this session. Existing teams/plans and collections must remain. Resume any already-started product acceptance at J–Z in [UNIFIED_GAME_ACCEPTANCE_1192617.md](UNIFIED_GAME_ACCEPTANCE_1192617.md), using the **current accounts/runtime-v2**, not its historical new-account/reset instructions. In its ordinary Multiplayer step choose Standard multiplayer. The shared Team companion remains `Run-AndroidAllianceCompanion.ps1`; it is different from the individual-room helper and now checks 1192619.

Do not claim all campaign branches, Team settlement/replay, administrative recovery or multiple-human acceptance from one individual battle. Previously accepted tests remain accepted; report untouched tests as NOT RUN.

## Z. Report and targeted retest

Return A–Z as PASS, FAILED, EXPECTED CANCELLATION or NOT RUN, with:

- both printed commits and installed 1192619;
- WAN disconnected/local Ethernet retained for the batch, noting any change;
- actual player IDs, selected hero/form/level and before/after permanent XP;
- numeric Room ID, map, capacity, gold/turn/fog settings;
- companion sanitized report path/result, two-round/native-end outcome;
- first failing step/substep, exact message and relevant build/install/workflow/companion log.

Do not send private credentials/runtime/backups. I will reproduce the reported failure on the VPS, fix and verify it, commit/push, then provide exact pull/build/run/retest commands and expected results. Only the changed components and affected regressions need repeating. A successful VPS test is never recorded as your Windows/LDPlayer acceptance.
