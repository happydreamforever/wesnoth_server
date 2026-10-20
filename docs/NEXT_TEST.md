# Next test: Android player account through the Windows server

The new account integration provides a separate native TLS listener and an in-game Alliance menu for registration, login, a personal leader and logout. Existing MongoDB/admin acceptance and the completed standalone Android transport checks remain valid. Windows account-bridge compilation and artifact verification now pass in the returned console. Listener startup and LDPlayer account acceptance remain pending.

The returned build completes section 2. **The current handoff is section 3 only: start the account listener alongside the existing database and admin service, then return the live console output.** No new pull or rebuild is needed. Keep internet/WAN disconnected and local Ethernet connected for this next run. Sections 1–2 below are completed delivery references; sections 4–6 remain later steps. WAN status for the returned build was not reported.

Keep the existing game, native dependency stages, game-data OBB, profile database and administrator data. Use `D:\Test\wesnoth-setup\msys64` and the selected LDPlayer instance `127.0.0.1:5555` (API28/x86_64). This delivery adds no dependency download or MongoDB initialization step.

## 1. Previous delivery reference — do not repeat now

Run in ordinary Windows PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) {
            throw "Pull failed for $name. Stop here and send the output."
        }
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read $name commit. Send the output."
        }
    }
    'Both updates completed successfully.'
}
```

Expected: both fast-forward pulls succeed, followed by their commit IDs and `Both updates completed successfully.` If Git reports local edits, retain them and return the error.

Disconnect internet/WAN now, while keeping local Ethernet and LDPlayer available.

## 2. Windows account listener build — passed

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'

    if ($LASTEXITCODE -ne 0) {
        throw 'Account bridge build failed. Send the saved build log.'
    }
}
```

This builds a small, separate executable at `wesnoth_server\build\alliance-account-bridge\alliance-account-bridge.exe` using the existing MINGW64 tools. It does not rebuild the guest server or any Android dependency.

Expected first-build markers:

```text
ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED
ALLIANCE ACCOUNT BRIDGE BUILD PASSED
Saved log: ...\wesnoth_server\diagnostics\alliance-bridge-build-<timestamp>-<id>.txt
```

An unchanged completed build instead reports `Completed native account bridge reused; no build was run.` and verifies its receipt.

The returned console confirms both success markers and saves diagnostics/alliance-bridge-build-20261020-101034-914-4f9607a9e56445d4a9e8df9db469ca65.txt. No rebuild or duplicate build log is required. This proves the executable builds and verifies, not its listener or Android connection. Proceed to section 3.

## 3. Start the existing backend, then the new listener — current step

Keep the existing MongoDB and administrator-service windows open. If they are already running successfully, leave them running. If they are closed, start them in this order, each in its own PowerShell window.

Database window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected: `Alliance MongoDB running on 127.0.0.1:27018.` Keep the window open.

Administrator-service window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected: `ALLIANCE DATABASE CHECK PASSED` and `Alliance admin: http://127.0.0.1:18765/`. Keep this window open too.

In a third PowerShell window, start the new account listener:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expected:

```text
ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED
ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service
Keep this window open. Ctrl+C stops the bridge.
```

The listener uses the existing identity in `wesnoth_server\runtime\alliance-transport`, validates the local backend and binds the IP address recorded in that identity. It keeps its private key and backend credential on Windows. Its log is `wesnoth_server\diagnostics\alliance-bridge-run-*.txt`; the final saved-log line appears when the launcher exits.

**Stop at the ready marker, keep all running windows open, and send the live console output. Do not stop the listener just to obtain its final saved-log line.** Also report whether WAN was disconnected during this startup; the prior build's WAN status remains unknown.

The guest server on port 15000 is unchanged and is not needed for this account-only test. If the listener fails, return its console output and saved log before proceeding. An address change requires reviewing the existing public identity; do not overwrite it or initialize the database again.

## 4. Build the account-enabled Android game

