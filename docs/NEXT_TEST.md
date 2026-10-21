# Update Alliance password entry, then make one controlled login

The returned Windows trace identifies password_mismatch/HTTP401 after service authorization and account lookup. The user typed with the Windows keyboard in LDPlayer. The earlier Windows local password check matched. The exact cause of the differing received password is still unproven; do not reset or recreate accounts.

1192607 adds Show password, off by default, and an Alliance credential field that keeps the displayed text and submitted value consistent through edits, Unicode, selection replacement and the128-character limit. It also prevents temporary preedit text from entering the field. Passwords are not trimmed or normalized. This gives a local inspection method and fixes reproduced editing defects without claiming those defects caused this incident.

## 1. Pull the update

Quit the Android game. Keep MongoDB, the existing disarmed trace backend and READY account bridge running; do not start another admin service or rerun the trace. Temporarily connect Windows to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
    }
    'Both updates completed successfully.'
}
```

Expected: both updates succeed. Stop on any local-change or Git error and send it; do not discard files. Disconnect WAN again while leaving local Ethernet connected. No server/bridge rebuild, database initialization or dependency installation is needed.

## 2. Rebuild and install the account-game update offline

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Credential update build failed. Send the saved rebuild and build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Credential update installation failed. Send the saved install log.'
    }
}
```

Expected: original1192606 account engine/APK stages are retained under unique before-credential-input-ui backups. All older journals/backups,all568 original engine objects and completed libraries remain intact; the account relink reuses567 original objects. The targeted build finishes with ANDROID ACCOUNT GAME REBUILD COMPLETE, and installation finishes with ANDROID ACCOUNT GAME INSTALL COMPLETE and Version1192607. No OBB transfer or app-data deletion occurs. Reports are in client diagnostics/android-account-{rebuild,build,install}-*.txt. Stop at the first failure; do not clear locks or rerun initialization.

## 3. Inspect entered text locally and submit once

Confirm Wesnoth Alliance still displays Trusted server100.99.99.14:15001, then Start game -> Alliance -> Log in. If the saved profile is missing or unusable, stop and report the message without reimporting or resetting it.

Enter UniPlayer and the password that matched the earlier Windows local check, using the Windows keyboard. Show password must initially be unchecked and the field masked. Check Show password and compare the displayed text locally with the intended password, including case and symbols. Do not share the visible password or a screenshot containing it. If the text differs, correct it locally and note only whether characters were missing, duplicated or different; do not report the characters themselves. Toggling Show password off and back on should preserve the entered text.

Hide the password, then submit once. Expected: Logged in. If successful, View personal leader and My team must show the existing player ID, Spearman/level1/Experience0/Total experience0 and unchanged Koichi roster (UniPlayer captain, UniRecruit member,2/8). Do not create another player or begin planning tests yet. If it fails, stop further attempts and return the exact error plus whether the revealed text matched the intended password. The old backend capture is already disarmed; another trace is not requested.

Return one combined report: build/install result, retained Trusted server, Show password default/toggle behavior, whether the locally inspected text matched, exact login result and unchanged profile/team values if login succeeds. Include actual WAN status during build/test. Never include passwords, hashes, tokens or private runtime files. The full earlier sanitized trace JSON is optional supporting evidence; its supplied outcome line is already accepted.

## Paused planning acceptance — resume after login recovery

The returned Windows output now confirms all three services ready: MongoDB127.0.0.1:27018, authenticated database/schema/transaction checks and admin127.0.0.1:18765, and bridge100.99.99.14:15001. Keep those three PowerShell windows and LDPlayer open. The earlier1192606 battle-planning build/install remains accepted. Resume this checklist only after the1192607 credential update and successful login above have been confirmed. At that point no additional pull/build/install, database initialization, repeated backend diagnostic or initial service restart is required. The intentional restart occurs only at check F.

This update tests saved battle planning: approved maps, fixed lineups, two captain approvals, player readiness, persistence and cancellation. Combat, battle start and XP/rating rewards are later work. Use one LDPlayer and log out/log in to switch between four players. Keep WAN disconnected and local Ethernet connected; report the actual WAN state with the combined results.

First confirm the app still shows Wesnoth Alliance and Trusted server100.99.99.14:15001, then choose Start game -> Alliance -> Log in. If the saved profile is missing/unusable, stop and report it without reimporting or resetting. Keep Koichi in Yama, ID4cd736d3-dc6c-4c3d-a816-e7682b56db30, captain UniPlayer and member UniRecruit2/8, with team level1/XP0/rating1000 and unchanged leaders. Do not repeat the previous1192605 management A–H tests; this is the new planning checklist.

