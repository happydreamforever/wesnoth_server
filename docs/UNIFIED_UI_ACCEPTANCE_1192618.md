# Android 1192618 — startup, keyboard, session and Quit correction

This corrective batch keeps the accepted 1192617 Windows services, runtime-v2 database, trusted profile, players and game data. The change is the Android client. The final offline Android build, artifact/version/original-signer verification and same-input reuse pass on the VPS. The expected results below are the Windows acceptance target; LDPlayer input, exit and connection-loss behavior still require your report.

Use the existing single LDPlayer at `127.0.0.1:5555`, API28/x86_64. Keep all five runtime-v2 service windows open. Save and leave any active game before updating the app. Keep the same player account and record its ID/hero count before and after this batch if it was already created. Do not create a replacement player to work around a login failure.

The earlier A–H results remain accepted. The complete historical A–Z checklist is retained in [UNIFIED_GAME_ACCEPTANCE_1192617.md](UNIFIED_GAME_ACCEPTANCE_1192617.md) for the later J–Z gameplay checks. Do not repeat its old backup/fresh-initialization/build sequence. This batch requires no server update/build, database initialization, dependency upgrade, OBB transfer or profile import. The `.env` internet database remains unused.

At the first unexpected result, stop and send its step, exact message and relevant saved log. Keep app data, stages, journals, backups and runtime files. Never send passwords or private runtime/profile-key files. Record actual WAN status once for the batch and mention any subsequent change.

## U1. Update only the client

Temporarily connect Windows to GitHub. In PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    $repo = '/d/Test/wesnoth-setup/wesnoth_client'
    & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
    if ($LASTEXITCODE -ne 0) { throw 'Client pull failed. Stop and send the output.' }
    & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the client commit. Stop and send the output.' }
}
```

Expected: successful pull and the delivered client commit. Preserve existing README edits. Disconnect WAN again while retaining local Ethernet and LDPlayer. Keep the five services open; no routine restart is needed.

## U2. Build the corrected Android app offline

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android update failed. Send the saved rebuild/build logs.'
    }
}
```

Expected: the completed 1192617 account stages are retained, the new account engine/APK build succeeds, and `ANDROID ACCOUNT GAME REBUILD COMPLETE` appears. The helper reuses the original engine/dependency foundations and cached Gradle packages; it does not replace the installed OBB. Saved logs are `diagnostics/android-account-rebuild-*.txt` and `diagnostics/android-account-build-*.txt`. Do not delete an interrupted update journal or manually rename stages.

