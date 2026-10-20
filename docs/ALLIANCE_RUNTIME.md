# Alliance database and admin service — first implementation delivery

This delivery implements the persistent game rules and a local operator website. It does **not** add account login, new campaigns or Alliance Battle to the installed Android game yet. Those integrations remain in [the implementation checklist](ALLIANCE_IMPLEMENTATION.md). Continue using LDPlayer only.

The existing native guest server on TCP 15000, APK, OBB, source game data and native library stages are unchanged. Completed native server/Android builds are preserved. The small native component now compiles on Windows and passes its first six checks. The current handoff fixes the expired-certificate fixture and reuses that executable without rebuilding; all24-case completion remains pending.

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

The replica set enables atomic multi-document transactions; one member provides no redundant copy. The local helpers never read, modify or initialize through the old `.env`. The user corrected that URL to an internet server and confirmed that the game must use MongoDB on Windows. A prior read-only assessment made no remote database/configuration changes; the external deployment direction is withdrawn and no external mode was implemented. The runtime folder is ignored by Git and restricted to the current Windows account and SYSTEM. Keep it private; do not upload it with diagnostics. No default administrator password is supplied.

All website assets are local. Neither the website nor MongoDB binds to the LAN. Future Android account traffic will use the native server with provisioned TLS. Do not forward these local ports through a router.

## Windows sequence

Run one numbered step at a time. Dependency preparation and isolated installation passed on Windows. Local initialization then failed before administrator prompts with `Owned MongoDB did not start`. The user confirms the intended deployment is local MongoDB on Windows; the `.env` internet server must not be used. The returned log now proves a Windows sharing violation on the WiredTiger.turtle.set rename/deletion, followed by WT_PANIC and fatal assertion 50853. The process responsible is unknown. Resource Monitor then reported no matching handles. The subsequent scratch probe failed with winerror32, and its CSV identifies svchost.exe PID4600 holding the source without delete sharing. The subsequent elevated lookup confirms blocker4600 is a child of4196 hosting NetActvity; its implementation/purpose and the actual MongoDB-crash holder remain unverified. The returned event Stack contains 13 unresolved caller addresses. The complete module.txt has 76 rows, with no matching ranges; even a known Kernel32 stack address is absent. The returned JSON shows all 13 caller addresses currently in private executable memory with matching process identity. The expanded Defender alert now identifies C:\Windows\SysWOW64\netactive32.dll as the affected file for Trojan:Win32/Wacatac.B!ml, Severe, Active, at 10/19/2026 3:36 PM. Any link to the traced process or MongoDB crash remains unverified. Network disconnection and quarantine outcome are unconfirmed. On 2026-10-20 the user reports being unable to delete it and asks to set the issue aside; the method/error is unspecified, so a failed Defender quarantine is not established. Malware troubleshooting is deferred. The Windows Python TLS identity fixture now passes; current NEXT_TEST.md supplies the native C++ fixture retry using the successfully compiled probe; no repeated scan/removal question or MongoDB restart is requested. Earlier service configuration/registry/reboot checks were inconclusive and are not repeated. Preserve the partial runtime, scratch evidence and crash dump; do not retry step3, repair/delete metadata, terminate processes or change services/security settings. The native fixture retry requires a normal source pull and the explicit existing probe path; no compile, collector rerun, reinstall or game rebuild is requested. The commands below remain the planned local sequence, not instructions to rerun initialization now.

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

The MongoDB installer makes at most six final-directory rename attempts for Windows errors 5/32/33, with 0.5/1/2/4/8s waits. It checks that the verified extraction is unchanged and the destination remains absent before each attempt. A completed extraction is preserved if publication fails; the log reports its path. Stop and return that log rather than deleting the extraction or destination. A later invocation does not automatically adopt preserved `.extract-*` directories. This retry does not change ACLs, services, archive pins or database data.

Clean database shutdown releases `operation.lock`. A forced process termination or power failure can leave it behind. The helper deliberately refuses a second database operation rather than guessing whether another process owns the database. Return the error and process status for a verified recovery step; do not delete a live lock or launch another MongoDB against the same data directory. A full crash-recovery/backup/restore tool remains unchecked in the implementation checklist.

Interrupted progression runs stay reserved until the bridge completes them or an administrator cancels them with an audit reason. Cancellation releases reservations without XP. Completed results cannot be replaced or cancelled through the admin interface. Result disputes and controlled XP correction are later releases.

