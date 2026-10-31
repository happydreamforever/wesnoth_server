**Current Windows step (2026-10-31): AD1 administrator access.** Five-service startup passed: W02–W05 reused healthy services, W06 started the native Room server and W07 declared readiness. The original W05 timeout is retained as history; its cause is not established. Keep all five service windows and the existing LDPlayer open. No additional pull, rebuild or restart is needed.

Perform these checks in order on the Windows host:

| Check | Action | Expected result |
|---|---|---|
| AD1a | Open `http://127.0.0.1:18765/` and sign in with the existing website administrator account. | Emerald Court administration appears with the operator name and **Administrator** badge. Use the website administrator, not a MongoDB or game-player credential. |
| AD1b | Inspect the sidebar. | **Overview, Users, Rooms, Teams, Team battles, Companies, Campaigns, World, Engagements, Game runs, Operations, Areas, Audit log** appear. |
| AD1c | In a fresh private/incognito window, open `http://127.0.0.1:18765/accounts`. After the Login redirect, attempt one login with an ordinary game-player account and its correct player password. | The protected page requires Login. The player attempt receives **Invalid username or password.** This is expected administrator-role denial; no administrative records appear. |
| AD1d | In the normal administrator window, choose **Sign out** and reopen `http://127.0.0.1:18765/accounts`. | Login is required again. Sign back in with the administrator after confirming this. |

Return AD1a–AD1d PASS/FAIL/NOT RUN and stop at the first unexpected result. Do not send passwords. These checks create/revoke browser sessions and record one failed admin-scope attempt; they do not change player progression. Do not edit accounts, reset passwords, change roles or close Rooms yet. AD2 preservation and AD3 disposable waiting Room closure follow review.

WAN is already confirmed disconnected with local Ethernet retained for this administration batch; no repeat confirmation is required unless it changes. Preserve accepted build/UI/Company results and existing campaign saves.

---

**Historical resume (accepted 2026-10-31): existing services reused and Room server started.** The returned W05 transcript now establishes worker artifact readiness and a listening battle service. The original JSON remains a failed health-check snapshot; untimestamped READY lines do not establish why the earlier timeout occurred. Successful workflow health is still pending.

Keep existing service windows open and retain WAN-disconnected/local-Ethernet operation. Run once:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -IncludeBattles

    if ($LASTEXITCODE -ne 0) {
        throw 'Workflow resume stopped. Send the new workflow text/JSON and current W05 output.'
    }
}
```

Expect `W02 PASS existing database`, `W03 PASS existing backend`, `W04 PASS existing bridge`, `W05 PASS existing battles`, then W06 START/PASS multiplayer and `W07 UNIFIED GAME SERVICES READY`. The helper validates running services before reuse; an occupied unhealthy listener stops the workflow without starting a duplicate.

Return the new complete console and `diagnostics/alliance-workflow-*.txt/.json`. If anything fails, stop and return the exact new error plus current W05 output; do not retry again or close healthy service windows. Preserve the original failed report. No pull, rebuild, timeout change, lock removal or initialization is needed. Administrator-role checks remain next after successful startup review. WAN status is already recorded once for this batch.

---

**Historical diagnostic (reviewed 2026-10-31): existing W05 reports.** The supplied workflow passes W02 database, W03 backend and W04 bridge, then stops at `W05_startup_unconfirmed`. W06/W07 were not reached. W05 readiness was not established within its five-minute window; the cause is not shown in the console. Keep all currently open service windows open, including W05. Do not retry startup or run another build yet.

Run this read-only command and return both sections:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $reportStem = 'D:\Test\wesnoth-setup\wesnoth_server\diagnostics\alliance-workflow-20261031-042622-727-095df455a11b43fca6a2797378eeb145'

    Write-Host 'BATTLE SERVICE LOG (W05)'
    Get-Content -LiteralPath ($reportStem + '-W05.txt') -Raw -Encoding UTF8

    Write-Host 'WORKFLOW JSON'
    Get-Content -LiteralPath ($reportStem + '.json') -Raw -Encoding UTF8
}
```

This reads existing diagnostics only; it does not start, stop or change a service. If a file cannot be read, return the error and the current visible battle-service output. Do not recreate files or remove locks. Preserve the main workflow text log with the same stem too. Do not send private runtime configuration or credentials.

After reviewing W05 output and JSON, reproduce/fix the identified failure and retest only that step and affected regressions. Keep the accepted Git/Room build and earlier UI/Company results. WAN-disconnected/local-Ethernet status remains recorded for this batch; no repeat confirmation is required. Administrator checks remain pending until service startup is resolved.

---

