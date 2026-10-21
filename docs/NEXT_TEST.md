# Next Windows step: start the updated admin service and bridge

The application-decision bridge rebuild passed on Windows, preserving its previous build. The user explicitly confirms WAN was disconnected while local Ethernet stayed connected. Keep those conditions for this phase. No further pull or bridge rebuild is needed.

The next step starts a fresh admin service to load the new routes, followed by the rebuilt bridge. Keep the existing MongoDB window running and the game closed. If the old admin process is still running, press Ctrl+C in its own window and wait for its prompt before starting the new one. Do not start a second copy. Use the existing runtime, accounts, team and identity.

Return both startup results before the later Android build/install phases below. APK1192604 adds private approval/rejection notices, login/My applications unread checks and retained Application decisions history. Notification acceptance still requires the Android update and a new captain decision: earlier1192603 rejections were not saved and cannot be reconstructed.

## Current phase: load the new backend and bridge

Keep the existing database window running. In the stopped admin window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected: ALLIANCE DATABASE CHECK PASSED and Alliance admin: http://127.0.0.1:18765/. Keep that window open. In the stopped bridge window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expected: ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001. Keep all three windows open. Return readiness output; failures save diagnostics/alliance-serve-*.txt or alliance-bridge-run-*.txt. Do not initialize or reset the database.

## Phase 3: build the Android update offline

Use another PowerShell window; keep the game closed and LDPlayer open:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send the saved rebuild and build logs.' }
}
```

Expected: existing 1192603 account engine/APK stages are preserved under unique before-decisions-ui paths, then ANDROID ACCOUNT UPDATE PREPARED, ANDROID ACCOUNT GAME BUILD PASS and ANDROID ACCOUNT GAME REBUILD COMPLETE. Earlier stages/backups and cached dependencies remain. Return the result; logs are client diagnostics/android-account-rebuild-*.txt and android-account-build-*.txt. Do not rename stages manually or rerun earlier dependency builds.

## Phase 4: install while retaining the trusted server

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Android update installation failed. Send the saved install log.' }
}
```

Expected: verified version 1192604, ANDROID ACCOUNT GAME INSTALL COMPLETE, and LDPlayer shows Wesnoth Alliance / Trusted server: 100.99.99.14:15001 / Start game. The helper preserves app data and does not reimport the profile or copy an OBB. If the saved profile is missing/unusable, stop and report the message without resetting/reimporting. Return diagnostics/android-account-install-*.txt if installation fails.

## Phase 5: new rejection, unread notice and retained history

Keep WAN disconnected and local Ethernet connected throughout. Use the same LDPlayer and existing accounts; never send passwords.

1. Start game -> Alliance -> Log in as UniRecruit. Dismiss the profile. Under Teams, open My applications and confirm Koichi — 1/8 members. If no request is pending, inspect My team first; only if no team is present, submit one application through Browse areas and teams -> Yama -> Koichi -> Apply to join -> Send application -> Open. Confirm the refreshed pending entry. If UniRecruit already belongs to a team, stop and report instead.
2. Log out; log in as captain UniPlayer. Teams -> Review applications -> UniRecruit -> Open. Select **Reject application**, then confirm Reject this application for Koichi. Approval is a separate option: do not choose it in this rejection test. Expect Application rejected and the refreshed empty captain queue. My team remains 1/8 with the same captain/level/XP/rating. Stop and report this phase before switching back.
3. Log out; log in as UniRecruit. Dismiss Logged in. Expect **Unread application decisions** with **Unread — Rejected — Koichi** and a UTC time. Choose **Back** without opening the notice.
4. Teams -> My applications must offer the same unread notice again. Select it -> Open. Expect **Application rejected** and **The captain rejected your application to join Koichi**. Choose OK. This acknowledges only that decision, then My applications reports no pending requests. My team still reports no team.
5. Teams -> Application decisions now shows **Read — Rejected — Koichi**. Open it to confirm the saved result, then choose Back from the history and Teams menus. Logging out/in must not offer that read notice as unread; Application decisions must still retain it. Do not create repeated applications just to test notification count.

Report the login notice, Back/unread behavior, detail, retained Read status, no-membership state and whether WAN remained disconnected. A list/read failure is not proof of a lost decision. If acknowledgement is unconfirmed, reopen Application decisions to inspect the saved status before repeating anything.

## Next acceptance after the rejection notice

A later bounded handoff will reapply as UniRecruit and approve as UniPlayer, then verify the approval notice, matching2/8 roster on both accounts, unchanged personal/team XP and full-service restart persistence. No battle or campaign reward has been implemented by this update. Team leave/captain transfer UI, campaign progression and Alliance Battle follow the implementation checklist.
