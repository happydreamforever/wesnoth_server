# Next test: local account-service health

The corrected Windows bridge rebuild passed, including preservation of the old build. Startup now reaches `stage=backend-health`: certificate validation and TLS key matching have completed, but the local account service has not passed its check. The generic stage does not distinguish a missing listener, timeout, rejected authentication or a database/response error.

**Current step: collect the local service result.** Keep the existing MongoDB and admin-service windows open. Preserve the newly built bridge and its backup. No native/Android rebuild, database initialization, identity change or service restart is requested.

## 1. Update only the server diagnostic while connected to GitHub

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $bash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull failed. Stop and send the output.' }
}
```

The client receives mirrored project records only; its application is unchanged. Disconnect WAN after this pull while retaining Ethernet.

## 2. Run one read-only backend diagnostic

In an ordinary PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsAllianceBackend.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
    if ($LASTEXITCODE -ne 0) {
        throw 'Backend check reported a failure. Send the saved text and JSON reports.'
    }
}
```

Expected: current listener metadata for TCP18765 and27018, followed by a safe health-check result. A healthy response prints `outcome=healthy; http_status=200`, all four checks `True`, and `ALLIANCE BACKEND CHECK PASSED`. A failed result should distinguish the HTTP status or connection/timeout/configuration problem. This is a diagnostic result, not account login or Android connectivity acceptance.

Send the complete console output and printed diagnostics/alliance-backend-*.txt and*.json reports, including a failure result. Confirm whether WAN was disconnected during the diagnostic. The helper reads the existing bridge credential locally but never prints it. Do not send config.json, credentials.json, .env, private keys or passwords.

**Stop after this check.** The remaining sections describe later steps after the backend check and actual bridge READY marker pass.

## 3. Build the account-enabled Android game

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

## 4. Update the app and import the public server profile

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

## 5. Manual account acceptance with WAN disconnected

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
