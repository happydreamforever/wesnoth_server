# Alliance database and admin service — first implementation delivery

This delivery implements the persistent game rules and a local operator website. It does **not** add account login, new campaigns or Alliance Battle to the installed Android game yet. Those integrations remain in [the implementation checklist](ALLIANCE_IMPLEMENTATION.md). Continue using LDPlayer only.

The existing native guest server on TCP 15000, APK, OBB, source game data and native library stages are unchanged. No native or Android rebuild is required for this delivery.

## What is implemented

- Accounts with Argon2id password hashes, scoped sessions, explicit expiry, logout/revocation and login throttling.
- One persistent leader with the actual 1.19.26 advancement choices and XP thresholds. Permanent leader snapshots cannot change after captains approve a battle proposal.
- Eight-member teams, membership applications and rejection/withdrawal, captain transfer, areas and area standings.
- Campaign progression records and fixed 2v2/3v3/4v4 battle proposals, mutual captain approval, readiness and atomic start reservations.
- Transactional leader/team XP and rating settlement, duplicate-result protection, conflicting-result rejection and audited cancellation.
- Admin login and views for accounts, teams, areas, runs, rewards and audit history. Admins can suspend/reactivate players, create areas, move inactive teams and cancel interrupted runs with a reason.

Only a trusted local native-server bridge can eventually submit game results. The internal service interface exists; the bridge and playable custom mission content are not delivered yet. The service's health response states `game_bridge_integrated=false` and `campaign_content_ready=false`.

## Local components

| Component | Selection |
| --- | --- |
| Python | Existing native Windows x86_64 3.14.3, isolated environment under `build\alliance-venv` |
| MongoDB | Portable 8.0.32, `127.0.0.1:27018`, authenticated single-member `wesnoth-rs` replica set |
| Database | `wesnoth_game`; application user has only that database's `readWrite` role |
| Website/service | Flask 3.1.3 and Waitress 3.0.2; `http://127.0.0.1:18765/` |
| Driver/passwords/forms | PyMongo 4.18.3, argon2-cffi 25.1.0, Flask-WTF 1.3.0 |
| Dependency pins | All 17 Windows wheels and portable Mongo archive in `tools/alliance-dependencies/windows.json`, with byte counts and SHA256 |
| Private runtime | `runtime\alliance`; generated settings, operator credentials, replica-set key, database files and local Mongo log |

The replica set enables atomic multi-document transactions; one member provides no redundant copy. The old `.env` is never read, modified or used for initialization. The existing remote database audited during planning is not this deployment. The runtime folder is ignored by Git and restricted to the current Windows account and SYSTEM. Keep it private; do not upload it with diagnostics. No default administrator password is supplied.

All website assets are local. Neither the website nor MongoDB binds to the LAN. Future Android account traffic will use the native server with provisioned TLS. Do not forward these local ports through a router.

## Windows sequence

Run one numbered step at a time. Step 1 now passed on Windows (server e9b42e7/client d8ab444): all 17 wheels and MongoDB 8.0.32 verified. Current handoff is step 2 only; no pull or repeat download is needed. Return its saved installation log before continuing to initialization. Use the existing checkouts under `D:\Test\wesnoth-setup`.

