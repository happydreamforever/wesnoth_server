# Unified game — release 1192617 Windows acceptance

This batch replaces the former separate Alliance account/leader flow with one startup account, a collection of campaign heroes, and hero selection for multiplayer and teams. VPS verification and Windows acceptance are recorded separately. The Windows results below are pending until you return them.

Use the existing **one LDPlayer instance**, MSYS2, Python, SDK/NDK, supplied 1.19.26 data and installed OBB. No dependency upgrade, OBB transfer or trusted-profile reimport is required. The internet MongoDB URL in `.env` is unused. The authorized fresh database is created beside the old runtime; it is not an in-place migration. Old accounts/teams stay in the old backup/runtime. You will create new administrator/player accounts and earn heroes through campaigns.

Report each step before continuing if you prefer. At the first unexpected result, stop that test and send its letter, exact message and sanitized log. Do not delete stages, journals, locks or runtime data. Record WAN status once per batch; keep local Ethernet and LDPlayer available.

## Current checkpoint — A–B accepted; run C next

Step A reached server `73460b1` and client `ee71821`; the subsequent Git integrity checks passed with only the existing README edits. Step B now reports ALLIANCE BACKUP VERIFIED, 110 files / 258,474,865 bytes and MA03 completion. The user explicitly confirms WAN was disconnected while Ethernet stayed connected. `schema_checked: false` is expected for cold backup.

Keep the exact private backup at `%LOCALAPPDATA%\WesnothAlliance\backups\before-1192617-20261023-100621-012` for F. The saved diagnostic is `diagnostics/alliance-maintenance-20261023-100621-819-6c2fb4025ae3458a900a03d4a6d9c8cf.txt`. No service was activated and the existing runtime was preserved.

Continue directly at **C** using the existing checkout. No further pull or backup is required. Keep all services stopped and WAN disconnected/local Ethernet retained through F. C–Z remain pending; A and B below are retained as reference and should not be repeated now.

## A. Stop services and pull both repositories

Save/quit the game. Stop companions, native multiplayer, shared battles, account bridge and admin service with Ctrl+C; stop MongoDB last. Wait for their prompts. Temporarily connect Windows to GitHub:

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
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the delivered commit.' }
    }
}
```

Expected: both pulls succeed and print commit IDs. Disconnect WAN, retain local Ethernet. Keep all game services stopped through F. Existing Git file-mode settings remain in place; do not stash/reset local work blindly if a pull stops.

## B. Make a new cold backup of the old game

Use a new backup now: an earlier backup may not include your latest accounts, teams or battles.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $backup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192617-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Backup -DestinationPath $backup `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Backup stopped. Send its sanitized diagnostic log.' }
    Write-Host "Keep this exact private backup path for step F: $backup"
}
```

Expected: `ALLIANCE BACKUP VERIFIED`, then MA03 completion. `schema_checked: false` is normal for a cold backup. Keep the backup locally; it contains credentials and player data. The separate TLS identity remains in `wesnoth_server\runtime\alliance-transport`. Do not start or change the old runtime between B and F.

## C. Rebuild the account bridge

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild failed. Send its rebuild/build logs.' }
}
```

Expected: previous bridge retained, `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`. The new account protocol and hero catalogue require the coordinated client/server update. Keep services stopped afterward and continue at D; the wrapper's generic suggestion to run the bridge does not replace this batch order.

## D. Build authenticated ordinary Multiplayer

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Multiplayer build failed. Send the saved log.' }
}
```

Expected: `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` and `UNIFIED MULTIPLAYER BUILD PASSED`. This uses a separate `build\windows-unified-mingw64` stage. The earlier guest-server build remains retained; do not run it alongside the new server on port15000. A same-input interrupted build can be resumed. After a later source correction, use `-PreservePreviousBuild` only as directed; it retains a verified completed prior stage before rebuilding.

## E. Build Android 1192617 offline

```powershell
& {
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send the saved rebuild/build logs.' }
}
```

Expected: both previous account stages retained, native build and offline Gradle complete, `ANDROID ACCOUNT GAME REBUILD COMPLETE`. Pinned foundation objects, dependencies and OBB remain intact. Keep any interrupted update journal for analysis.

## F. Create the new database beside the old one

Paste the exact backup path printed in B when this block asks for it. Enter only the new administrator credentials at the helper's private prompts. The administrator is separate from game players.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $backup = Read-Host 'Paste the full private backup path from step B'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Initialize-WindowsUnifiedGame.ps1' `
        -BackupPath $backup `
        -PreviousRuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2')
    if ($LASTEXITCODE -ne 0) { throw 'Fresh initialization stopped. Send only the console error, never credentials.' }
}
```