**Historical startup attempt (stopped at W05 on 2026-10-31):** The supplied native Room build passed all 47 steps and final artifact verification; the previous build was retained. Git checks and the build are accepted. No additional pull or rebuild is needed.

With WAN disconnected and local Ethernet retained, run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -IncludeBattles

    if ($LASTEXITCODE -ne 0) {
        throw 'Startup stopped. Send the workflow text/JSON and failing service log.'
    }
}
```

Expect W02–W06 PASS for the database, backend, account bridge, shared battle service and native Room server, followed by `W07 UNIFIED GAME SERVICES READY`. Keep all five service windows open. Return the complete console plus the saved `wesnoth_server\diagnostics\alliance-workflow-*.txt` and `.json`; if startup stops, include the failing service's W02–W06 transcript and leave unrelated running services open.

Startup health does not establish admin authorization or Room closure. Review this result before AD1a–AD1d below; AD2/AD3 follow separately. The user confirms WAN was disconnected and local Ethernet stayed connected during the accepted Room-server build. This once-per-batch status is now recorded; retain that condition, with no repeat confirmation needed unless it changes. Do not repeat accepted Android, Company or build checks, initialize a database, or change credentials.

---

**Historical prerequisite (accepted 2026-10-31): preserving native Room build.** Git review passed: server HEAD is `81b73583d04a23cd7fd53a284dbaf833ecc5172a`, full fsck exits zero without errors, only the existing README edit is unstaged, and no changes are staged. All five services are reported stopped. The checkout already contains the admin update; no further pull or Git repair is needed.

Keep all five services stopped. Disconnect WAN while retaining local Ethernet, then run only:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild

    if ($LASTEXITCODE -ne 0) {
        throw 'Room server build stopped. Preserve all files and send the saved build log.'
    }
}
```

Expect `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` and `UNIFIED MULTIPLAYER BUILD PASSED`. Return the complete console and saved `wesnoth_server\diagnostics\unified-multiplayer-build-*.txt`, plus WAN/Ethernet status once for this administration batch. Stop at the first unexpected result and retain all files. No Android, bridge or full-worker rebuild, dependency setup, database migration or initialization is required.

After the successful build is reviewed, restore all five services with `Start-WindowsAllianceStack.ps1 -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles`. Startup and AD1a–AD1d follow; do not run those later checks yet. Earlier two-window restart instructions apply only when the other three services are still running.

---

**Historical prerequisite (accepted 2026-10-31): read-only Git integrity check.** The server pull reached `81b73583d04a23cd7fd53a284dbaf833ecc5172a`, but reported an unavailable pack index twice. The user stopped all five services with Ctrl+C. Keep them stopped; do not build or restart yet. No repeat pull or repair is needed for this diagnostic.

Disconnect WAN while retaining Ethernet, then run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $adminBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    $adminGit = 'PATH=/usr/bin:$PATH /usr/bin/git --no-pager --no-optional-locks --no-lazy-fetch -c core.fsmonitor=false -c diff.autoRefreshIndex=false -C /d/Test/wesnoth-setup/wesnoth_server '

    foreach ($adminCheck in @(
        'rev-parse --verify HEAD^{commit}'
        'fsck --full --no-reflogs --no-dangling --no-progress'
        'diff --no-ext-diff --no-textconv --name-status --'
        'diff --cached --no-ext-diff --no-textconv --name-status HEAD --'
    )) {
        Write-Host "CHECK: $adminCheck"
        & $adminBash --noprofile --norc -c ($adminGit + $adminCheck)
        $adminGitExit = $LASTEXITCODE
        Write-Host "EXIT: $adminGitExit"
        if ($adminGitExit -ne 0) {
            throw 'Git check failed. Preserve all files and send the complete output.'
        }
    }
    Write-Host 'READ-ONLY GIT CHECKS COMPLETE. Send this output for review.'
}
```

Send the complete console, including all exit statuses, and WAN/Ethernet status once for this administration batch. A healthy fsck can print nothing between its CHECK and EXIT lines. Expect the existing README edit; preserve and report any additional differences. A zero fsck exit alone does not establish native build or game readiness. Stop at the first nonzero exit; keep every Git pack/index, source file, build stage, runtime and recovery journal intact.

After review, build only the updated native Room server with `Build-WindowsMultiplayer.ps1 -PreservePreviousBuild`. Once that passes, restore all five services with `Start-WindowsAllianceStack.ps1 -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles`. The earlier two-window restart instructions below apply only when the other three services are still running. Review build/startup output before the administrator-role checks. Do not execute these later steps yet.

---

**Historical administrator-role handoff (superseded by current AD1 above):** Android1192625 UI1–UI6 are accepted by user report. The backend/native Room administration update has not yet been confirmed on Windows. Start with these existing-browser checks before deciding whether a server update is needed; keep existing services running. Do not repeat the Android update.

| Check | Action | Expected result |
|---|---|---|
| AD1a | On the Windows host open `http://127.0.0.1:18765/`. Sign in with the existing website administrator account. | The operator name and **Administrator** badge appear. Login does not use a game-player or MongoDB account. |
| AD1b | Inspect the navigation. | **Overview, Users, Rooms, Teams, Team battles, Companies, Campaigns, World, Engagements, Game runs, Operations, Areas, Audit log** appear. If the old menu appears, stop and report it before using the update instructions below. |
| AD1c | In a fresh private/incognito window without an administrator session, open `http://127.0.0.1:18765/accounts`. Then attempt one login using a known game-player username and its correct player password. | The protected page first redirects to Login; the player attempt shows **Invalid username or password.** No administrative records are displayed. This is expected role denial, not evidence that the player's game password is wrong. |
| AD1d | In the normal administrator window choose **Sign out**, then open `/accounts` again. | Login is required. Sign in again with the administrator to continue later checks. |

