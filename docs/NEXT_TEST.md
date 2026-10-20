# Next Windows test: save an area and verify it survives restart

The returned console confirms both profile database and local website startup, including the database/schema/administrator/transaction check. The user confirms browser login as Uni, Area 1 visible and WAN disconnected with local Ethernet connected. This is user-observed browser/connectivity acceptance. Administrator initialization previously ran with internet access available; that separate fact is unchanged.

Use the existing running database and website. No pull, download, build, reinstall or initialization is needed. Keep WAN disconnected and local Ethernet connected. Continue under the same Windows account and with the same `%LOCALAPPDATA%\WesnothAlliance\runtime` directory. This step creates one real area and retains it for the game.

## 1. Create one area in the Windows browser

At `http://127.0.0.1:18765/`, sign in as `Uni` if needed. Click **Areas**. Under **Create an area**, enter `Area 2` in **Area name**, then click **Create area** once. If that name already exists, use another unused name, such as `Area 3`, and note which name you chose.

Expected: **Area created.** and the new area's name, identifier and **Enabled** status in **Area list**. Note its identifier for comparison after restart. This is an area identifier, not a password or credential.

## 2. Check the saved audit entry and sign-out

Click **Audit log**. Find the new row with **Action** `create_area`, **Target** equal to the area's identifier and **Reason** `Create an area`. Actor and Target are identifiers; the audit table does not display the administrator's username or the area's name.

Click **Sign out**, then type `http://127.0.0.1:18765/` in the address bar and load it again. Expected: the login page. Use a fresh request rather than the browser Back button.

If creation, audit or sign-out differs from these expectations, stop and report what appeared before proceeding to restart.

## 3. Stop the website, then the database

In the PowerShell window running `Run-WindowsAlliance.ps1`, press **Ctrl+C once** and wait for the PowerShell prompt. Then, in the window running `Run-WindowsAllianceDatabase.ps1`, press **Ctrl+C once** and wait for its prompt. Allow shutdown to finish before restarting either process.

If an error appears or a prompt does not return, stop and send the output. Do not force-close windows, repeatedly interrupt shutdown, delete lock files, rerun initialization or launch a second database. The scripts normally print their **Saved log** paths when they exit; retain those transcripts.

## 4. Restart the database in its PowerShell window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for:

```text
Alliance MongoDB running on 127.0.0.1:27018. Keep this window open. Ctrl+C stops this process.
```

Leave this window running. If startup fails, stop here and return its output.

## 5. Restart the website in its PowerShell window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected after the version/pin checks:

```text
PASS MongoDB 8.0.32 / authenticated replica set / schema / administrator / transaction rollback
ALLIANCE DATABASE CHECK PASSED
Alliance admin: http://127.0.0.1:18765/
```

The scope and keep-window-open messages are normal. The launcher performs the database check automatically; no separate Test-WindowsAlliance command is needed. Leave both windows open. If startup fails, stop and return the output.

## 6. Confirm persistence and report

Load `http://127.0.0.1:18765/` afresh and sign in as `Uni` with the same password. Under **Areas**, confirm the new area has the same name and identifier. Under **Audit log**, confirm the matching `create_area` record remains. Do not recreate the area after restart; finding the existing record is the test.

Return:

- The new area's name, whether creation and matching audit entry succeeded, and whether sign-out required login on a fresh request.
- Both restart outputs and whether the same area identifier and audit entry survived.
- Any unexpected shutdown/startup message. Keep WAN disconnected throughout this test; mention if connectivity changed.

Transcripts are saved under `D:\Test\wesnoth-setup\wesnoth_server\diagnostics` as `alliance-database-*.txt` and `alliance-serve-*.txt`; exact **Saved log** paths appear after exit. Healthy restarted windows can stay open while you report their visible output. The MongoDB log remains `%LOCALAPPDATA%\WesnothAlliance\runtime\logs\mongodb.log`. Do not send passwords, `.env`, cookies or private runtime files.

This acceptance checks local administration and persistence. Android account login, leader progression and Alliance Battle integration remain pending. Preserve the working guest game, all completed builds/data/receipts, and earlier runtime/scratch/log/dump evidence.
