# Alliance team battle — release 1192615

**Current user checkpoint:** A's pulls, B's cold backup, C's Windows bridge rebuild and D's Windows Android1192615 rebuild have passed. Continue at **E** with the existing checkouts and completed builds; no additional pull or rebuild is needed. Keep WAN disconnected/local Ethernet retained. Start the four Alliance services, keep their windows open and report the workflow result before F installation. New APK installation and gameplay checks remain pending.

This is the next complete Windows/LDPlayer acceptance batch. Earlier account, membership, planning and local-practice results remain accepted. The new campaign progression, shared battles, result settlement, replay retrieval and recovery must be tested on your computer. VPS results do not establish Windows acceptance.

Use **one LDPlayer instance**. The new companion helper runs separately authenticated, computer-controlled engine processes inside that same instance for the other fixed seats. These are real network clients, but they do not establish multiple-human synchronization or separate-device connectivity. Start with 2v2. Larger formats need enough memory for six/eight engine processes; report resource limits rather than starting another emulator.

Keep the existing MSYS2, Python, SDK/NDK, game data, OBB, public profile and database. No dependency installation, database initialization, password reset, app-data clearing or profile reimport is part of this update. The internet database in `.env` is unused.

## A. Stop, pull and record the delivered commits

Finish or save local practice, then quit the Android game. If an earlier shared battle is still active, finish its result review before updating; do not abandon it by resetting the database. Stop any companion, shared-battle, account-bridge and admin windows with Ctrl+C, then stop the database last. Wait for their prompts. Do not terminate processes or delete locks.

Temporarily connect Windows to GitHub and run:

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
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the delivered commit.' }
    }
}
```

Expected: both updates succeed and print their commit IDs. Disconnect WAN again while keeping local Ethernet and LDPlayer available. Record WAN status once for this batch; if it changes, report which steps were affected.

## B. Make a cold database/replay backup

All Alliance service windows must be stopped. Run this in a new PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $backup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192615-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Backup -DestinationPath $backup `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Backup stopped. Send only its sanitized diagnostic log.' }
    Write-Host "Keep this private pre-update backup path: $backup"
}
```

Expected: MA03 maintenance complete, with a new backup destination. Existing runtime is unchanged. The backup contains private database credentials and player data: keep it locally. The separate TLS identity at `wesnoth_server\runtime\alliance-transport` is preserved in place and is not included in this runtime backup.

## C. Rebuild the account bridge

Before this first C run, update the server helper. Review found a mismatch between the old three-input receipt check and the new four-input bridge build. The correction preserves either completed prior version and requires all current inputs after rebuilding. Temporarily connect Windows to GitHub and run this targeted pull once:

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

Disconnect WAN again, retain local Ethernet, and keep all Alliance services stopped. Your completed B backup remains valid. Run the rebuild:

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild failed. Send its rebuild/build logs.' }
}
```

Expected: `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`. The previous bridge is retained. The original guest server on port15000 is separate and does not need rebuilding for this batch.

## D. Build the new Android update offline

```powershell
& {
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send the saved rebuild/build logs.' }
}
```

Expected: retained prior account stages, new1192615 build and `ANDROID ACCOUNT GAME REBUILD COMPLETE`. Original engine/dependency stages and OBB remain intact. A failure does not authorize deleting a stage or its update journal; send the first error and saved logs.

## E. Start all four services in order

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles
    if ($LASTEXITCODE -ne 0) { throw 'Service startup stopped. Send the workflow text and JSON reports.' }
}
```

Expected: the helper checks configuration, starts missing services in separate windows, and reports readiness. Keep those windows open:

| Service | Expected address |
| --- | --- |
| MongoDB | 127.0.0.1:27018 |
| Admin website | http://127.0.0.1:18765/ |
| Account bridge | 100.99.99.14:15001 |
| Shared battle service | 100.99.99.14:15002 |

The shared window must show `ALLIANCE SHARED BATTLE SERVICE READY`. The launcher requires backend release1192615. If it reports an older running service at W03, stop that admin window with Ctrl+C, restart it with Run-WindowsAlliance.ps1, and repeat step E. The launcher does not terminate or automatically reload that process. For later health checks, rerun this command with `-CheckOnly`; it changes no service state. If LAN access fails, send the exact marker and workflow report before changing firewall or certificate settings.

## F. Install while retaining the trusted server

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Send the saved install log.' }
}
```