## A–E — planning in one LDPlayer

Log out and log in to switch players. Registration does not automatically log in: after creating a new player, explicitly Log in using its saved password. Do not send passwords. Select rows with Open, dismiss messages with OK, and use Back to return to the parent menu. All new proposal choices, plan actions and confirmations begin on **Back without changes**. Explicitly select the named action; default Open/Back/Escape must not submit a mutation.

Use existing UniPlayer and UniRecruit for Koichi. Reuse the separate UniSolo account from the accepted archive test if available; it should have no team. Create one additional player, UniRival, with Spearman. Use a new opponent team named RivalPlan in Yama. If those test names already belong to something else, use unused names and record the actual names/IDs. Do not rename, archive or alter an unrelated team. Keep the original Koichi captain and roster throughout these tests.

| Check | Action | Expected result |
| --- | --- | --- |
| A. Prepare four players/two teams | As UniPlayer, compare My team and View personal leader with the accepted baseline. Log in as UniSolo and confirm no team, then create RivalPlan in Yama. Register/log in UniRival, browse Yama/RivalPlan and apply. UniSolo approves through Review applications. UniRival logs in, opens/acknowledges the approval and checks My team. | Koichi remains UniPlayer captain + UniRecruit 2/8. RivalPlan has UniSolo captain + UniRival 2/8 in the same Yama area. Record both team IDs and the four player IDs from their profiles. New leaders are Spearman level 1/Experience 0/Total experience 0; both teams level 1/XP 0/rating 1000. Reuse the existing UniSolo identity rather than recreating it. |
| B. Catalog, size guard and safe choices | UniPlayer -> Teams -> Battle plans -> Propose battle. Inspect Choose battle map: Isar's Cross — 2v2, Hexcake — 3v3 and Mokena Prairie — 4v4 when enabled for Yama. Select Hexcake; then reopen Propose battle and select Mokena Prairie. Finally reopen the map selector and open the default Back without changes. | Two-member Koichi receives “Your team needs at least 3 members for this map.” / “Your team needs at least 4 members for this map.” respectively; no plan is created. The catalog identifies each enabled map and size. Default Back returns without submitting. Do not add six/eight test players for this check. |
| C. Save exact ordered 2v2 lineups | UniPlayer -> Propose battle -> Isar's Cross -> RivalPlan. In Choose lineup — Koichi select UniPlayer first (Side 1), then UniRecruit (Side 4), then Use this lineup. In RivalPlan select UniSolo first (Side 2), UniRival second (Side 3), then Use this lineup. At Confirm battle proposal first open default Back without changes; My battle plans must remain unchanged, with no new draft. Repeat the same selection and explicitly Send battle proposal. Use View fixed lineups, record the battle plan ID, then Refresh plan. | Saved state draft; same teams/map/ordered sides and leader snapshots. Both Captain approval values Waiting and all four Not ready: proposing does not approve automatically. The refresh returns the same ID and details. Return to Battle plans -> Propose battle and submit the same proposal once more; it is rejected because one of these teams already has a planned battle; My battle plans still contains only the original active draft; any existing historical entries remain unchanged. |
| D. Member permissions and early readiness | Switch to UniRecruit -> Teams -> Battle plans. Propose battle must report that only the current captain can propose. Open My battle plans -> this plan -> View fixed lineups. Inspect the action menu. | A current member can read the same plan. Approve this plan and Cancel this battle plan are absent for the member. Set myself ready is absent while both captain approvals are not yet present. No Start action exists. These are UI permission observations; automated backend fixtures cover forged requests. |
| E. Both approvals and four ready flags | UniPlayer opens the plan -> Approve this plan; first leave its confirmation through default Back without changes and reopen/refresh to verify Waiting. Then Approve this plan -> Approve saved map and lineups. UniSolo opens the same plan and explicitly approves it too. Each of UniSolo, UniPlayer, UniRecruit and UniRival then chooses Set myself ready -> Set myself ready in its confirmation. As UniRecruit, choose Set myself not ready -> Set myself not ready, refresh, then set ready again. Finish with View fixed lineups from both captains. | Both Captain approval values Approved only after their separate confirmations; only the logged-in selected player's ready flag changes. All four end Ready, original sides/IDs/leader values unchanged. Unready/ready persists through separate reads. State remains draft; no game starts, XP/rating does not change. |

