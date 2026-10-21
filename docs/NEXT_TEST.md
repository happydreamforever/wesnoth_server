# Team management update: one combined offline test

This release adds captain transfer, team departure, explicit last-member archival, top-20 area rankings and safe default choices for captain decisions. APK version is 1192605. The existing database/schema, game data/OBB, account identities, saved server profile and native dependency stages are retained. The user now requests larger coherent deliveries: perform this combined checklist and report the results together, stopping early only on a failure or uncertain mutation outcome. Earlier instructions to report after every small successful action are superseded for this batch.

The user confirms the preceding checks: approval history says Read, My applications is empty, and UniRecruit remains the same player/Spearman/level 1 with both experience values zero. The earlier approval notice and matching 2/8 roster were explicitly confirmed with WAN disconnected. Full restart history/membership and a fresh rejection notice are included below; they are not already accepted.

## 1. Pull once while temporarily connected

Quit the Android game. Stop the account bridge and admin service using Ctrl+C in their own windows and wait for each PowerShell prompt. Keep the MongoDB window and LDPlayer running. In another PowerShell window:

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

Disconnect WAN while keeping local Ethernet connected. Keep it disconnected throughout the build and all tests. No new package download is required.

## 2. Build both changed components and update the existing app

The helpers preserve the completed bridge and both 1192604 account stages. The Android update uses a new 1192605 journal and before-management-ui backup names, retaining all older journals/backups. Do not manually rename/delete build stages.

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

Expected markers: ALLIANCE ACCOUNT BRIDGE REBUILD PASSED, ANDROID ACCOUNT UPDATE PREPARED, ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE and installed version 1192605. The existing Trusted server 100.99.99.14:15001 must remain displayed. If missing/unusable, stop without reimporting/resetting. No OBB transfer or database initialization is needed.

## 3. Start fresh admin and bridge processes

In the admin PowerShell window, with the existing MongoDB still running:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for ALLIANCE DATABASE CHECK PASSED and http://127.0.0.1:18765/. Keep the window open. Then in the bridge PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expect ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001. Keep all three service windows open.

## 4. Combined LDPlayer checklist

Choose Start game -> Alliance. Use the existing UniPlayer and UniRecruit accounts. Each selection uses Open; each profile/message uses OK; Back leaves Teams for Alliance. Log out and log in to switch accounts. In approval/rejection, captain-transfer and leave-team selectors, **Back without changes** is now the first/default row. Explicitly select the named action and its final confirmation to perform it. Ordinary Back/Escape or opening the default row must not change anything.

| Check | Action | Expected result |
| --- | --- | --- |
| A. Rankings and baseline | Log in UniPlayer. Teams -> Area rankings -> Yama -> Koichi. Then Back to Teams -> My team. | Rating 1000, team level 1, 2/8; same Koichi ID and UniPlayer captain/UniRecruit roster. Rankings contain at most 20 teams, highest rating first; equal ratings use team ID ordering. |
| B. Captain protection and cancel | As UniPlayer, choose Leave team. Then Transfer captain, leaving the default Back without changes selected and choosing Open. Reopen My team. | Leave is blocked until captain transfer; cancelled transfer changes nothing. Captain remains UniPlayer, 2/8. |
| C. Captain transfer | UniPlayer -> Transfer captain -> explicitly select UniRecruit -> Open -> Transfer captain to UniRecruit -> Open. | Confirmation then fresh My team shows UniRecruit (captain), UniPlayer member, 2/8. Personal/team XP unchanged. |
| D. Permissions and departure | Still UniPlayer, Review applications must deny captain access. Leave team -> Leave this team -> Open. | Successful departure; My team reports no team. Koichi remains active with UniRecruit captain and 1/8. |
| E. New rejection and unread preservation | UniPlayer browses Yama/Koichi and applies. Switch to UniRecruit, Review applications -> UniPlayer -> Reject application -> Reject this application. Switch back to UniPlayer; dismiss login profile. At Unread — Rejected — Koichi choose Back without opening. Teams -> My applications must offer that notice again. Open it, verify rejection, choose OK. | Fresh rejection notice survives Back and is offered again. Application decisions then shows Read — Rejected — Koichi; My applications empty; UniPlayer still has no team. Older decision history is retained. |
| F. Rejoin and restore captain | UniPlayer applies to Koichi again. UniRecruit approves that request using the explicit Approve application / Approve this player choices. UniRecruit -> Transfer captain -> UniPlayer -> Transfer captain to UniPlayer. | Koichi returns to the original captain UniPlayer and members 2/8. UniPlayer receives a new Approved notice on next login; open/OK it and verify Read history. |
| G. Progression unchanged | View My team and View personal leader from both existing accounts. | Same account/team IDs, Spearman level 1 and personal Experience 0 / Total experience 0. Team level 1/XP 0/rating 1000, original captain and 2/8 roster. |
| H. Last-member archival | Log out of the current player. Choose Create player account, register one separate test player UniSolo (do not share its password), and choose Spearman. Registration does not log in automatically: Log in as UniSolo, then Teams -> Create team to create a separate team ArchiveTest in Yama. My team must show only UniSolo 1/8. Choose Leave team; read the archive warning; explicitly select Leave and archive this team -> Open. | That test team is archived, no longer in active directory/rankings, and UniSolo has no team. UniSolo's leader remains level 1/XP 0. Koichi is unchanged. If these names already exist, use unused test names instead of altering an existing team. |

On any unexpected result or uncertain timeout/cancellation, stop and report the check letter and current screen. Do not repeat a mutation to refresh its outcome. My team and decision history are the read-only reconciliation views. The server rejects stale leave requests that would archive a team unless the client explicitly confirmed the archive consequence. It also rejects stale/unauthorized transfer and active-game changes.

## 5. One restart check for the whole batch

After A–H pass and Koichi is restored, quit the game. Stop bridge, admin service, then MongoDB with Ctrl+C, waiting for each prompt. Start MongoDB first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for MongoDB running on127.0.0.1:27018, then use the same admin and bridge commands from step3 in their separate windows. Reopen the game and log in as UniPlayer and UniRecruit in turn. Check the same Koichi ID, UniPlayer captain, 2/8 roster, unchanged personal/team values, retained Read approval/rejection history for the relevant account, and no repeated unread prompt for acknowledged notices. The archived ArchiveTest must stay absent from the active directory. Saved trusted server must remain present; game restart requires a fresh login.

## Return one result report

Send build/install success markers and the result for A–H plus restart, including whether WAN stayed disconnected throughout. Report any differing text instead of passwords, private keys or runtime files. On a build/startup failure send the complete console plus its named diagnostics log; do not continue to later steps.

Saved logs are under server diagnostics/alliance-bridge-{rebuild,build,run}-*.txt and alliance-serve-*.txt; client diagnostics/android-account-{rebuild,build,install}-*.txt. No physical phone, new environment inventory or old dependency/gameplay retest is requested. Battle creation, campaign rewards and actual Alliance combat integration remain later work.
