# Emerald Court administration — Windows update and acceptance

This is a server-side administration update for installed Android 1192624,
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
