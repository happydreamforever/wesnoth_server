# Next test: recover from a temporary account-bridge interruption

The user confirms game restart retained the trusted server, required a fresh login and returned the same UniPlayer ID, Spearman, level1 and both experience values0. WAN stayed disconnected with Ethernet connected. Accept this as user-observed app restart; no backend/database restart or independently captured process termination is claimed.

**Current step: stop and restart only the account bridge, then recover the current account session.** Keep LDPlayer logged in and leave the MongoDB window (27018) and admin-service window (18765) running. Keep Ethernet connected and WAN disconnected. No pull, build, reinstall, new account, profile import or database restart is needed.

## 1. Stop the bridge and make one leader request

1. Find the Windows PowerShell window displaying **ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001**. Press **Ctrl+C** in that window only.
2. Wait for its PowerShell prompt to return. Normal output includes **Alliance account bridge stopped.** and a saved `wesnoth_server\diagnostics\alliance-bridge-run-*.txt` log. If it does not return, stop and report that output; do not start a duplicate bridge or stop the database/admin windows.
3. In LDPlayer, dismiss the old personal-leader dialog with **OK**, then select **View personal leader → Open** once. Stay logged in.
4. Expected: **The Alliance service is unavailable. Check the Windows database, service and account bridge.** If the connection is dropped rather than refused, **The server did not reply in time...** is also an acceptable bounded error. The request has a ten-second overall deadline; allow a few seconds for the UI. If it is still pending after roughly15 seconds, choose **Cancel** and record that result.

Record the exact message. A new successful profile response while the bridge is supposedly stopped, an identity error, an unexpected sign-out or an unresponsive app is not a pass. Preserve that observation; if the bridge is confirmed stopped, restore it using the command below. Do not log out, register again, reimport the profile or reset the app.

## 2. Restart the existing bridge

In the same bridge PowerShell window, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require **ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service**. Leave this window open. If startup fails, send its complete console output and the new saved `alliance-bridge-run-*.txt` log, then stop; do not rebuild or initialize MongoDB.

## 3. Retrieve the leader again

After READY, dismiss the previous Android error and select **View personal leader → Open** again, using the existing session without another login. Expected: the same player ID, **UniPlayer**, **Spearman**, **Level 1**, **Experience 0**, **Total experience 0**.

**Stop with the recovered profile visible.** Report the stopped-bridge error, new READY result, whether the same profile returned without login, and WAN status. If the app asks to log in or reports a different error, send that observation before changing anything. Do not send passwords, tokens, private keys or runtime files.

This tests one account-bridge interruption and recovery. The unavailable/timeout path should retain the in-memory session/profile, and a successful later request refreshes them from the running local service. It does not prove resilience to every network failure, restart MongoDB/admin or establish player persistence across their restart. Custom progression/team gameplay remains later implementation.
