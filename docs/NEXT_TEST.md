# Next Windows test: start the database and sign in to administration

The latest console output confirms administrator initialization passed. The username prompt appeared first, administrator `Uni` was accepted, the authenticated MongoDB8.0.32 setup completed, and the owned database stopped. Keep the same `%LOCALAPPDATA%\WesnothAlliance\runtime` directory and the password you chose. Do not repeat initialization.

This handoff uses helpers already installed in your checkout. No pull, download, build or reinstall is needed for this documentation update. Keep WAN disconnected and local Ethernet connected. Use normal PowerShell windows under the same Windows account as initialization. The earlier standalone storage test was confirmed offline; WAN status for the successful administrator initialization has not yet been reported.

## 1. Start the database in PowerShell window 1

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected after the version/pin checks:

```text
Alliance MongoDB running on 127.0.0.1:27018. Keep this window open. Ctrl+C stops this process.
```

Wait for that line and leave the window open. If an error appears, stop here and return its output. The command keeps running normally; it should not return to the prompt while the database is serving.

## 2. Start the administrator website in PowerShell window 2

Open a second normal PowerShell window while the database window stays open:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

This service automatically checks the database version, authenticated primary, schema, administrator and an aborted transaction before serving the website. A separate Test-WindowsAlliance command is not needed for this step. Expected:

```text
PASS MongoDB 8.0.32 / authenticated replica set / schema / administrator / transaction rollback
ALLIANCE DATABASE CHECK PASSED
Alliance admin: http://127.0.0.1:18765/
```

Another scope notice and keep-window-open message are normal. Leave both windows open. An error means stop and return the output; do not delete data/locks, rerun initialization or launch extra database instances.

## 3. Open the website in the Windows browser

Open `http://127.0.0.1:18765/` in a browser on the Windows computer. This website is local to Windows; use its browser rather than the Android app.

Sign in with username `Uni` and the password you entered during initialization. Expected: the Overview page headed **Your Alliance world**, showing your signed-in username. Click **Areas** and confirm **Area 1** appears. Viewing it is enough for this step; creating an area, checking its audit record and testing persistence across restart come after this result.

Return both windows' visible startup/error output, whether login succeeded and Area 1 appeared, and whether WAN was disconnected. Do not send passwords, `.env`, cookies or private runtime files. The game still uses the working guest flow; persistent Android accounts/progression/Alliance battles are not connected yet.

Database/service transcripts are saved under `D:\Test\wesnoth-setup\wesnoth_server\diagnostics` as `alliance-database-*.txt` and `alliance-serve-*.txt`. Their exact Saved log paths are printed after the commands exit; do not stop healthy windows just to get those paths. The MongoDB log remains `%LOCALAPPDATA%\WesnothAlliance\runtime\logs\mongodb.log`. Keep previous runtime/scratch/log/dump evidence and all completed game stages.