Expected: `ANDROID ACCOUNT GAME INSTALL COMPLETE`, version1192615, and the existing Trusted server100.99.99.14:15001. Choose Start game -> Alliance -> Log in. Record the existing player IDs, leaders/XP, both team IDs/rosters/XP/rating and area IDs before earning rewards. If the profile is missing, stop instead of reimporting or clearing data.

## G–Z. Gameplay, persistence and operator checks

Use the existing four accounts sequentially in the GUI: UniPlayer/UniRecruit in Koichi; UniSolo/UniRival in RivalPlan. Adjust only if the actual saved membership differs, and report that difference. Passwords are entered locally and must never be included in reports.

| Step | Action | Expected result |
| --- | --- | --- |
| G | As UniPlayer open Teams -> Captain orders, write a short plan, confirm it; then view as UniRecruit. Back from a new order must not publish. | The same saved order appears to both members; only the captain can post. No XP/readiness changes. |
| H | As UniPlayer open Campaign progression, start the first unlocked mission, read its objectives, recruit/move/fight and win. Return to Campaign progression -> Send completed result. | A real Victory is recorded with a run ID/replay. Confirming the saved result adds exactly20 personal XP and unlocks the next mission. Team XP/rating are unchanged. |
| I | Reopen Send completed result and Campaign history; log out/in and inspect the leader again. | The acknowledged result cannot grant another reward. The same run and total XP remain saved. |
| J | Win and submit the second and third missions. Choose leader advancement when available. | Each new victory adds20XP. A Spearman starting at0 reaches60 totalXP; choosing Swordsman or Pikeman consumes42 currentXP, leaving18 and level2. Other starter trees use their own thresholds. The chosen unit appears in later games. |
| K | Start another unlocked mission, quit unfinished, then inspect/cancel that exact unfinished run. Separately finish a mission with Defeat and submit its result. | Quit/cancel and defeat grant0XP; cancellation releases the reservation. Ordinary stock Load cannot resume an Alliance save for rewards. Do not cancel a completed result waiting to be sent. |
| L | Campaign history -> a completed run -> Watch replay. Watch through END, then inspect progression. | The recorded mission plays; viewing it grants no additional reward. Replay availability is local to the device for campaign runs. |
| M | Create a NEW Isar's Cross2v2 plan using Koichi sides1 UniPlayer/4 UniRecruit and RivalPlan sides2 UniSolo/3 UniRival. Both captains approve; leave the selected players Not ready until step N. Record the new Battle plan ID. | Lineups use current saved leaders, including advancement. If a selected leader has an unchosen advancement, choose it in Campaign progression before preparing the plan. All four Ready and both approvals are required for shared start. Old cancelled plans remain inactive. |
| N | Before everyone is Ready, check Practice with only your own Ready and both approvals; then return to menu and finish readiness. | Individual practice remains available, awards nothing and does not reserve/start/complete the shared plan. Shared start still waits for every fixed player. |
| O | Use the companion commands below for UniRecruit, UniSolo and UniRival in three separate PowerShell windows. Then log in as UniPlayer in LDPlayer and choose the plan's Join shared battle action. | Each companion explicitly authenticates its own fixed seat. All four load the same map before the battle starts. Your GUI controls only UniPlayer's army. |
| P | Recruit/move/attack and End Turn through at least two full rounds. | Other authenticated seats play automatically; alliances and leaders match the plan. Control returns to you without synchronization errors. |
| Q | During your turn, quit to the main menu without ending the battle, then reopen the same plan and Reconnect. After this passes, perform the controlled shared-service restart below. | Both reconnects return to the existing army/turn with earlier moves retained. No new army, reservation or reward is created. Other clients wait when your seat is needed. |
| R | Finish the shared battle by defeating the opposing leaders, or use the explicitly confirmed captain Surrender action described below. Let all companion processes finish. | Every participant records END and uploads its replay. Companion success requires its own acknowledged result. No XP is awarded while player reports or captain confirmations are missing. |
| S | Log in as each captain sequentially -> the same battle -> Review shared battle result -> confirm the matching outcome. | Only after all reports agree and both captains confirm does the plan become completed. Winner:20 leaderXP/player and100 teamXP; loser:10 leaderXP/player and25 teamXP; draw:10/player and50/team. Team level is1+floor(teamXP/500). Elo changes once; equal1000-rated teams become1012/988 after a decisive result. |
| T | Watch the completed battle's verified local replay. As the other captain, use Download completed battle replay if no local recording exists, then Watch replay. | Server download is authenticated and verified. Playback reaches the recorded END and grants no XP. Cancelled/incomplete plans never offer a completed replay. |
| U | Record values, quit the app, stop services in reverse order, restart with step E, reopen/login and inspect the same completed run. Reopen result review. | Same player/team IDs, replay/result/XP/rating remain. Repeated review or an acknowledged-result retry cannot award twice. |
| V | Add one new player to each team through normal registration/application/approval. Make a NEW Hexcake3v3 plan; both captains approve and all six selected players choose Ready. Run five companions and one GUI client. Play and complete/confirm. | Fixed sides1/4/5 oppose2/3/6; six authenticated seats, normal END/rewards/replay. Report insufficient memory as a blocked acceptance step, not a pass. |
| W | Add a fourth player to each team, then repeat on NEW Mokena Prairie4v4 with seven companions and the GUI. | Sides1/3/5/8 oppose2/4/6/7; eight fixed seats and unchanged eight-member team capacity. Finish and confirm before another progression run. |
| X | On separate NEW2v2 plans, test captain confirmation Back, surrender, and mutual draw using the captain-policy helper below. | Back sends no decision. Surrender makes the opposing team win. One draw offer does not end a battle; both captains' offers produce a draw. Replays retain these outcomes; normal player-report/captain-confirmation settlement still applies. |
| Y | In the local admin website inspect Accounts, Teams, Areas, Runs and Audit. On a disposable test player outside any run, apply a+1XP correction with a reason, then-1 with another reason. Create a disposable area and edit its enabled/maps settings. Inspect the completed battle review. | Corrections are bounded/audited, do not change leader type/membership, and restore that player's startingXP. Area restrictions govern new plans. Result resolution is for disputed runs and requires a reason; never invent a dispute by editing MongoDB. Automated VPS tests cover conflicting results and duplicate resolution. |
| Z | Stop all services, make a new post-test backup, then restore it into a NEW separate destination using the commands below. | Restore checks authentication, replica set, schema and rollback, then stops its temporary database. It does not replace or activate your normal runtime. Restart normal services with step E and confirm your latest state. |