Expected: `UNIFIED FRESH START VERIFIED`, `schema_version: 2`, old runtime/backup preserved and new database stopped. Repeating the exact command after success reuses the completed new runtime; it must not erase new accounts. If initialization is interrupted, retain the incomplete target and report the error. Do not choose another target to work around a failure.

From now on **every service uses runtime-v2**. Older saved campaign/account identities are not silently reassigned to newly registered users, even if usernames match.

## G. Start all five services in order

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles
    if ($LASTEXITCODE -ne 0) { throw 'Startup stopped. Send the workflow text and JSON reports.' }
}
```

Expected: W01 runtime/identity, W02 database, W03 backend, W04 bridge, W05 shared battles, W06 native Multiplayer, then **W07 UNIFIED GAME SERVICES READY**. Keep all five service windows open.

| Service | Address |
| --- | --- |
| MongoDB | 127.0.0.1:27018 |
| Admin website | http://127.0.0.1:18765/ |
| Account bridge | saved Windows address:15001 |
| Shared teams | saved Windows address:15002 |
| Native Multiplayer | saved Windows address:15000 |

The saved address was 100.99.99.14. If it no longer belongs to Windows, report that result before changing the trusted profile. An older running backend or guest server is rejected rather than silently accepted. Later use the same command with `-CheckOnly` for read-only health checks.

## H. Install with the saved trusted connection

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Send the saved install log.' }
}
```

Expected: `ANDROID ACCOUNT GAME INSTALL COMPLETE`, installed version1192617, and the existing Trusted server100.99.99.14:15001. Choose Start game. If the profile is missing/unusable, report the message without clearing data or reimporting.

## I–Z. Functional acceptance

Use new player accounts, for example UniPlayer, UniRecruit, UniSolo and UniRival. Reusing those usernames is allowed, but their new IDs must differ from the old database. Record IDs/XP as observed; do not copy the historical baseline. Passwords never belong in a test report.

