# Team management update: continue the combined game test

Windows setup is complete at the logged scope: bridge rebuild, preserved1192604 account stages, six native Android steps,33 Gradle --offline tasks, APK/signature checks,1192605 installation and setup activity startup all pass. Fresh admin/database checks and bridge READY100.99.99.14:15001 also pass. The CMake/Java warnings did not prevent successful compilation. No repeated pull, rebuild, installation, dependency change or initial service startup is needed.

Keep MongoDB, the admin service and the bridge running in their three windows; keep LDPlayer open. Disconnect WAN while retaining local Ethernet for the following tests. The completed build/startup WAN status is unreported; include it separately in the final report without rerunning the build solely to establish that fact. The actual saved-profile display and new game actions remain to be checked. Use the existing installed1192605 app.

The user requests one combined batch report, not a pause after each successful action. Preserve existing Koichi and its players; the checklist restores UniPlayer captain/UniRecruit member2/8 before archiving a separate disposable test team. Earlier1192604 Read approval/no-pending/unchanged-player checks are accepted; fresh rejection/Back preservation and full membership/history restart remain part of this batch.

## 1. Combined LDPlayer checklist

On the setup screen, confirm Wesnoth Alliance, Trusted server:100.99.99.14:15001 and Start game. If the saved profile is missing/unusable, stop and report that message without reimporting/resetting. Otherwise choose Start game -> Alliance. Use the existing UniPlayer and UniRecruit accounts. Each selection uses Open; each profile/message uses OK; Back leaves Teams for Alliance. Log out and log in to switch accounts. In approval/rejection, captain-transfer and leave-team selectors, **Back without changes** is now the first/default row. Explicitly select the named action and its final confirmation to perform it. Ordinary Back/Escape or opening the default row must not change anything.

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

## 2. One restart check after A–H pass

After Koichi is restored, quit the game. Stop bridge, admin service, then MongoDB with Ctrl+C, waiting for each PowerShell prompt. In the database window start MongoDB first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for MongoDB running on127.0.0.1:27018. In a separate admin window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for ALLIANCE DATABASE CHECK PASSED and http://127.0.0.1:18765/. In a separate bridge window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Wait for ALLIANCE ACCOUNT BRIDGE READY100.99.99.14:15001. Keep all three windows open. Reopen the game and log in as UniPlayer and UniRecruit in turn. Check the same Koichi ID, UniPlayer captain,2/8 roster, unchanged personal/team values, retained Read approval/rejection history for the relevant account, and no repeated unread prompt for acknowledged notices. The archived ArchiveTest stays absent from active teams. Saved trusted server remains present; game restart requires fresh login.

## Return one result report

Send the result for A–H and restart, confirming the trusted-server display and whether WAN stayed disconnected during these game tests. Also say whether WAN was disconnected during the already-completed build/install/startup. Do not repeat any successful build just to change its WAN evidence. On an unexpected result, stop and report the check letter and actual message; on an uncertain mutation do not repeat it.

Build/install/startup successes have already been returned; their full logs need not be resent unless requested. New failure logs are saved under the existing server/client diagnostics directories. Do not share passwords, keys or private runtime files. No physical phone, new environment inventory or old dependency/gameplay retest is requested. Actual Alliance battle creation, campaign reward and combat integration remain later work.