### Companion commands for step O

Copy the actual new UUID from step M. In **each separate PowerShell window**, set `$battle` to that UUID, then run one command, changing only the username:

```powershell
$battle = 'PASTE-THE-NEW-BATTLE-PLAN-UUID-HERE'
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidAllianceCompanion.ps1' `
    -Username 'UniRecruit' -BattleId $battle
```

Repeat for UniSolo and UniRival. Review the selected account/battle/control policy and type the requested confirmation, then enter that player's password at the hidden prompt. After authentication, check the printed fixed side. No password appears in command arguments. Keep all companion windows open. They wait for the GUI player and the other fixed seats. Normal success ends with a verified acknowledged result and a saved sanitized companion report. They are separate computer-controlled accounts; do not simultaneously use the same account in the GUI.

If a companion disconnects mid-game, rerun its **same account and same battle** command to reconnect. If END already occurred and only its result upload failed, use the same command with `-RetryResult`; this sends the retained result/replay without starting another battle. Do not remove its private journal or replay. Send the sanitized error/report if a retry fails.

### Controlled shared-service restart for step Q

After the ordinary client reconnect succeeds, wait until UniPlayer's turn and return to the main menu again. Stop **only the shared battle service** window with Ctrl+C and wait for its prompt. Leave MongoDB, the admin service and the account bridge running. The three companion windows should report a disconnect; these particular errors are intentional in this subcheck. Wait for all three helper commands to finish.

Rerun the step E startup command. It should start the missing shared service and keep the other healthy services. Rerun each companion's same account and exact same Battle plan ID command, then choose Reconnect for that same plan in the GUI. Use normal companion mode, not RetryResult, because END has not occurred. Expect the same map, armies, side/turn and previous moves. Do not create a new plan, cancel, change readiness or reset data. Stop and report any different recovery error. Continue step R only after the recovered battle is consistent.

### Captain actions for step X

During your selected captain's own turn, open the game's context menu and choose Alliance: surrender team, offer draw or withdraw draw offer. The confirmation opens with Back selected by default; Back sends no decision. These controls apply to a captain occupying a fixed battle seat; an off-lineup captain still handles planning, orders and result confirmation.

For a one-LDPlayer mutual-draw test, replace the usual UniSolo AI companion with the explicit captain-policy command below on a fresh plan. This policy passes its turns and sends one draw offer on/after its first available turn. It does not play the army tactically. UniPlayer offers a draw through the actual GUI, so both captain decisions are exercised.

```powershell
$battle = 'PASTE-THE-NEW-DRAW-TEST-UUID-HERE'
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Run-AndroidAllianceCompanion.ps1' `
    -Username 'UniSolo' -BattleId $battle -CaptainAction OfferDraw -AfterTurn 1