## U3. Install and retain the saved trusted server

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Android installation failed. Send the saved install log.'
    }
}
```

Expected: `ANDROID ACCOUNT GAME INSTALL COMPLETE`, verified installed version **1192618**, and the setup screen showing the existing **Trusted server: 100.99.99.14:15001** and **Start game**. The app update preserves its data and profile. Saved log: `diagnostics/android-account-install-*.txt`. If the saved profile is missing or unusable, stop and report it without importing/resetting it.

## U4. Welcome, clean cancellation and exact keyboard input

1. Choose **Start game**. Expect **Welcome to Wesnoth** with three direct buttons: **Log in**, **Sign up** and **Quit**. There must be no action list or extra OK selection step, and no usable gameplay behind the welcome screen.
2. Choose **Log in**, then **Cancel** before submitting. Expect a clean welcome screen with no old credential dialog left visible behind it. Open **Sign up**, then cancel before submitting; expect the same clean return. Neither cancellation should create an account or report a failed login.
3. In a login password field, enable **Show password** and type only a harmless test sample such as `aAzZ1!`, not your real password. Check lowercase, deliberate uppercase with Shift, deliberate Caps Lock on/off, and a symbol using your Windows keyboard layout. What appears must match what you typed; the first character must not be capitalized automatically. Turn off Caps Lock and release Shift afterward.
4. Choose **Reset keyboard modifiers**. Expect inline confirmation that modifiers were reset for new typing and existing text was not changed. The sample already in the field must remain exactly unchanged. Append a lowercase letter, then a deliberate Shift-uppercase letter and symbol. Normal intentional case must still work. Clear the whole sample and cancel; do not submit it as a login.
5. If you already created a player in runtime-v2, log in to that same player. Do not sign up again. If you have not created any player yet, use **Sign up** once with your chosen name and a private 12–128-character password, then its confirmation prompt. Expect automatic sign-in without a starter-leader choice. If signup gives an uncertain result, report it and try the same account's login only as instructed; do not make another account.
6. Open **Heroes -> My heroes**, then **Account details**. Record the actual player ID and hero count. An account that has not completed a campaign should still show **Heroes unlocked: 0**. Existing heroes/XP, if any, must remain unchanged.

## U5. One session and main-menu Log out

1. Open **Campaigns**, then return without starting a scenario. Open **Teams**, then return. Neither should request another login.
2. Open **Multiplayer**, then use **Back** to return to the main menu. It must retain the current account; Heroes -> Account details must show the same ID. Starting a multiplayer game or selecting an owned hero is not required for this check.
3. Use **Log out** on the main menu. Heroes should contain only **My heroes** and **Account details**, without its former duplicate logout action. Expect the welcome screen directly after the logout request, without a separate acknowledgement/OK dialog. This manual observation checks the signed-out UI; it does not independently prove server token revocation.
4. After logout, expect a solid authentication background and the welcome/login gate. Main-menu controls or gameplay must not remain accessible behind it. Cancel a login once to confirm the clean return, then log in to the same player. Check the same ID and hero count.

WAN remains disconnected throughout U4/U5. A working LAN account connection must not depend on public internet access.

## U6. Controlled account-bridge outage and recovery

This check stops **only the account bridge on port15001**. Keep MongoDB, the admin service, shared battles, native Multiplayer and LDPlayer running. Keep the game foreground, signed in and idle at its main menu, with no request or credential dialog already open.

1. In the existing **Run-WindowsAllianceBridge.ps1** window, press **Ctrl+C** once and wait for its PowerShell prompt. Normal shutdown prints `Alliance account bridge stopped.` and saves `diagnostics/alliance-bridge-run-*.txt`. If shutdown is uncertain, stop and report it rather than starting a duplicate bridge.
2. Return focus to LDPlayer, leave the game foreground and wait. It should detect the missing account connection automatically and clear its local signed-in session. The check interval is about 3 seconds; a request that reaches its timeout can add up to about 10 seconds, plus UI scheduling. Expect the connection-lost/sign-in explanation over a solid background, with no interactive old game/menu behind it. This is local sign-out; it does not claim the unreachable server revoked the previous token.
3. Choose **Log in** and make one attempt using the same account while the bridge is still stopped. Expect a clear connection error and return to the authentication flow, without a crash, frozen interface or access to gameplay. Cancel must not uncover the old game. This reconnect gate may show only **Log in** and **Quit**, because continuing the paused app requires the same player and database generation; do not create another player.
4. Restart the existing bridge in its PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expected: `ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service`. Keep this window open. Do not rebuild, reinitialize, change the trusted profile or switch back to the old runtime.

5. Log in with the **same player account**. Expect recovery to the paused app with the same player ID, hero count and XP. No account replacement or new reward should occur. If the bridge fails to reach READY or the app stays signed out after a correct reconnect, return the exact message and saved bridge log.
6. After that recovery passes, check the foreground-request path once: stop only the bridge again, wait for its PowerShell prompt, then immediately return to LDPlayer and tap **Multiplayer** before the periodic check opens the sign-in gate. Expect a connection error/authentication gate, **not the app closing**, and no usable old menu behind it. If automatic sign-out opens first, report that timing; it does not independently test the foreground-request path, and repeated racing clicks are unnecessary.
7. Restart the bridge with the exact command in step 4, require READY again, and log in to the **same account**. Expect the same player ID and collection. Keep the bridge and other four services running afterward. WAN remains disconnected; no separate WAN reconfirmation is needed between these two controlled outages.

This deliberately tests background detection and a foreground account request during a bridge outage, not every possible server outage or database restart.

## U7. Quit closes the app task

1. From the signed-in main menu choose its **Quit** action. Expect the Wesnoth app/task to close to LDPlayer's launcher, not return to the server-profile setup screen.
2. Reopen **Wesnoth Offline** from its icon. The saved trusted server must still be present. Choose Start game; expect fresh authentication rather than the previous in-memory session.
3. At Welcome choose **Quit** without logging in. Expect the whole app/task to close again, with no unauthenticated gameplay or setup screen left open.
4. Reopen, choose Start game and log in to the same player. Confirm the same player ID, hero count and any existing XP. Leave all five services running.

No campaign victory, hero unlock, team creation or XP correction is part of this corrective batch.

## Return one combined result

Return U1–U7 as PASS, FAILED or NOT RUN, the printed client commit, installed version, existing player ID/hero count and any changed XP. For a failure include the exact screen text, the first failing substep and its relevant saved build/install/bridge log. Report how long automatic sign-out took and whether Quit returned to the LDPlayer launcher. Confirm WAN was disconnected/local Ethernet connected for the batch; note any change. Never include passwords, tokens, `.env`, private keys or database backups.

After review, continue the retained gameplay checklist from J onward using this same runtime and account. Routine fixes repeat only the failed check and affected regressions; they do not repeat fresh setup or erase progress.