After the listener starts successfully, use another PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidAccountGame.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Android account game build failed. Send the saved build log.'
    }
}
```

The builder reuses 567 completed engine objects, compiles the account/title-screen changes, and links a new engine in `build\android-account-engine`. It packages an APK in `build\android-account-game`, checks its native payloads and verifies that its signer matches the original game. Gradle runs offline using the existing cache.

Expected first-build markers include:

```text
ANDROID ACCOUNT ENGINE BUILD PASS
ANDROID ACCOUNT GAME BUILD PASS
ANDROID ACCOUNT GAME BUILD COMPLETE: ...\build\android-account-game\receipt.json
Saved log: ...\diagnostics\android-account-build-<timestamp>-<id>.txt
```

The package remains `org.wesnoth.offline`, now versionCode `1192601`, with x86_64/minAPI23. The existing completed engine, original APK and OBB are preserved. Return `android-account-build-*.txt`; a build success is not yet an Android account-runtime pass.

## 5. Update the app and import the public server profile

After the Android build is accepted, leave LDPlayer open and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -Serial '127.0.0.1:5555' `
        -ProfilePath 'D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance-transport\public-profile.json'

    if ($LASTEXITCODE -ne 0) {
        throw 'Android account installation failed. Send the saved install log.'
    }
}
```

The helper verifies the APK before Android changes, updates the existing installation using `adb install -r`, and transfers only a validated public profile to a unique file in LDPlayer's Downloads folder. It performs no uninstall, app-data reset or OBB transfer. Existing saved games remain in the same app storage.

Expected console marker: `ANDROID ACCOUNT GAME INSTALL COMPLETE`. The log is `wesnoth_client\diagnostics\android-account-install-*.txt`. This marker confirms the update and a fresh setup-activity marker; it does not confirm account registration or login.

Expected LDPlayer screen: **Wesnoth Alliance**, with **Import server profile** and **Start game**.

1. Choose **Import server profile**.
2. In the Android file picker, open **Downloads** and select the `wesnoth-alliance-public-profile-<id>.json` filename printed by the install helper.
3. Compare the displayed address and certificate SHA-256 with the `Server:` and `Certificate SHA-256:` lines printed by that helper. The expected existing endpoint is `100.99.99.14:15001`.
4. If they match, choose **Trust server**. The setup screen should display the saved trusted server.
5. Choose **Start game**. Existing game data is checked and reused. At the main menu, the former Add-ons entry is now **Alliance**.

Return the install log and confirm that the setup screen, profile import and Alliance menu appear. If connection later fails, return the displayed error and account-listener log; the old guest connection on 15000 does not establish reachability on 15001.

## 6. Manual account acceptance with WAN disconnected

Keep local Ethernet connected, WAN disconnected, and all three Windows backend windows running.

1. Open **Alliance → Create player account**.
2. Choose **Spearman — Loyalists**.
3. Enter a new player username, for example `UniPlayer`, and your own password of 12–128 characters. Repeat that password when asked. Use a player account separate from the administrator `Uni`. Do not send the password in reports.
4. Expected: account-created confirmation with the chosen personal leader, level **1**, experience **0** and a player ID.
5. Choose **Log in**. One attempt with an intentionally incorrect password should fail without entering the player menu. Then use the correct password.
6. Expected: login confirmation and the same username, player ID and Spearman leader. Open **View personal leader** and check those values.
7. Choose **Log out**. Expected: `Logged out. The server has revoked this session.` The menu should return to **Create player account / Log in**.
8. Log in again and open **View personal leader**. Expected: the same player ID and leader; no duplicate account or new leader is created. Log out to finish.

The server stores the account and personal leader in the existing local MongoDB. This milestone does not yet award campaign experience or implement team battles.

Report the visible results for registration, wrong-password rejection, correct login, personal leader, logout and repeat login, plus whether WAN was disconnected throughout. Send the relevant build/install/listener logs if anything fails. Do not send passwords, session tokens, `.env`, server private keys or private runtime configuration files.
