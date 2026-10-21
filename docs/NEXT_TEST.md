# Battle planning 1192606: one combined offline delivery and test

The user confirms the previous 1192605 management A–H checks with WAN disconnected. Keep that acceptance; do not repeat the old checklist. Its separate final full-service restart was not explicitly confirmed. This 1192606 batch adds saved battle planning only: approved maps, fixed lineups, both captains' explicit approval, selected-player readiness and cancellation. It cannot start combat or award XP/rating. Use one LDPlayer with sequential logins for four players; no phone or eight-account setup is required.

Preserve Koichi in Yama: team ID 4cd736d3-dc6c-4c3d-a816-e7682b56db30, original captain UniPlayer and member UniRecruit, 2/8, team level 1/XP 0/rating 1000. Keep the same accounts, saved trusted server, profile runtime, identity, OBB and every completed stage/backup. Return one combined report after this batch succeeds; stop early on any failure or uncertain mutation.

## 1. Pull once while temporarily connected

Quit the Android game. Stop the bridge and admin service with Ctrl+C in their own windows, waiting for each prompt. Keep MongoDB and LDPlayer running. In another PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Stop and send the output." }
    }
}
```

Disconnect WAN while retaining local Ethernet, and leave WAN disconnected for the build, installation, service startup and all tests below. No package download, dependency upgrade or database initialization is needed.

## 2. Rebuild the changed bridge/account stages and install in place

The helpers preserve the completed bridge and both1192605 account stages. The Android update uses a new 1192606 journal and unique before-battle-planning-ui backups, retaining all four older journals/backups. Do not manually rename/delete stages. The original engine objects, dependency stages and OBB are reused.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild failed. Send its saved logs.' }

    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send its saved logs.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Android installation failed. Send its saved log.' }
}
```

Require ALLIANCE ACCOUNT BRIDGE REBUILD PASSED, ANDROID ACCOUNT UPDATE PREPARED, ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE and installed version 1192606. On setup, confirm Wesnoth Alliance, Trusted server 100.99.99.14:15001 and Start game. If the saved profile is missing/unusable, stop and report it without reimporting/resetting. KeepSavedProfile performs no OBB transfer or data clearing.

## 3. Start fresh admin and bridge processes

With MongoDB still running, use the admin PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for ALLIANCE DATABASE CHECK PASSED and http://127.0.0.1:18765/. Keep it open. In the separate bridge window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001. Keep all three windows open, choose Start game -> Alliance, and use the planning checklist below.

## 4. Planning checks A–E in one LDPlayer

Log out and log in to switch players. Registration does not automatically log in: after creating a new player, explicitly Log in using its saved password. Do not send passwords. Select rows with Open, dismiss messages with OK, and use Back to return to the parent menu. All new proposal choices, plan actions and confirmations begin on **Back without changes**. Explicitly select the named action; default Open/Back/Escape must not submit a mutation.

Use existing UniPlayer and UniRecruit for Koichi. Reuse the separate UniSolo account from the accepted archive test if available; it should have no team. Create one additional player, UniRival, with Spearman. Use a new opponent team named RivalPlan in Yama. If those test names already belong to something else, use unused names and record the actual names/IDs. Do not rename, archive or alter an unrelated team. Keep the original Koichi captain and roster throughout these tests.

| Check | Action | Expected result |
| --- | --- | --- |
| A. Prepare four players/two teams | As UniPlayer, compare My team and View personal leader with the accepted baseline. Log in as UniSolo and confirm no team, then create RivalPlan in Yama. Register/log in UniRival, browse Yama/RivalPlan and apply. UniSolo approves through Review applications. UniRival logs in, opens/acknowledges the approval and checks My team. | Koichi remains UniPlayer captain + UniRecruit 2/8. RivalPlan has UniSolo captain + UniRival 2/8 in the same Yama area. Record both team IDs and the four player IDs from their profiles. New leaders are Spearman level 1/Experience 0/Total experience 0; both teams level 1/XP 0/rating 1000. Reuse the existing UniSolo identity rather than recreating it. |
| B. Catalog, size guard and safe choices | UniPlayer -> Teams -> Battle plans -> Propose battle. Inspect Choose battle map: Isar's Cross — 2v2, Hexcake — 3v3 and Mokena Prairie — 4v4 when enabled for Yama. Select Hexcake; then reopen Propose battle and select Mokena Prairie. Finally reopen the map selector and open the default Back without changes. | Two-member Koichi receives “Your team needs at least 3 members for this map.” / “Your team needs at least 4 members for this map.” respectively; no plan is created. The catalog identifies each enabled map and size. Default Back returns without submitting. Do not add six/eight test players for this check. |
| C. Save exact ordered 2v2 lineups | UniPlayer -> Propose battle -> Isar's Cross -> RivalPlan. In Choose lineup — Koichi select UniPlayer first (Side 1), then UniRecruit (Side 4), then Use this lineup. In RivalPlan select UniSolo first (Side 2), UniRival second (Side 3), then Use this lineup. At Confirm battle proposal first open default Back without changes; My battle plans must still be empty. Repeat the same selection and explicitly Send battle proposal. Use View fixed lineups, record the battle plan ID, then Refresh plan. | Saved state draft; same teams/map/ordered sides and leader snapshots. Both Captain approval values Waiting and all four Not ready: proposing does not approve automatically. The refresh returns the same ID and details. Return to Battle plans -> Propose battle and submit the same proposal once more; it is rejected because one of these teams already has a planned battle; My battle plans still contains only the original draft. |
| D. Member permissions and early readiness | Switch to UniRecruit -> Teams -> Battle plans. Propose battle must report that only the current captain can propose. Open My battle plans -> this plan -> View fixed lineups. Inspect the action menu. | A current member can read the same plan. Approve this plan and Cancel this battle plan are absent for the member. Set myself ready is absent while both captain approvals are not yet present. No Start action exists. These are UI permission observations; automated backend fixtures cover forged requests. |
| E. Both approvals and four ready flags | UniPlayer opens the plan -> Approve this plan; first leave its confirmation through default Back without changes and reopen/refresh to verify Waiting. Then Approve this plan -> Approve saved map and lineups. UniSolo opens the same plan and explicitly approves it too. Each of UniSolo, UniPlayer, UniRecruit and UniRival then chooses Set myself ready -> Set myself ready in its confirmation. As UniRecruit, choose Set myself not ready -> Set myself not ready, refresh, then set ready again. Finish with View fixed lineups from both captains. | Both Captain approval values Approved only after their separate confirmations; only the logged-in selected player's ready flag changes. All four end Ready, original sides/IDs/leader values unchanged. Unready/ready persists through separate reads. State remains draft; no game starts, XP/rating does not change. |