| Step | Actions | Expected result |
| --- | --- | --- |
| I — startup/session | Start game. Try Back without login, then Sign up as UniPlayer. Open Heroes, Campaigns and Teams. Log out, try one wrong password, then log in correctly. Quit/reopen and log in. | No unauthenticated gameplay path. Signup has no starter selection and signs in once. New Heroes collection is empty. Modes reuse the same session; no additional Alliance login. Wrong password is rejected; saved trusted connection survives restart. |
| J — first story victory | Campaigns -> Story campaigns -> Heir to the Throne, easiest difficulty. Play its first scenario according to its normal objectives. Save once during play, finish with Victory, then inspect Heroes. | Original story units/stats/objectives remain. Eligible named heroes that participated become owned with their earned forms. Each receives actual earned combat/supported script XP plus20 victoryXP; ordinary recruits do not enter the collection. No teamXP/rating. Record each visible hero and XP. |
| K — save/recall/forms | Continue that playthrough. Save/quit/reopen with the same account; load and continue. Deploy a named companion, exercise recalls and a natural advancement/transformation when available, then win. In a separate account, try loading the first account's bound save. | Same-account continuation preserves scenario state and its XP ledger. Eligible deployed/recall/departed participants are tracked; unused recalled-list heroes do not receive a free victory award. Earned forms share the canonical hero's XP. Another account cannot claim the save. Report the campaign/scenario/hero for any mismatch. |
| L — repeat, defeat and delayed delivery | Record XP. Replay the already rewarded checkpoint from its retained save and win again. Start a genuinely NEW story playthrough and win. Separately lose a scenario. For delayed delivery, stop only the account bridge just before a saved scenario victory, finish, then restart the missing bridge with G and log in again. | Same checkpoint awards once; each scenario grants XP once per playthrough. A genuine same-scenario revisit can unlock new eligible forms/heroes without repeatXP; a new playthrough can earnXP again. An older already-advanced branch may refuse continuation rather than create a new reward sequence. Defeat grants0 permanentXP. Failed delivery retains a private pending result and retries after reconnection, awarding once. Do not clear game data. Record before/afterXP and the exact error/result. |
| M — owned hero growth/training | Heroes -> inspect owned heroes/forms. Campaigns -> Hero training -> choose an unlocked mission and an owned hero/form; win, then inspect that hero. Retry pending results/history, watch its local replay. Also test an unfinished training cancellation and a defeat. | Victory adds20XP to the selected hero only; cancellation/defeat add0. Other heroes/team/rating stay unchanged. Forms share heroXP. Level costs5L²+15; accumulated growth affects later multiplayer/training, not story starting stats. Replay/retry never awards twice. |
| N — ordinary Multiplayer | Main-menu Multiplayer opens the trusted lobby using the current account. Create a normal map with your human side and computer opponents. Choose your owned hero/form before Ready; Back from a selection leaves it unchanged. Play two rounds, save, finish/leave and inspect Heroes. Then host the saved game and resume. | No second login or guest nickname. Human side requires owned selection and Ready. Original map/recruitment/turn flow remains. HeroHP/damage use permanent level; movement/strikes/resistances/innate abilities remain. No permanentXP/rating. Resume retains the saved hero/army/combat state; no fresh healing or hero replacement. |
| O — teams/membership | Create the other three players sequentially. Each must win a real story scenario to unlock a hero. In the admin website create/enable Yama if needed. UniPlayer creates Koichi; UniSolo creates RivalPlan. UniRecruit applies to Koichi and UniRival to RivalPlan; captains approve. Test withdrawal/rejection/decision history with a disposable application. Post and view captain orders. | Empty signup collections require real unlocks. Applications, decisions, member-only views and captain permissions remain correct. Each team has2/8 members; player collection details replace the former single starter. Membership/captain changes invalidate affected draft consent. |
| P — fixed hero choice/readiness | Create NEW Isar's Cross 2v2 plan: Koichi sides1/4 and RivalPlan sides2/3. Each player selects an owned hero/form before Ready. Both captains approve; set Ready. Change one player's hero/form, inspect all actors, then reapprove/re-ready. | Unowned/absent hero cannot be readied. Confirmed selection change clears every Ready flag and both approvals. Plan shows the chosen hero, form and permanent level per seat. Back does not mutate. Cancelled/stale plans remain inactive; leaving/rejoining cannot retain valid old consent. |
| Q — individual practice | With both approvals but only your own Ready, open Practice. Test My side, Command my team and Local hotseat, including saved-game load. Set yourself Not ready; separately cancel a disposable plan. | Practice appears after your own Ready; no Ready-and-practice shortcut. Actual copies use selected hero/forms/scaling. No persistent reward/reservation/shared completion. Not ready, cancelled and stale plans cannot start new practice. |
| R — shared 2v2 | Finish all four selections/Ready/approvals. Use the companion commands below for the other three fixed accounts. Log in as UniPlayer in LDPlayer, join the same shared plan. Play at least two rounds. | All four authenticated seats load before start. Each controls its fixed army; same hero/form/stats/alliance/map. Companion seats are computer-controlled. No synchronization error; control returns to you. |
| S — reconnect | During UniPlayer's turn return to menu without completing the battle, then reconnect to the same plan. After this passes, perform the controlled shared-service restart below. | Same army, position, turn and immutable hero snapshot; no new battle/reward. Missing seat pauses progression as needed. No hero switch while a run is active. |
| T — completion/settlement | Finish the battle, let every companion acknowledge END/replay, then log in as both captains sequentially and confirm the matching result. Reopen result review. | Settlement waits for consistent reports and both captain confirmations. Winner20XP/selectedhero and100teamXP; loser10/selectedhero and25teamXP; draw10/selectedhero and50teamXP. Other owned heroes stay unchanged. Team level1+floor(teamXP/500); Elo changes once. Repeated review cannot award twice. |
| U — replay | Watch the completed local replay; as the other captain download the completed replay if needed and watch through END. Inspect Heroes/team values afterward. | Verified replay contains original frozen heroes and outcome. No additional rewards. Cancelled/incomplete plans offer no completed replay. |
| V — larger teams | Add one story-qualified player per team; create/complete NEW Hexcake 3v3 with five companions. Add another per team; repeat NEW Mokena Prairie 4v4 with seven companions. Choose heroes, approve and ready every seat. | Fixed 6/8-seat ownership, all-loaded start, normal synchronization, results/replay and selected-hero-only rewards. Same one LDPlayer; report insufficient memory as blocked acceptance, not pass. No second emulator is required. |
| W — captain decisions | On NEW plans test confirmation Back, surrender and mutual draw. Use the explicit captain-policy command below for the opposing captain. Test offer/withdraw/reoffer. | Back sends nothing; surrender gives the other team victory; a single draw offer does not end play, both current offers do. Normal END/replay/report/confirmation settlement still applies. |
| X — admin controls | Local website: inspect accounts, individual heroes, teams, areas, runs and audit. On an unlocked test hero outside a run enter `1` in the XP correction field with a reason, then `-1` with another reason. Test disposable area enabled/map settings. Reset a disposable player's password and verify old/new password behavior. | Correct specific hero is edited/audited; no other collection changes. Area controls affect new plans. Reset invalidates sessions/unused tickets. Existing live hero snapshots remain immutable. Never edit MongoDB directly to fabricate a result. |
| Y — restart/persistence | Record new IDs, hero/forms/XP, teamXP/rating and completed run. Quit game, stop all five services in reverse order, restart with G, reopen/login and inspect the same records. | Same new database generation/IDs, collections, teams, completed result and replay. No extra reward and no profile reimport. Old1192615 account saves cannot become new account results. |
| Z — recovery | Stop all services, run the post-test backup/isolated restore below, then restart normal runtime-v2 with G. | Verified cold backup; isolated authenticated/schema/rollback restore test shuts down cleanly. Normal runtime is neither replaced nor activated from the restore. Latest new progress remains. |