```

The helper requires explicit action/turn consent. Do not use CaptainAction with RetryResult. `Surrender` and `WithdrawDraw` are also bounded test policies; the normal companion command remains ordinary AI. To check withdrawal, offer then withdraw through the GUI before the other captain's delayed offer (for example AfterTurn3); the battle must continue until both current offers exist.

### Backup and isolated restore for step Z

Stop all four service windows first. Run in one PowerShell block so the exact newly created backup is used:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $root = Join-Path $env:LOCALAPPDATA 'WesnothAlliance'
    $tag = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $backup = Join-Path $root ('backups\after-1192615-' + $tag)
    $restore = Join-Path $root ('restore-checks\1192615-' + $tag)
    $helper = 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1'
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper `
        -Operation Backup -DestinationPath $backup -RuntimeRoot (Join-Path $root 'runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Post-test backup failed. Send its sanitized log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper `
        -Operation Restore -BackupPath $backup -DestinationPath $restore `
        -RuntimeRoot (Join-Path $root 'runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Isolated restore failed. Preserve both new folders and send its sanitized log.' }
}
```

Do not point your normal launchers at the restored test folder. Keep it and the backups privately. Re-running step E selects the original runtime.

## Report and targeted retest

You may stop after any step and report it before continuing. On the first unexpected result, preserve the current plan/run, logs and stages; send the failed letter, exact message and sanitized log filename. Do not keep retrying mutations, clear the database, delete locks or rebuild old dependencies.

Example after A–F pass and G fails (change the letters to your actual results):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\New-WindowsAllianceTestReport.ps1' `
    -BatchId '1192615' -WanStatus Disconnected `
    -PassedSteps 'A,B,C,D,E,F' -FailedSteps 'G' `
    -NotRunSteps 'H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z'
```

This helper records **your observations**; it does not execute the tests. Send its JSON, relevant build/install/workflow/companion logs, exact battle/run IDs and before/after XP/rating for reward failures. Never send passwords, tokens, `.env`, runtime credentials, private identity files or full database backups.

For a reported failure, the development cycle is: reproduce/analyze on VPS -> fix and regression test -> commit/push -> precise pull/rebuild/restart instructions for affected components only -> repeat the failed step and a nearby regression check. Earlier accepted steps remain accepted unless the fix changes them. Windows/LDPlayer results and WAN observations are recorded separately from VPS verification.