If My battle plans already contains an unexpected draft before C, stop and report its ID/state instead of replacing it. For the intentional duplicate check, dismiss the expected rejection and inspect the saved plan. On any other unexpected result or timeout/cancelled acknowledgement, stop and report the check letter and actual screen. Reconcile through My battle plans/Refresh plan before any later mutation; never repeat a mutation merely to discover whether it committed.

## 5. F — one full restart with the ready draft intact

After A–E pass and all four are Ready, leave the draft intact and quit the game. Stop bridge, admin service, then MongoDB with Ctrl+C, waiting for each PowerShell prompt. Start MongoDB first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for MongoDB running on 127.0.0.1:27018. Start the admin and bridge in their separate windows using the same commands in step 3, waiting for their database-check/admin URL and bridge READY markers. Keep WAN disconnected and local Ethernet/LDPlayer connected.

Reopen the app; confirm the retained Trusted server and fresh login requirement. Log in each of the four players in turn and inspect the same My battle plans entry -> View fixed lineups. Require the same battle ID, team/player IDs, Isar's Cross 2v2, fixed sides 1/4 vs 2/3, saved Spearman/level 1 snapshots, both Approved and all four Ready, with state still draft. As UniPlayer and UniRecruit also check My team, View personal leader and Application decisions: Koichi retains original captain/2/8 and unchanged XP/rating, old Read approval/rejection history remains for the relevant account, and acknowledged notices do not repeat. The earlier archived ArchiveTest stays absent from active teams. This explicitly tests the final membership/history restart that was not established by the previous A–H report.

## 6. G–H — stale cancellation and leave both teams intact

| Check | Action | Expected result |
| --- | --- | --- |
| G. Stale draft, readiness withdrawal and captain cancellation | As UniRival, leave **RivalPlan only** through Teams -> Leave team -> Leave this team. As UniPlayer, open/refresh the saved plan and View fixed lineups, then Set myself not ready with its confirmation. As UniSolo, open this plan and choose Cancel this battle plan, first default Back without changes; refresh to confirm it is still draft. Then Cancel this battle plan -> Cancel this draft plan. | The saved plan still has the original four-player snapshot, but reads “Team membership changed after this plan was saved.” Approval/new-ready actions are unavailable while stale; the still-selected UniPlayer may withdraw readiness. The current opponent captain can cancel this stale draft; state becomes cancelled and the same ID/lineups remain in history. No game/XP/rating change occurs. Koichi is never left or transferred. |
| H. Restore opponent roster and compare final values | UniRival reapplies to RivalPlan; UniSolo approves. UniRival logs in and acknowledges the fresh approval. Both captains read My team and the cancelled plan history; check each player's View personal leader. | Original Koichi ID/UniPlayer captain/UniRecruit 2/8 unchanged. RivalPlan retains its original ID/UniSolo captain and returns to UniRival 2/8. All four original player IDs and leader XP remain unchanged, both teams level 1/XP 0/rating 1000, cancelled draft retained. No active battle is running. Preserve both teams/accounts for later gameplay work. |

## Return one combined report

Return the bridge/APK/install success markers and version 1192606, actual saved Trusted server display, planning A–H results (including F's full restart), the two team IDs and saved plan ID, and whether WAN stayed disconnected throughout the offline build/install/startup/tests. Include actual names if you used alternatives. No password, private key or runtime file is needed.

On any build/startup failure, send the complete console and its saved diagnostics log and stop before later steps. Saved logs are under server diagnostics/alliance-bridge-{rebuild,build,run}-*.txt and alliance-serve-*.txt; client diagnostics/android-account-{rebuild,build,install}-*.txt. Do not repeat earlier dependency builds, old management A–H or guest gameplay checks. Larger 3v3/4v4 contracts have automated backend/native coverage and pinned-map proof; actual combat, battle start, reconnect/turn synchronization and reward settlement remain later work.