For cross-campaign identity coverage, additionally win eligible scenarios featuring the same named protagonist in different stories. The same canonical hero gains a new earned form/XP; unrelated characters such as Konrad and KonradII stay separate. Completing every supplied campaign is extended content acceptance; report exactly which stories/scenarios were exercised rather than marking all 21 entries played.

## Companion seats within the existing LDPlayer

Each companion account must already own a story-earned hero, belong to the correct team, and have its selected hero/form and Ready saved on the exact plan. They do not unlock heroes automatically. In three separate PowerShell windows for R, substitute the actual plan UUID and use UniRecruit, UniSolo and UniRival respectively:

```powershell
$battle = 'PASTE-THE-NEW-BATTLE-PLAN-UUID-HERE'
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidAllianceCompanion.ps1' `
    -Username 'UniRecruit' -BattleId $battle
```

Review/confirm the account, battle and controller policy. Enter its password only at the hidden prompt. Keep the windows open; do not simultaneously use a companion account in the GUI. Success requires its acknowledged END/replay and saved sanitized report. These are real authenticated engine clients, not a multiple-human usability test.

For a mid-battle disconnect rerun the same account and battle command. If END already occurred and only result upload failed, use `-RetryResult`; keep its journal/replay. Do not automatically change the plan or create a replacement run.

For mutual draw on a fresh plan, replace UniSolo's normal companion with:

```powershell
$battle = 'PASTE-THE-NEW-DRAW-PLAN-UUID-HERE'
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidAllianceCompanion.ps1' `
    -Username 'UniSolo' -BattleId $battle -CaptainAction OfferDraw -AfterTurn 1
```

This explicit policy passes turns and sends one draw offer. UniPlayer offers through the in-game captain menu. For withdrawal testing delay the opposing offer, for example AfterTurn3. `Surrender` and `WithdrawDraw` are also explicit policies; normal companions play AI. These controls require a captain in a fixed seat.

## Controlled shared-service restart for S

After GUI reconnect passes, wait for UniPlayer's turn and return to menu. Stop only the shared-battle service with Ctrl+C and wait for its prompt. Other services remain open. Companion disconnect errors are expected in this subcheck; let their commands finish. Repeat G to start the missing shared service, then rerun the same companion accounts/exact plan and reconnect UniPlayer. Expect preserved armies/turn; continue only if consistent. Do not cancel, change readiness, reinitialize or use RetryResult before END.

## Post-test backup and isolated restore for Z

Stop all five services. Run this whole block so the restore uses the just-created backup:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $root = Join-Path $env:LOCALAPPDATA 'WesnothAlliance'
    $tag = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $backup = Join-Path $root ('backups\after-1192617-' + $tag)
    $restore = Join-Path $root ('restore-checks\1192617-' + $tag)
    $helper = 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1'
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper `
        -Operation Backup -DestinationPath $backup -RuntimeRoot (Join-Path $root 'runtime-v2')
    if ($LASTEXITCODE -ne 0) { throw 'Post-test backup failed. Send its sanitized log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper `
        -Operation Restore -BackupPath $backup -DestinationPath $restore `
        -RuntimeRoot (Join-Path $root 'runtime-v2')
    if ($LASTEXITCODE -ne 0) { throw 'Isolated restore failed. Keep both folders and send its sanitized log.' }
}
```

Keep both private folders locally; do not select the restored test folder for normal launch. The retained version1 backup can also be verified/restored into a separate folder. It stays version1 and requires matching1192615 application code to operate; restore does not migrate it or switch current services.

## Report, fix and retest

Example after A–H pass and I fails; replace these letters with your actual results:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\New-WindowsAllianceTestReport.ps1' `
    -BatchId '1192617' -WanStatus Disconnected `
    -PassedSteps 'A,B,C,D,E,F,G,H' -FailedSteps 'I' `
    -NotRunSteps 'J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z'
```

This records your observations; it does not execute gameplay checks. Send the exact error, relevant diagnostic/build/install/workflow/companion log, plan/run ID and before/after heroXP for reward problems. Never send passwords, tokens, `.env`, private identity/runtime files or database backups.

Development workflow: analyze/reproduce the first failure on VPS -> fix -> affected regression/real execution checks -> commit/push -> precise pull/rebuild/restart instructions -> repeat the failed step and affected regressions. Keep unrelated accepted results. After F has succeeded, a normal fix does not repeat the fresh-database step or reset player progress. WAN status is recorded once per batch, with changes noted. Windows rendering and multiple-human acceptance are never inferred from VPS or companion results.