Return AD1a–AD1d PASS/FAIL and WAN/Ethernet status once for this administration batch. Stop at the first unexpected result. Do not send passwords or connection strings. These checks affect browser sessions and the single failed admin-scope attempt counter, not player progression. Do not edit roles, reset passwords or create records for this batch.

The new sidebar confirms only the backend UI. Before AD3, establish that the native Room update was built and started and that its live inventory is available. If update evidence is missing, review it or perform the server-only update below; do not repeat a confirmed build. AD2 and later management checks remain pending.

---

# Emerald Court administration — Windows update and acceptance

This is a server-side administration update compatible with Android 1192624 and
the presentation-only Android1192625 update,
protocol 4 and schema 4. The server update must contain implementation commit
`147118122340ca169eca44004e081eb5bd86fa19` (and its parent `a7f8267`). Continue using the existing `runtime-v2`. No database
migration, initialization, Python installation, Android update, account bridge
rebuild or full World worker rebuild is required.

## Management coverage

| Page | Available management |
|---|---|
| Overview | Current counts, recent games and navigation to each game system. |
| Users | Search/pagination, create an ordinary player, rename, suspend/reactivate, password reset, hero XP correction and end sessions. Creation grants no heroes or soldiers. |
| Rooms | Actual native waiting/full/ready/playing Rooms, maps, seats, readiness, economy and rules. Request closure of a selected Room; observe pending, changed or acknowledged closure. |
| Teams | Roster and applications, rename, appoint a current active member as captain, remove a noncaptain, change administrative Area and inspect battles. |
| Team battles / Game runs | Plans, Open/Reserved/Computer/Closed slots, participants, rules, readiness, captain approvals and recorded human results. Cancel an unresolved run; retain the existing evidence-gated ordinary Team result resolution. |
| Companies | Every player's earned heroes, forms, XP, soldiers, wounds, selected force and commitments. Rest eligible ordinary wounds without bypassing territorial recovery or frozen deployments. |
| Campaigns | Story runs and recent scenario checkpoints. Cancel an abandoned server run without deleting local saves or undoing completed rewards. |
| World | Existing explicit founding-Team enrollment and host round controls, Castle ownership/routes, wars, defenses and developments. Withdraw defense permission immediately when unlocked, or after the committed engagement finishes. |
| Engagements / World history | Company, skirmish and territorial contracts, forces and settings; cancel one unresolved engagement through its existing release path. Inspect settlement rewards, soldier advancement, wounds and replay evidence digests. |
| Operations | Recorded engagement queue and player reservations. It does not pretend a stored record proves that a native worker is currently alive. |
| Audit log | Searchable, paginated administrator, action, target, reason and timestamp records. |

Administrative corrections use existing game lifecycles. The console does not
grant invented campaign discoveries, rewrite a completed result, impersonate a
captain's approval, change a frozen force or transfer Castles without combat.
Replay evidence is inspectable here; playback remains in the game. Room creation
and rule selection remain in the native Room interface.

All pages require an active administrator on Windows loopback. POSTs retain
CSRF protection, bounded forms and audit reasons. New destructive forms require
explicit confirmation and current record versions. No password hashes, account
session tokens, worker tickets or private configuration are displayed.

## Live Room behavior

The native Room server publishes a complete bounded inventory every ten seconds.
Use the visible **Refresh** control to update the admin page; forms are not
automatically replaced while an operator is editing them. A report older than
35 seconds is marked unavailable, not presented as current live status.

Closing a Room is a request to its current native-server generation. A change
to its rules, participants, readiness or state invalidates the old request.
The server closes only the matching Room through its normal removal path, which
releases that Room's reservations and returns players to the lobby. The console
reports closure only after the server publishes its disappearance. Request and
acknowledgement have separate audit records. Other Rooms and permanent XP remain
unchanged. Recent closed Rooms are bounded to 100 within the current native
instance; durable moderation history remains in Audit log.

