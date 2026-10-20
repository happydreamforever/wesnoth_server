# Next test: install the account-enabled Android game

The Windows account listener reports READY on `100.99.99.14:15001`. The returned Android account build log now passes all six native steps, 33 Gradle tasks and final artifact checks. The user confirms internet was available during this build; Gradle used `--offline`, but a WAN-disconnected build is not established. The next visible game milestone is the setup screen for this completed APK. Team gameplay and custom campaign rewards remain later work.

**Current step: install the completed Android update and confirm its setup screen.** Use the previously delivered installer; no pull or rebuild is needed. Keep the running database/admin/bridge, their credentials/identity, all completed game stages and OBB. Stop after this step and return its result before continuing to profile import or account testing.

## 1. Install the completed APK in LDPlayer

Keep local Ethernet connected and internet/WAN disconnected. Leave LDPlayer and the database, admin-service and account-bridge windows open. In a **new PowerShell window**, run:

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

The helper verifies the completed APK, its receipt and matching signer before Android changes, updates the existing installation using `adb install -r`, and transfers only a validated public profile to a unique file in LDPlayer's Downloads folder. The package remains `org.wesnoth.offline`, now versionCode `1192601`, with x86_64/minAPI23. It performs no uninstall, app-data reset or OBB transfer. Existing saved games remain in the same app storage. Verification may take a few minutes; let it finish.

Expected console marker: `ANDROID ACCOUNT GAME INSTALL COMPLETE`. The log is `wesnoth_client\diagnostics\android-account-install-*.txt`. This marker confirms the update and a fresh setup-activity marker; it does not confirm account registration or login.

Expected LDPlayer screen: **Wesnoth Alliance**, with **Import server profile** and **Start game**.

**Stop here and send the saved `android-account-install-*.txt` log**, including any error, and confirm which screen appears in LDPlayer. Report whether WAN was disconnected during installation. The helper also prints later import instructions; wait for setup acceptance before following them. Installation alone does not test LAN account reachability.

## 2. Import the public profile after installation is accepted

Use the address, fingerprint and Downloads filename from the successful install log:

1. Choose **Import server profile**.
2. In the Android file picker, open **Downloads** and select the `wesnoth-alliance-public-profile-<id>.json` filename printed by the install helper.
3. Compare the displayed address and certificate SHA-256 with the `Server:` and `Certificate SHA-256:` lines printed by that helper. The expected existing endpoint is `100.99.99.14:15001`.
4. If they match, choose **Trust server**. The setup screen should display the saved trusted server.
5. Choose **Start game**. Existing game data is checked and reused. At the main menu, the former Add-ons entry is now **Alliance**.

Confirm that profile import succeeds and the Alliance menu appears. If connection later fails, return the displayed error and account-listener log; the old guest connection on 15000 does not establish reachability on 15001.

## 3. Manual account acceptance with WAN disconnected

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
