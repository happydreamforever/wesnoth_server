# Next test: keep the player after the backend restarts

The user confirms the expected unavailable-service dialog while the account bridge was stopped and the same player ID/Spearman/level 1/zero experience after restart, without another login. WAN stayed disconnected with Ethernet connected. Accept that bridge interruption/recovery at user-observed scope; do not repeat it.

**Current step: restart the persistent backend, then use a fresh game login to read the same player.** Keep Ethernet connected and WAN disconnected. Use the existing account, public profile and Windows profile runtime. No pull, build, reinstall, new account, profile import or database initialization is required.

## 1. Quit the game and stop the three Alliance processes

1. In LDPlayer, dismiss the profile with **OK**, choose **Back to game**, then the main-menu **Quit**. Leave LDPlayer running. This discards the game's memory-only token so the later check uses a fresh login.
2. In the account-bridge PowerShell window (READY on15001), press **Ctrl+C once** and wait for its prompt. Normal output includes **Alliance account bridge stopped.**
3. In the admin-service PowerShell window (website18765), press **Ctrl+C once** and wait for its prompt.
4. In the database PowerShell window (MongoDB27018), press **Ctrl+C once** and wait for its prompt. Allow it to finish shutdown; do not close the window or press Ctrl+C repeatedly.

Keep the three windows available for restart. If a window does not return to its prompt, or reports a lock/database shutdown error, stop and send its output and saved log before starting duplicates. Do not delete operation.lock/operation.guard or database files. An intentional admin interruption can report exit130/Stopped; preserve that output. The current database launcher has no explicit clean-storage-shutdown success marker, so a returned prompt alone is not such proof.

## 2. Start MongoDB in its original window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for **Alliance MongoDB running on 127.0.0.1:27018.** Leave it running before starting the next component.

## 3. Start the admin/account service in its original window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Require **ALLIANCE DATABASE CHECK PASSED**, then **Alliance admin: http://127.0.0.1:18765/**. Leave it running. Existing startup text about game integration being a later milestone predates the accepted account update; it does not invalidate the successful database check.

## 4. Start the account bridge in its original window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require **ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service**. Leave all three windows open. If any startup fails, stop at that component and send its complete console output and saved log; do not initialize the database or rebuild.

## 5. Log in and retrieve the stored leader

Open the existing **Wesnoth Offline** app in LDPlayer, use the saved trusted server and choose **Start game**. Open **Alliance → Log in → Open**, then sign in as the existing **UniPlayer** with its private password. Dismiss the login confirmation and choose **View personal leader → Open**.

Expected: the same on-screen player ID, **UniPlayer**, **Spearman**, **Level 1**, **Experience 0**, **Total experience 0**. Compare with the previous profile; do not infer an exact ID from the earlier ambiguous copied text. Do not create another account or import a profile if something is missing; report the observation.

**Stop at the personal-leader dialog.** Return the three startup results, whether fresh login and the separate leader view match, and whether WAN remained disconnected throughout. On error, send the corresponding `wesnoth_server\diagnostics\alliance-database-*.txt`, `alliance-serve-*.txt` or `alliance-bridge-run-*.txt` log. Running launchers finish their saved transcripts when stopped; no need to stop a healthy component just to finalize its log. Never send passwords, tokens, private keys or private runtime configuration.

This checks the actual Android-created account and leader after an orderly backend restart. It does not test abrupt crash recovery, backup/restore, XP settlement or team gameplay. Earlier browser area persistence and bridge-only recovery remain separately accepted.