## VPS verification and limits

The verification environment uses Python 3.14.3 and MongoDB 8.0.32. Linux and Windows executable files and OS libraries differ; Windows wheel hashes are pinned separately. The actual tests run with external networking disabled. Test databases use isolated `alliance_test_*` names on a separate test port; deployment tests use a temporary owned directory. The private `.env` database is never a test target.

`tools/Dockerfile.alliance-verify` records the container image digests and matching Python package versions. Build its small context from that file and `tools/alliance-dependencies/requirements-verify.txt`; never send `.env` or runtime data as a build context. Use `--ulimit nofile=65536:65536` for the Linux test container: repeated fixture collection creation exhausted the default 1024 descriptors in an earlier run. That infrastructure failure was corrected before the final passing run.

Real-database checks cover concurrent team membership/start claims, repeat settlement, transaction rollback, changed leaders/captains, schema uniqueness, admin authorization, CSRF, session expiry/revocation, local-only HTTP, initialization and clean restart. PowerShell helpers are exercised with simulated native tools under Linux PowerShell 7.4.6; actual Windows PowerShell 5.1, MongoDB execution and visual browser behavior await the user's report.


## Completed Windows Python identity fixture

The Python fixture has passed; do not repeat it for the native handoff. [NEXT_TEST.md](NEXT_TEST.md) now gives the small C++ component check. `Test-WindowsAllianceTransport.ps1` prepares/reuses a separate `runtime/alliance-transport` identity using installed Python3.14.3 and MINGW64 OpenSSL3.6.3. No MongoDB or native server starts. The private key is restricted to the current Windows account and SYSTEM; only `public-profile.json` is intended for later trusted client provisioning. It contains a public self-signed leaf certificate, canonical server IP, future port15001, minimum TLS1.2 and certificate SHA256. Do not transfer private keys to clients.

The fixture verifies TLS1.2/TLS1.3 payload round trips, wrong-IP rejection, untrusted-certificate rejection and plaintext rejection on loopback only. Existing identities are verified and reused without renewal; changed IP/port, expired certificates or incomplete/modified files fail with the original files preserved. Submit the saved diagnostics/alliance-transport text and JSON reports; do not send the identity directory. This does not establish native game account support, LAN reachability or database readiness. Existing guest gameplay remains unchanged.


Latest Windows identity result (reported2026-10-20): the corrected fixture reuses the existing identity and passes TLS1.2/TLS1.3 encrypted round trips plus wrong-IP, untrusted-certificate and plaintext rejection. Saved report stem: alliance-transport-20261019-165349-386-09cf43f88ef94e64a4314f0021d642a4. Only console text was returned; raw reports and WAN-disconnection status were not supplied. No repeated Python fixture is needed.

## Native connection component handoff

Client `alliance_native/transport.hpp/.cpp` is a new reusable component, outside the pinned upstream engine. It validates a typed trusted public profile, accepts only native TLS preamble1 followed by0, verifies the numeric-IP certificate and exact DER pin with an isolated trust store, and permits framed application bytes only after verification. It does not discover/trust arbitrary remote profiles, follow redirects or reconnect in plaintext.

Its worker-thread API separates connect/send/receive, supports server-push frames, has no outgoing queue, bounds compressed frames to64KiB, and supports monotonic deadlines/cancellation. It does not decompress or interpret WML. Future callers must bound decompression and validate account message schemas. Operations are serialized, accept at most10seconds and close on timeout; future UI integration must provide a network worker and deliberate idle/reconnect behavior. This is an account transport component, not a replacement for the full game relay or its large scenario payloads.

`Test-WindowsAllianceNative.ps1` builds two C++ files into a new owned directory with existing MINGW64 dependencies and runs24 real native checks through `test_alliance_native.py`. It reads the existing public profile only; original private identity and MongoDB runtime remain untouched. Disposable test identities are created in a separate restricted fixture directory. Reports contain version/case/phase/error metadata, not keys or account payloads. Both success and failure preserve reports and build state. Follow NEXT_TEST.md for the exact command and expected markers.

The actual Windows/LDPlayer native component acceptance remains pending. No changed APK/menu is delivered yet. Trusted profile import, selection of this component by Alliance login/team screens, the backend bridge and local database acceptance remain unchecked integration tasks.
