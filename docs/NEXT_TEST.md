# Next test: preserve Koichi across a full Alliance restart

The user confirms the Yama directory returns the same Koichi team ID, roster and starting values. The supplied personal profile confirms UniPlayer still has Spearman, level 1, Experience 0 and Total experience 0. The all-confirmed reply covers the requested WAN-disconnected/local-Ethernet conditions at user-observed scope. Creation, separate My team retrieval, directory lookup and unchanged personal leader are accepted. Team persistence after a restart remains untested.

Keep WAN disconnected and local Ethernet connected throughout this phase. Leave LDPlayer open. Use the installed app, saved trusted server and existing runtime. No pull, rebuild, installation, profile import, database initialization or new team is needed.

## 1. Stop the current game and Alliance processes

1. In the personal-leader dialog press **OK**, then **Back to game**, then the game main menu's **Quit**. Leave LDPlayer itself open.
2. In the **account bridge** PowerShell window, press **Ctrl+C once** and wait for its PowerShell prompt.
3. In the **admin service** window, press **Ctrl+C once** and wait for its prompt.
4. In the **MongoDB** window, press **Ctrl+C once** and wait for its prompt before proceeding.

The admin launcher may report `Stopped` or exit 130 for the intentional interruption. This is distinct from a startup failure. If a process does not return to its prompt, or there is a database/runtime-lock error, stop and send the output. Preserve runtime files and locks; do not force-kill processes or launch duplicates. MongoDB's helper requests an authenticated shutdown, but a returned prompt alone is not evidence of clean storage shutdown.

## 2. Start MongoDB

In the database PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Require **Alliance MongoDB running on 127.0.0.1:27018**. Keep the window open and wait for that marker before starting the next component.

## 3. Start the admin service

In the admin PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Require **ALLIANCE DATABASE CHECK PASSED** and **Alliance admin: http://127.0.0.1:18765/**. Keep the window open. Existing historical text about integration being a later milestone does not supersede the accepted account/team functionality.

## 4. Start the account bridge

In the bridge PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require **ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service** and keep this window open. If any startup fails, stop at that component and return its console error and saved diagnostic log; do not continue to the game test.

## 5. Retrieve the stored team after fresh login

1. Reopen **Wesnoth Alliance** in LDPlayer. The existing **Trusted server: 100.99.99.14:15001** should remain visible. Press **Start game**.
2. Open **Alliance**, select **Log in**, then **Open**. Use the existing **UniPlayer** credentials and press **Log in**.
3. Require the same on-screen player ID, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. Press **OK**.
4. Select **Teams → Open → My team → Open**.
5. Require **Koichi**, team ID **4cd736d3-dc6c-4c3d-a816-e7682b56db30**, **Yama**, team level **1**, team experience **0**, rating **1000**, members **1/8** and **UniPlayer (captain) — Spearman, leader level 1**.

**Stop at that dialog.** Return whether all three processes stopped and restarted, the readiness outputs, whether the player and team values match after fresh login, and whether WAN stayed disconnected. A successful result establishes stored team retrieval across this controlled restart, not power-loss recovery or team battle functionality.

The latest pasted area/player IDs include non-hexadecimal characters; do not change stored IDs or guess corrections. Use direct on-screen comparison. The earlier valid area reference remains `ff010e4d-af74-4906-8ba6-5f096aaf90ec`.

Launchers save logs under `wesnoth_server\diagnostics\alliance-database-*.txt`, `alliance-serve-*.txt` and `alliance-bridge-run-*.txt`; active transcripts finalize when their windows stop. Do not stop healthy components just to finish a log. Return console output or a saved error log, never passwords, tokens, private identity files or runtime credentials. Preserve Koichi, Yama, the runtime, identity, original game/OBB/native stages and all build backups.