### 1. While temporarily connected: pull and prepare the cache

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server'
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Prepare-WindowsAlliance.ps1' -Download
    if ($LASTEXITCODE -ne 0) { throw 'Alliance preparation failed. Send the saved log.' }
}
```

Expected: `ALLIANCE DEPENDENCIES VERIFIED: 17 wheels; MongoDB 8.0.32.` The first download is approximately 810 MB, mostly the MongoDB archive. The helper verifies pinned hashes and saves `diagnostics\alliance-prepare-*.txt`. Existing matching files are reverified and reused. Temporary connection/read failures and HTTP 408/429/500/502/503/504 receive at most three attempts, with 2s/4s delays. A retry restarts only the current transfer; completed files stay cached. Hash/size mismatches, certificate errors and local file errors stop without automatic retry. After a network failure, keep internet connected and rerun this same step; do not delete the cache. This step downloads files; it does not install MongoDB, start a service, alter the old database or rebuild the game.

### 2. Offline: install the new backend environment

Disconnect WAN access while keeping the local network. In PowerShell:

```powershell
Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Install-WindowsAlliance.ps1'
if ($LASTEXITCODE -ne 0) { throw 'Offline installation failed. Send the saved log.' }
```

Expected: `ALLIANCE OFFLINE ENVIRONMENT INSTALLED`. This creates only the new isolated Python environment and portable Mongo directory. Installation uses `--no-index --require-hashes`. No Windows service or global Python package is installed. If `mongod.exe` cannot start because a Windows runtime is missing, stop and return the error; the matching archive contains a runtime installer, but the helper does not silently run it.

### 3. Initialize the private local database and administrator

```powershell
Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Initialize-WindowsAlliance.ps1'
if ($LASTEXITCODE -ne 0) { throw 'Initialization failed. Send only the error, not private runtime files.' }
```

Enter your chosen administrator username (3–24 letters, digits or underscores), then a password of 12–128 characters twice. Password input is hidden. This step deliberately does not record a console transcript. Expected: `ALLIANCE INITIALIZATION PASSED`, then the temporary owned database stops. Rerunning initialization with the unchanged owned runtime preserves existing credentials and accounts.

### 4. Run the database and website in two PowerShell windows

Database window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1'
```

Website window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1'
```

Keep both open. Expected: database running on `127.0.0.1:27018`, then the admin URL `http://127.0.0.1:18765/`. Open that URL in the Windows browser and sign in with the administrator created above. The initial website shows Area 1 and the administrator account; the existing guest game has no persistent player accounts yet.

### 5. Test persistence and permissions

In a third PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsAlliance.ps1'
if ($LASTEXITCODE -ne 0) { throw 'Alliance database check failed. Send the saved log.' }
```

Expected: `ALLIANCE DATABASE CHECK PASSED`. The helper checks version, authenticated primary, supported schema, administrator and an explicitly aborted transaction. It does not simulate Android gameplay.

In the website, create `Area 2`. Confirm it appears under Areas and the creation appears under Audit. Sign out; the dashboard must require login again. Stop the website with Ctrl+C, then the database with Ctrl+C. Restart database then website, sign in, and confirm Area 2 still exists. Report these observations along with `diagnostics\alliance-check-*.txt`. The captured local check cannot substitute for these browser/restart observations.

## Recovery boundaries

Existing files with a different hash or ownership marker are preserved and rejected. Do not reset/delete completed native stages, overwrite `.env`, or remove `runtime\alliance\data` to retry setup.

Clean database shutdown releases `operation.lock`. A forced process termination or power failure can leave it behind. The helper deliberately refuses a second database operation rather than guessing whether another process owns the database. Return the error and process status for a verified recovery step; do not delete a live lock or launch another MongoDB against the same data directory. A full crash-recovery/backup/restore tool remains unchecked in the implementation checklist.

Interrupted progression runs stay reserved until the bridge completes them or an administrator cancels them with an audit reason. Cancellation releases reservations without XP. Completed results cannot be replaced or cancelled through the admin interface. Result disputes and controlled XP correction are later releases.

## VPS verification and limits

The verification environment uses Python 3.14.3 and MongoDB 8.0.32. Linux and Windows executable files and OS libraries differ; Windows wheel hashes are pinned separately. The actual tests run with external networking disabled. Test databases use isolated `alliance_test_*` names on a separate test port; deployment tests use a temporary owned directory. The private `.env` database is never a test target.

`tools/Dockerfile.alliance-verify` records the container image digests and matching Python package versions. Build its small context from that file and `tools/alliance-dependencies/requirements-verify.txt`; never send `.env` or runtime data as a build context. Use `--ulimit nofile=65536:65536` for the Linux test container: repeated fixture collection creation exhausted the default 1024 descriptors in an earlier run. That infrastructure failure was corrected before the final passing run.

Real-database checks cover concurrent team membership/start claims, repeat settlement, transaction rollback, changed leaders/captains, schema uniqueness, admin authorization, CSRF, session expiry/revocation, local-only HTTP, initialization and clean restart. PowerShell helpers are exercised with simulated native tools under Linux PowerShell 7.4.6; actual Windows PowerShell 5.1, MongoDB execution and visual browser behavior await the user's report.
