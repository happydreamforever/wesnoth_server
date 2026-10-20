# Alliance database and admin service — first implementation delivery

This delivery implements the persistent game rules and a local operator website. It does **not** add account login, new campaigns or Alliance Battle to the installed Android game yet. Those integrations remain in [the implementation checklist](ALLIANCE_IMPLEMENTATION.md). Continue using LDPlayer only.

The user now prioritizes local MongoDB setup. We use **MongoDB Community Edition8.0.32**, the free self-managed edition that can run offline ([official overview](https://www.mongodb.com/products/self-managed/community-edition)). The pinned portable MongoDB and17 Python packages already passed Windows installation. Reuse them. The previous failure was database startup, not a missing paid product or installer.

Current action: the Windows database and administrator website acceptance is complete at the delivered scope. The user confirms the saved area, matching audit identifier and login page after sign-out following the offline restarts. Preserve both applications and all data. The next milestone in [NEXT_TEST.md](NEXT_TEST.md) is the standalone Android transport check; it does not use MongoDB or change the installed game.

| Stage | Current state |
| --- | --- |
| Download pinned MongoDB and Python wheels while connected | Complete on Windows; cache retained |
| Install from the local cache | Complete on Windows; installation itself was performed while internet remained available |
| Verify MongoDB startup and clean-restart persistence | Complete on Windows under LOCALAPPDATA; user confirms WAN disconnected and local Ethernet connected |
| Initialize the authenticated game replica set, schema and administrator | Complete on Windows; username Uni; selected profile runtime; internet access was available during initialization |
| Start database and local admin website; check transactions and login | Complete on Windows; console checks pass; browser login/Area 1/WAN disconnection user-confirmed |
| Verify database and website restart | Re-launches succeed in returned Windows output; user confirms WAN disconnected. Recovery-helper backup report and shutdown exit codes not supplied |
| Create an area, check audit and sign-out, verify records after restart | Passed by user report: same area name, matching audit identifier, login required after sign-out; WAN disconnected during restarts |
| Connect Android accounts, progression and Alliance Battle | Pending integration |

The final database binds to127.0.0.1:27018 and the administrator website to127.0.0.1:18765. The Windows game service will use the database locally; Android clients will communicate with the game service. The internet database URL in `.env` is not used.

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
| Private runtime | `%LOCALAPPDATA%\WesnothAlliance\runtime`, selected explicitly with `-RuntimeRoot`; settings, operator credentials, replica-set key, database files and local Mongo log |

The replica set enables atomic multi-document transactions; one member provides no redundant copy. The local helpers never read, modify or initialize through the old `.env`. The user corrected that URL to an internet server and confirmed that the game must use MongoDB on Windows. A prior read-only assessment made no remote database/configuration changes; the external deployment direction is withdrawn and no external mode was implemented. The selected profile runtime is outside the repositories and restricted to the current Windows account and SYSTEM. Keep it private; do not upload it with diagnostics. No default administrator password is supplied.

All website assets are local. Neither the website nor MongoDB binds to the LAN. Future Android account traffic will use the native server with provisioned TLS. Do not forward these local ports through a router.

## Windows sequence

Follow [NEXT_TEST.md](NEXT_TEST.md) for the next Android transport check. The browser acceptance is complete. The launch commands below are references for future sessions, not a request to start duplicate processes. The existing credentials and profile data remain authoritative. Do not initialize again or delete either MongoDB storage locks or operation.guard.

The profile standalone fixture passed startup, journaled write/read, both clean shutdowns and a persisted read after restart. This does not prove recovery of the old repository database or the disappearance of the earlier sharing conflict. Keep `runtime/alliance`, its logs/lock evidence, all disposable test directories and crash dumps. The user deferred the malware investigation; no service/security changes are part of this step.

### 1. Initialization completed

Actual Windows initialization passed in `C:\Users\Uni\AppData\Local\WesnothAlliance\runtime`, with administrator `Uni`. The corrected prompt order was visible; the helper reported authenticated MongoDB8.0.32, single-node replica set, scoped application user and administrator ready, then database stopped. Keep the chosen password private. No repeated initialization is needed.

All four runtime helpers accept `-RuntimeRoot`. Always select the same `%LOCALAPPDATA%\WesnothAlliance\runtime` when starting/checking this database. Omitting it retains the old repository default; there is no automatic migration. Existing unowned directories, redirected paths and stale operation locks remain refused. Keep old runtime/scratch/log/dump evidence intact.

### 2. Run the database and website in two PowerShell windows

Database window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Website window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Keep both open. Expected: database running on `127.0.0.1:27018`, then the admin URL `http://127.0.0.1:18765/`. Open that URL in the Windows browser and sign in with the administrator created above. Sign in as `Uni`, then view Areas to find Area 1; the existing guest game has no persistent player accounts yet.

### 3. Test persistence and permissions

Completed by user report after the offline restarts: **Areas** retained the same name, the **Audit log** identifier matched, and fresh root-URL access after **Sign out** showed the login page. These observations complement the automatic database checks. Do not repeat the test or create another area for this checkpoint.

## Recovery boundaries

Existing files with a different hash or ownership marker are preserved and rejected. Do not reset/delete completed native stages, overwrite `.env`, or remove `runtime\alliance\data` to retry setup.

The MongoDB installer makes at most six final-directory rename attempts for Windows errors 5/32/33, with 0.5/1/2/4/8s waits. It checks that the verified extraction is unchanged and the destination remains absent before each attempt. A completed extraction is preserved if publication fails; the log reports its path. Stop and return that log rather than deleting the extraction or destination. A later invocation does not automatically adopt preserved `.extract-*` directories. This retry does not change ACLs, services, archive pins or database data.

The updated launcher holds an OS lock on permanent `operation.guard` throughout database ownership and cleanup. The OS releases that lock when the owning process exits; the guard file remains. A legacy `operation.lock` from older launchers is refused. The separate Repair-WindowsAllianceRuntimeLock.ps1 helper can preserve an evidence-checked stale marker only while no competing application processes/listeners remain; it does not repair MongoDB storage. Do not delete the guard, bypass a busy lock or launch another MongoDB against the same data directory. The latest user output shows successful re-launches, but the recovery backup report has not been supplied. A full database crash-recovery/backup/restore tool remains unchecked in the implementation checklist.

Interrupted progression runs stay reserved until the bridge completes them or an administrator cancels them with an audit reason. Cancellation releases reservations without XP. Completed results cannot be replaced or cancelled through the admin interface. Result disputes and controlled XP correction are later releases.

## VPS verification and limits

The verification environment uses Python 3.14.3 and MongoDB 8.0.32. Linux and Windows executable files and OS libraries differ; Windows wheel hashes are pinned separately. The actual tests run with external networking disabled. Test databases use isolated `alliance_test_*` names on a separate test port; deployment tests use a temporary owned directory. The private `.env` database is never a test target.

`tools/Dockerfile.alliance-verify` records the container image digests and matching Python package versions. Build its small context from that file and `tools/alliance-dependencies/requirements-verify.txt`; never send `.env` or runtime data as a build context. Use `--ulimit nofile=65536:65536` for the Linux test container: repeated fixture collection creation exhausted the default 1024 descriptors in an earlier run. That infrastructure failure was corrected before the final passing run.

Real-database checks cover concurrent team membership/start claims, repeat settlement, transaction rollback, changed leaders/captains, schema uniqueness, admin authorization, CSRF, session expiry/revocation, local-only HTTP, initialization and clean restart. PowerShell helpers are exercised with simulated native tools under Linux PowerShell7.4.6. Actual Windows standalone MongoDB startup/persistence now passes; profile administrator initialization also passes. Authenticated service startup/transaction checks now pass in the returned Windows console; browser login, Area 1 and WAN-disconnected operation are user-confirmed. Database and website re-launches now also pass in the returned output, with WAN disconnected by user report. Same-area/audit persistence and sign-out browser acceptance now pass by user report.


## Completed Windows Python identity fixture

The Python and native Windows fixtures have passed; do not repeat them for the current MongoDB handoff in [NEXT_TEST.md](NEXT_TEST.md). `Test-WindowsAllianceTransport.ps1` prepares/reuses a separate `runtime/alliance-transport` identity using installed Python3.14.3 and MINGW64 OpenSSL3.6.3. No MongoDB or native server starts. The private key is restricted to the current Windows account and SYSTEM; only `public-profile.json` is intended for later trusted client provisioning. It contains a public self-signed leaf certificate, canonical server IP, future port15001, minimum TLS1.2 and certificate SHA256. Do not transfer private keys to clients.

The fixture verifies TLS1.2/TLS1.3 payload round trips, wrong-IP rejection, untrusted-certificate rejection and plaintext rejection on loopback only. Existing identities are verified and reused without renewal; changed IP/port, expired certificates or incomplete/modified files fail with the original files preserved. Submit the saved diagnostics/alliance-transport text and JSON reports; do not send the identity directory. This does not establish native game account support, LAN reachability or database readiness. Existing guest gameplay remains unchanged.


Latest Windows identity result (reported2026-10-20): the corrected fixture reuses the existing identity and passes TLS1.2/TLS1.3 encrypted round trips plus wrong-IP, untrusted-certificate and plaintext rejection. Saved report stem: alliance-transport-20261019-165349-386-09cf43f88ef94e64a4314f0021d642a4. Only console text was returned; raw reports and WAN-disconnection status were not supplied. No repeated Python fixture is needed.

## Native connection component handoff

Client `alliance_native/transport.hpp/.cpp` is a new reusable component, outside the pinned upstream engine. It validates a typed trusted public profile, accepts only native TLS preamble1 followed by0, verifies the numeric-IP certificate and exact DER pin with an isolated trust store, and permits framed application bytes only after verification. It does not discover/trust arbitrary remote profiles, follow redirects or reconnect in plaintext.

Its worker-thread API separates connect/send/receive, supports server-push frames, has no outgoing queue, bounds compressed frames to64KiB, and supports monotonic deadlines/cancellation. It does not decompress or interpret WML. Future callers must bound decompression and validate account message schemas. Operations are serialized, accept at most10seconds and close on timeout; future UI integration must provide a network worker and deliberate idle/reconnect behavior. This is an account transport component, not a replacement for the full game relay or its large scenario payloads.

`Test-WindowsAllianceNative.ps1` builds two C++ files into a new owned directory with existing MINGW64 dependencies and runs24 real native checks through `test_alliance_native.py`. It reads the existing public profile only; original private identity and MongoDB runtime remain untouched. Disposable test identities are created in a separate restricted fixture directory. Reports contain version/case/phase/error metadata, not keys or account payloads. Both success and failure preserve reports and build state. This Windows native check is complete; retain its reports. NEXT_TEST.md now covers the separate local administrator persistence milestone.

Actual Windows native component acceptance is complete; LDPlayer execution of that component remains pending. No changed APK/menu is delivered yet. Trusted profile import, selection of this component by Alliance login/team screens, the backend bridge and administrator saved-change/restart acceptance remain unchecked integration tasks.