## Windows update

Wait for active battles to finish. Save/leave any game, then Quit the Android game. In the existing **admin service**
and **native multiplayer/Room** PowerShell windows, press Ctrl+C and wait for
their prompts. MongoDB, account bridge and shared battle service can stay open.
Do not stop a running territorial engagement for this update.

While internet is available, update only the server repository:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $adminBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $adminBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server update stopped. Send the output.' }
    & $adminBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check stopped.' }
    & $adminBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server merge-base --is-ancestor 147118122340ca169eca44004e081eb5bd86fa19 HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'The admin update is missing. Stop and send this output.' }
}
```

Disconnect WAN again while retaining local Ethernet. Rebuild only the native Room
server, retaining its previous completed stage:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) {
        throw 'Room server build stopped. Retain all files and send the saved build log.'
    }
}
```

Expect `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` and
`UNIFIED MULTIPLAYER BUILD PASSED`. Keep
`wesnoth_server\diagnostics\unified-multiplayer-build-*.txt`.

Start the admin service in its own window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2')
```

Expect `ALLIANCE DATABASE CHECK PASSED` and the admin URL. Leave the window open.
Start the updated Room server in its own window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsMultiplayer.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expect `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` and
`Starting authenticated multiplayer at 100.99.99.14:15000.` for the existing
identity. Leave this window open. A prior native inventory can take up to 35
seconds to expire before the new process takes ownership; use Refresh afterward.

## Acceptance, one batch at a time

Record WAN/Ethernet status once for this administration batch. Stop at the first
unexpected result. Send the step, expected/actual result and relevant saved log;
never send passwords, connection strings, private configuration or runtime files.

1. **AD1 — Existing login and overview.** Open `http://127.0.0.1:18765/`, refresh
   the page and sign in with the existing website administrator. Confirm the
   Emerald Court interface and the navigation items in the table above.
2. **AD2 — Read-only inspection.** Open Users, your existing account, Companies,
   Teams, Team battles, Campaigns, World, Engagements and Operations. Verify
   actual usernames, hero/form/XP values, Company roster and saves are unchanged.
   Empty World/history data remains empty; do not initialize World for this UI
   check. Search for a username and clear the filter.
3. **AD3 — Ordinary Room closure.** In LDPlayer log into the existing player,
   create a disposable individual Room and leave it waiting. After ten seconds
   Refresh Rooms in the browser. Check its name, map, seats, readiness, gold,
   income and turn limit. Open it, enter an audit reason, tick confirmation and
   request Close Room. Observe pending and then closed after native
   acknowledgement. LDPlayer returns to the lobby. Check Audit log for the
   request and acknowledgement. No permanent XP should change.

Return **AD1–AD3 PASS/FAIL/NOT RUN** and the saved build output first. Later
administration tests can use explicitly disposable records:

4. **AD4 — Users.** Create a disposable player, inspect its empty collection,
   edit its username, reset its password, end its sessions, suspend and reactivate
   it. Never include passwords in the report. A stale second edit must be rejected.
5. **AD5 — Team governance.** On a disposable idle Team, rename, change captain
   to a current active member, remove a noncaptain and move administrative Area.
   Each change needs a reason and confirmation; prepared battles or territorial
   commitments must block unsafe governance changes. Do not mutate accepted Teams
   solely to obtain a test pass.
6. **AD6 — Plans and evidence.** Cancel a disposable unresolved plan and verify
   only its reservations release. Completed results cannot be cancelled. Ordinary
   Team dispute resolution remains unavailable until all required human reports
   exist. Never manufacture a result to exercise the control.
7. **AD7 — Company and territorial recovery.** When normal gameplay has produced
   suitable wounds/defense records, inspect them here. Rest leaves territorial
   wounds and locked units unchanged. Defense withdrawal after commitment stays
   pending until settlement/cancellation. Otherwise mark NOT RUN.
8. **AD8 — Unavailable/stale Rooms.** With no running game, stop only the Room
   server. After 35 seconds Refresh: the console must say unavailable and disable
   closure. Restart it with the command above. Current-generation Rooms reappear
   after the inventory resumes. Previous closure forms cannot act on new Rooms.

Resume the existing World/Company acceptance at **L** after affected admin checks
pass. Previously accepted I1–I3 and K1/K2/J1/J2/K3 remain accepted; numerical hero
baseline and soldier count have not yet been supplied. K4 retirement and J3 World
map checks remain deferred. Preserve existing campaign saves and all prior build,
backup and recovery artifacts.
