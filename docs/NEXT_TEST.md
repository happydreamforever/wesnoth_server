# Next Windows test: start the updated membership services

The membership bridge rebuild is accepted: both native steps and all artifact/build/rebuild markers pass. The previous bridge was preserved. The user confirms WAN disconnected with local Ethernet retained during the build. The existing Koichi team and its earlier offline restart acceptance remain valid.

**Immediate action: phase 2 below.** Keep WAN disconnected, Ethernet connected and the existing MongoDB window running. No pull, repeat build, database initialization, profile import or OBB copy is needed. Start a fresh admin process to load the new routes, then the updated bridge. If an old admin process is still open, stop it with Ctrl+C and wait for its prompt before launching the new one. Do not start duplicate processes.

Use one phase at a time and return its result before proceeding. APK1192603 adds My applications, application/withdrawal and captain review/approve/reject; its Windows build/install and LDPlayer interaction remain pending. Approval should add a second member without changing XP. Battles, campaign rewards, leaving and captain transfer follow later. Later phases are retained below for continuity.

## Phase 2 — start the updated services after build acceptance

The MongoDB window should still be running on 127.0.0.1:27018. Start a fresh admin process so the new Python routes load:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expect database checks to pass and `Alliance admin: http://127.0.0.1:18765/`. Keep this window open. In another PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expect `ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service`. Keep all three windows open and return readiness output. Do not start a second copy of an already running service. If the database window was closed, use its existing Run-WindowsAllianceDatabase.ps1 launcher with the same RuntimeRoot first; do not initialize it again.

## Phase 3 — build the membership APK after service acceptance

Keep WAN disconnected and the local network connected:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Membership APK build failed. Send the saved rebuild and build logs.'
    }
}
```

This verifies the completed 1192602 account stages, preserves them in uniquely named before-membership-ui directories and builds 1192603 using the original engine objects, native prefixes and cached Gradle inputs. Previous before-team-ui backups and the 1192602 update journal remain intact. The new update journal supports the same-input resume only; do not delete locks/journals or rename stages manually.

Expected: `ANDROID ACCOUNT UPDATE PREPARED`, `ANDROID ACCOUNT GAME BUILD PASS` and `ANDROID ACCOUNT GAME REBUILD COMPLETE`. Return `diagnostics\android-account-rebuild-*.txt` and `android-account-build-*.txt` on failure, or the successful console summary. This build does not install the app.

## Phase 4 — update the existing installed app

Keep the game closed and LDPlayer running. After build acceptance:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile

    if ($LASTEXITCODE -ne 0) {
        throw 'Membership APK installation failed. Send the saved install log.'
    }
}
```

Expect `ANDROID ACCOUNT GAME INSTALL COMPLETE`, version 1192603, and the existing `Trusted server: 100.99.99.14:15001` with Start game. The helper accepts an installed 1192602 or 1192603, preserves app data/profile and does not transfer the OBB. If the profile is missing or unusable, stop and report the message; do not reset or reimport. Return the saved `diagnostics\android-account-install-*.txt` summary and visible setup result.

## Phase 5 — manual membership acceptance in the same LDPlayer

These checks will be handed off one at a time after installation. Keep WAN disconnected and Ethernet connected. Use the same LDPlayer by signing out and switching player accounts; another emulator is unnecessary for membership testing.

1. Start game -> Alliance -> Log in as existing UniPlayer. Teams -> My team must retain Koichi/Yama and its captain/values. Teams now includes My applications and Review applications. An empty application list is expected initially.
2. Log out with the server-revoked acknowledgement. Create one separate player, for example UniRecruit if available, with a private password and Spearman. Log in. Do not share the password and do not create another team.
3. Teams -> Browse areas and teams -> Yama -> Koichi. Open the team action list, choose Apply to join, review the selected team, then Send application. After OK, the refreshed My applications list must include Koichi. My team must still report no team; application alone does not grant membership.
4. My applications -> Koichi -> Withdraw application -> confirm. Koichi should disappear from that pending list and My team should still be empty. Apply again through Yama/Koichi.
5. Log out and log in as UniPlayer. Teams -> Review applications should show the second player. Reject that player using the confirmation dialog; the application should disappear and Koichi should remain 1/8.
6. Log in as the second player, verify no pending Koichi request and apply again. Return to UniPlayer -> Review applications and approve the intended player explicitly. My team must now show 2/8, with UniPlayer as the sole captain and the new player in the roster. Team level/XP/rating remain 1/0/1000.
7. Log in as the second player. My team must show the same Koichi ID, Yama and two-member roster, while My applications no longer includes the approved Koichi request. View personal leader must remain Spearman level 1, experience 0, total experience 0. Check UniPlayer's personal values are unchanged too.
8. After these observations pass, perform a controlled game/bridge/admin/database stop and restart against the same runtime. Fresh logins must retrieve the same roster and values. Record WAN status for this new test separately from earlier acceptance.

Report the actual dialogs and roster values after each handed-off step. Compare IDs on screen; earlier pasted player/area IDs contained transcription ambiguities. If a mutation reports an uncertain result, use My applications, My team or Review applications to read the saved state before taking another action. Never repeatedly tap approve/apply to compensate for a timeout.

VPS validation covers these protocol/database paths; actual Windows builds and LDPlayer interaction remain pending until returned evidence. Two-human battle synchronization, campaign progression, leave/captain transfer and match rewards remain later milestones.