Before C, inspect My battle plans and note its current entries. If it contains an unexpected draft, stop and report its ID/state instead of replacing it. For the intentional duplicate check, dismiss the expected rejection and inspect the saved plan. On any other unexpected result or timeout/cancelled acknowledgement, stop and report the check letter and actual screen. Reconcile through My battle plans/Refresh plan before any later mutation; never repeat a mutation merely to discover whether it committed.

## F — one full restart with the ready draft intact

After A–E pass and all four are Ready, leave the draft intact and quit the game. Stop bridge, admin service, then MongoDB with Ctrl+C, waiting for each PowerShell prompt. Start MongoDB first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for MongoDB running on127.0.0.1:27018 and leave its window open. In the admin window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for ALLIANCE DATABASE CHECK PASSED and the admin URLhttp://127.0.0.1:18765/. Leave it open. In the bridge window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Wait for ALLIANCE ACCOUNT BRIDGE READY100.99.99.14:15001. Keep all three windows open, WAN disconnected and local Ethernet/LDPlayer connected. Stop on the first error rather than deleting locks or initializing a different runtime.

Reopen the app; confirm the retained Trusted server and fresh login requirement. Log in each of the four players in turn and inspect the same My battle plans entry -> View fixed lineups. Require the same battle ID, team IDs and player names, Isar's Cross 2v2, fixed sides 1/4 vs 2/3, saved Spearman/level 1 snapshots, both Approved and all four Ready, with state still draft. For each player, separately open View personal leader to compare their player ID and unchanged personal XP with A; View fixed lineups does not display player UUIDs. As UniPlayer and UniRecruit also check My team, View personal leader and Application decisions: Koichi retains original captain/2/8 and unchanged XP/rating, old Read approval/rejection history remains for the relevant account, and acknowledged notices do not repeat. The earlier archived ArchiveTest stays absent from active teams. This explicitly tests the final membership/history restart that was not established by the previous A–H report.

## G–H — stale cancellation and leave both teams intact

| Check | Action | Expected result |
| --- | --- | --- |
| G. Stale draft, readiness withdrawal and captain cancellation | As UniRival, leave **RivalPlan only** through Teams -> Leave team -> Leave this team. As UniPlayer, open/refresh the saved plan and View fixed lineups, then Set myself not ready with its confirmation. As UniSolo, open this plan and choose Cancel this battle plan, first default Back without changes; refresh to confirm it is still draft. Then Cancel this battle plan -> Cancel this draft plan. | The saved plan still has the original four-player snapshot, but reads “Team membership changed after this plan was saved.” Approval/new-ready actions are unavailable while stale; the still-selected UniPlayer may withdraw readiness. The current opponent captain can cancel this stale draft; state becomes cancelled and the same ID/lineups remain in history. No game/XP/rating change occurs. Koichi is never left or transferred. |
| H. Restore opponent roster and compare final values | UniRival reapplies to RivalPlan; UniSolo approves. UniRival logs in and acknowledges the fresh approval. Both captains read My team and the cancelled plan history; check each player's View personal leader. | Original Koichi ID/UniPlayer captain/UniRecruit 2/8 unchanged. RivalPlan retains its original ID/UniSolo captain and returns to UniRival 2/8. All four original player IDs and leader XP remain unchanged, both teams level 1/XP 0/rating 1000, cancelled draft retained. No active battle is running. Preserve both teams/accounts for later gameplay work. |

## Return one combined report

The build/install and initial service readiness are already accepted; no repeat logs are required. Return the actual saved Trusted server display, planning A–H results (including F's full restart), the two team IDs and saved plan ID, and whether WAN stayed disconnected throughout these tests. State the earlier build/startup WAN status if known; it remains unreported. Include actual names if you used alternatives. No password, private key or runtime file is needed.

On any build/startup failure, send the complete console and its saved diagnostics log and stop before later steps. Saved logs are under server diagnostics/alliance-bridge-{rebuild,build,run}-*.txt and alliance-serve-*.txt; client diagnostics/android-account-{rebuild,build,install}-*.txt. Do not repeat earlier dependency builds, old management A–H or guest gameplay checks. Larger 3v3/4v4 contracts have automated backend/native coverage and pinned-map proof; actual combat, battle start, reconnect/turn synchronization and reward settlement remain later work.
