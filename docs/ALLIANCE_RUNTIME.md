# Alliance accounts, teams, battle planning and local service runtime

This delivery implements the persistent game rules, a local operator website and the Android account update. The user confirms the updated APK, public-profile sequence and first UniPlayer registration with WAN disconnected. UniPlayer registration, wrong-password rejection, login, leader retrieval and explicit server logout/relogin are accepted with WAN disconnected by user report. Graceful app restart, retained server profile and fresh login also pass with WAN disconnected by user report. The expected service-unavailable error and same-player recovery without login pass after bridge restart. Fresh login and the same stored player/leader also pass after all three backend processes restart, with WAN disconnected by user report. Remaining runtime acceptance is in [the implementation checklist](ALLIANCE_IMPLEMENTATION.md); playable custom campaigns and Alliance Battle are later milestones. Continue using LDPlayer only.

Local MongoDB setup is complete at the accepted scope. We use **MongoDB Community Edition8.0.32**, the free self-managed edition that can run offline ([official overview](https://www.mongodb.com/products/self-managed/community-edition)). The pinned portable MongoDB and17 Python packages already passed Windows installation. Reuse them. The previous failure was database startup, not a missing paid product or installer.

**Current battle-planning batch, APK 1192606 (2026-10-21):** The user confirms all management checks A–H on installed 1192605 with WAN disconnected. Accept rankings, safe cancellation, captain transfer, departure/rejoin, fresh rejection with Back preserving unread, later Read history, restored Koichi captain UniPlayer/member UniRecruit at 2/8, unchanged progression and separate last-member archival at user-observed scope. The final full-service restart was not explicitly confirmed; membership/history persistence through that final restart remains pending. Earlier Windows 1192605 build/install and admin/bridge readiness logs remain accepted. Do not repeat A–H or treat their confirmation as a process/network trace.

The next cohesive delivery is battle planning: approved 2v2/3v3/4v4 maps, same-area opponents, exact ordered lineups with saved leader snapshots, separate explicit approvals by BOTH current captains, selected-player ready/unready and current-captain cancellation of a draft, including a stale draft. A new proposal has no approvals or ready players; one draft per involved team is permitted. Planning does not start a game, reserve active_run locks, award XP or alter rating. Existing campaign/combat/reward integration remains later work. Preserve Koichi ID 4cd736d3-dc6c-4c3d-a816-e7682b56db30, Yama reference fb010e4d-af74-4906-8ba6-5f096aaf90ec, original players, profile runtime/identity, trusted server, OBB and every foundation/backup.

Android delivery helpers target 1192606 from completed 1192605 using .wesnoth-account-game-update-1192606.json and unique before-battle-planning-ui backups; all four older journals/backups remain retained. KeepSavedProfile accepts installed 1192605/1192606 and verifies 1192606 without profile import, OBB transfer or data clearing. All 39 builder tests and 21 PowerShell simulations pass, and the pre-build audit preserves 17,731 foundation files, 1,391 account/backup files and ten directory trees. Server validation passes 59 real MongoDB/domain, 36 HTTP, seven authentication and 34 native TLS bridge tests with networking disabled. Four prior full native flows and the new four-player planning flow pass, including exact ready-draft persistence through full-stack restart and no XP/locks/settlements. Final client verification passes 10 new battle TLS and 40 existing TLS cases, five battle UI and five management UI source contracts, five protocol marker groups, all seven host probe targets and the three-map proposal encoding check. The actual network-disabled1192606 APK build and standalone signature/receipt/version verification pass: six native steps and33 Gradle tasks. The returned Windows report now confirms the1192606 bridge rebuild, six native Android steps,33 Gradle offline tasks, APK/signature verification, in-place installation and setup activity startup. Two subsequent bridge launches stop at stage=backend-health before listener bind. The07:28:39 diagnostic found neither required endpoint listening and connection_refused; the user has now returned MongoDB running127.0.0.1:27018, the authenticated replica-set/schema/administrator/transaction-rollback checks passing, admin URL127.0.0.1:18765 and bridge READY100.99.99.14:15001. Accept current service startup recovery without attributing why the earlier services were absent. The user now reports Invalid username or password for all attempted accounts and explicitly confirms main menu -> Alliance -> Log in; the most recent individual username was not specified. Pause planning A–H and repeated player login attempts. Source comparison finds credential capture/login and server auth/config/schema/deployment unchanged from1192605; three focused native tests pass. The error can also represent internal backend authorization rejection, so do not diagnose a password typo or lost data from it. Next inspect the existing Windows admin Accounts page for UniPlayer/UniRecruit role/status and run the existing authenticated backend-health diagnostic. Use administrator Uni only for the website; never request passwords, stored hashes, private runtime files or request bodies. Keep all services and accounts unchanged; no reset, registration, initialization, rebuild or reinstall. WAN status and planning UI acceptance remain unreported. See BASELINE.md for evidence and NEXT_TEST.md for the focused login checks.


| Stage | Current state |
| --- | --- |
| Download pinned MongoDB and Python wheels while connected | Complete on Windows; cache retained |
| Install from the local cache | Complete on Windows; installation itself was performed while internet remained available |
| Verify MongoDB startup and clean-restart persistence | Complete on Windows under LOCALAPPDATA; user confirms WAN disconnected and local Ethernet connected |
| Initialize the authenticated game replica set, schema and administrator | Complete on Windows; username Uni; selected profile runtime; internet access was available during initialization |
| Start database and local admin website; check transactions and login | Complete on Windows; console checks pass; browser login/Area 1/WAN disconnection user-confirmed |
| Verify database and website restart | Re-launches succeed in returned Windows output; user confirms WAN disconnected. Recovery-helper backup report and shutdown exit codes not supplied |
| Create an area, check audit and sign-out, verify records after restart | Passed by user report: same area name, matching audit identifier, login required after sign-out; WAN disconnected during restarts |
| Native Android transport fixture | Windows build and 22 LDPlayer loopback cases pass; later device-only rerun also passes with WAN disconnected by corrected user report |
| Connect Android accounts | Registration, password rejection, login/profile, server logout/relogin and app restart accepted with WAN disconnected by user report; bridge outage/recovery accepted with WAN disconnected; player persistence after all three backend processes restart accepted with WAN disconnected by user report |
| First team UI | Windows bridge and Android 1192602 accepted; LDPlayer initial no-team lookup, Koichi creation in Yama and separate My team retrieval pass with WAN disconnected by user confirmation. Yama directory lookup and unchanged personal XP also accepted; controlled team restart persistence accepted with WAN disconnected by user report |
| Team membership and decisions UI | APK1192603 application/withdrawal/rejection and1192604 approval, unread detail, matching Koichi2/8, Read history, empty pending list and unchanged personal XP are accepted at user-observed scope.1192604 Windows build/install and retained trusted server are accepted. Fresh rejection/Back-unread behavior now passes in the user-confirmed offline1192605 A–H sequence; the final membership/history restart was not explicitly confirmed. |
| Team management UI1192605 | Windows build/install/startup and all A–H management checks are accepted with WAN disconnected by user report. Koichi is restored to UniPlayer captain/UniRecruit member2/8 with unchanged XP; the separate test team was archived. The final full-service restart remains unconfirmed. |
| Battle planning UI1192606 | Seven bounded operations add approved map catalog, private list/detail, exact lineups, two explicit captain approvals, selected-player ready/unready and draft cancellation. No gameplay start, active-run reservation or rewards are exposed. Server/native tests and the actual offline1192606 APK/signature/receipt verification pass on the VPS. Actual Windows1192606 build/install/setup startup pass; current MongoDB/admin/bridge startup recovery also passes in returned output. Player login is now reported rejected for all attempted accounts; planning A–H is paused for read-only account/status and backend-health checks. |
| Connect progression and Alliance Battle | Pending gameplay integration |

The final database binds to127.0.0.1:27018 and the administrator website to127.0.0.1:18765. The Windows game service will use the database locally; Android clients will communicate with the game service. The internet database URL in `.env` is not used.

## What is implemented

- Accounts with Argon2id password hashes, scoped sessions, explicit expiry, logout/revocation and login throttling.
- One persistent leader with the actual 1.19.26 advancement choices and XP thresholds. Permanent leader snapshots cannot change after captains approve a battle proposal.
- Eight-member teams, membership applications and rejection/withdrawal, captain transfer, areas and area standings.
- Campaign progression records and fixed 2v2/3v3/4v4 battle proposals, mutual captain approval, readiness and atomic start reservations.
- Transactional leader/team XP and rating settlement, duplicate-result protection, conflicting-result rejection and audited cancellation.
- Admin login and views for accounts, teams, areas, runs, rewards and audit history. Admins can suspend/reactivate players, create areas, move inactive teams and cancel interrupted runs with a reason.

Only a trusted local native-server bridge can eventually submit game results. The account bridge exposes registration, login, profile/logout, five bounded team-directory operations, six authenticated membership operations, two owner-only application-decision operations three team-management/ranking operations and seven battle-planning operations; it cannot start a battle or submit game results. Playable custom missions and battle settlement integration are not delivered yet. The service's health response states `game_bridge_integrated=false` and `campaign_content_ready=false`.

## Account connection delivery (2026-10-20)

The new `alliance-account-bridge.exe` listens on the numeric address/port in the existing `runtime/alliance-transport/public-profile.json` (currently 100.99.99.14:15001). It reads the existing protected runtime's bridge credential locally and talks only to `127.0.0.1:18765`. Neither MongoDB nor the admin website is exposed to the LAN. Start the existing database and admin service first, then `tools/Run-WindowsAllianceBridge.ps1`. Leave those three windows open during the account test. This does not replace guest `wesnothd` on port15000.

The Android update adds a public-profile import screen and an Alliance main-menu entry. Only the public JSON is copied to LDPlayer; private keys/runtime credentials stay on Windows. Compare the printed address/fingerprint and approve it explicitly in the app. Create a separate player account; administrator Uni remains an administrator. Closing the app loses the in-memory session, so log in again. Successful logout revokes the server token. Existing campaigns and guest multiplayer still use their original rules and do not award permanent account XP.

VPS integration uses a new disposable authenticated MongoDB replica set; it does not touch the user's database. Registration, Unicode credentials, duplicate rejection, login/profile/logout and restart persistence pass. The corrected Windows bridge now reports READY on100.99.99.14:15001 after the healthy backend diagnostic. Native startup is accepted; the prior failure cause remains unproven. The returned Windows account APK build now passes six native steps and 33 Gradle tasks, including artifact/signature checks, with internet available by user report. The user confirms installation, the public-profile sequence and the first real UniPlayer registration with WAN disconnected. The created Spearman is level1 with zero experience. The returned Logged in dialog and explicit follow-up answers accept correct login, wrong-password rejection and separate leader retrieval with WAN disconnected. The exact server-revoked logout message and repeat login/leader values are now explicitly confirmed with WAN disconnected. Graceful app restart now retains the trusted profile, requires login and returns the same player/leader with WAN disconnected by user report. The user now confirms the expected bridge-outage error and same-player recovery without another login, with WAN disconnected throughout. The user explicitly confirms stored player persistence after stopping/restarting all three backend processes and fresh game login, with WAN disconnected. Existing runtime, identity and original game stages remain preserved. The current NEXT_TEST.md delivers the1192605 management batch while preserving the existing runtime, completed1192604 account stages and every earlier backup/journal. Follow [NEXT_TEST.md](NEXT_TEST.md) for exact commands and expected results.

## Team management runtime contract — 2026-10-21

Transfer captain checks current captain authority, target membership and active-run restrictions in the existing MongoDB transaction. The former captain stays on the roster. A suspended target returns forbidden/HTTP403 through the new directory wrapper, preserving the caller's valid login; legacy domain behavior is unchanged. Ordinary departure keeps other members/captain. A captain with other members must transfer first. A sole captain sees explicit archival/cleared-applications consequences before sending leave_team with allow_archive:true; ordinary departure sends false. The expected team and consent are checked within each transaction attempt, so a changed roster cannot turn a normal leave into an unconfirmed archive. Client/bridge require an exact bounded acknowledgement and refuse archived:true without consent.

Area rankings show at most20 active teams, sorted by rating descending and UUID ascending for ties. The existing paged directory remains available for additional teams. No management action changes personal/team XP, rating or the eight-seat capacity. Confirmation menus for approve/reject, transfer and leave start on Back without changes. After success My team refreshes independently; after an uncertain outcome the player reads My team instead of retrying the mutation.

VPS tests pass50 domain,33 HTTP,7 authentication,30 native bridge TLS,40 client TLS responses, five protocol marker groups, five UI contracts,39 builder tests and21 PowerShell simulations. Four native-client/bridge/backend/MongoDB integration suites pass, including final restored original-captain/two-member persistence through restart. These are disposable VPS tests, not Windows/LDPlayer runtime evidence. Actual Android1192605 offline build and standalone artifact/signature verification also pass. Refer to BASELINE.md for artifact hashes, audit paths and final preservation of 17,731 foundation files, 1,388 prior account files and ten directory trees.

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

All website assets are local. Neither the website nor MongoDB binds to the LAN. Android account and team-directory traffic uses the native bridge with the saved provisioned TLS identity. Do not forward these local ports through a router.

## Windows sequence

Follow [NEXT_TEST.md](NEXT_TEST.md) for the current combined team-management acceptance batch. The browser and standalone Android transport acceptance are complete. The launch commands below are references for future sessions, not a request to start duplicate processes. The existing credentials and profile data remain authoritative. Do not initialize again or delete either MongoDB storage locks or operation.guard.

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

Keep both open. Expected: database running on `127.0.0.1:27018`, then the admin URL `http://127.0.0.1:18765/`. Open that URL in the Windows browser and sign in with the administrator created above. Sign in as `Uni`, then view Areas to find Area 1; the guest multiplayer login remains separate from the persistent Alliance player account.

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

The Python, native Windows and standalone Android transport fixtures have passed; do not repeat them for the next account integration milestone in [NEXT_TEST.md](NEXT_TEST.md). `Test-WindowsAllianceTransport.ps1` prepares/reuses a separate `runtime/alliance-transport` identity using installed Python3.14.3 and MINGW64 OpenSSL3.6.3. No MongoDB or native server starts. The private key is restricted to the current Windows account and SYSTEM; only `public-profile.json` is intended for later trusted client provisioning. It contains a public self-signed leaf certificate, canonical server IP, future port15001, minimum TLS1.2 and certificate SHA256. Do not transfer private keys to clients.

The fixture verifies TLS1.2/TLS1.3 payload round trips, wrong-IP rejection, untrusted-certificate rejection and plaintext rejection on loopback only. Existing identities are verified and reused without renewal; changed IP/port, expired certificates or incomplete/modified files fail with the original files preserved. Submit the saved diagnostics/alliance-transport text and JSON reports; do not send the identity directory. This does not establish native game account support, LAN reachability or database readiness. Existing guest gameplay remains unchanged.


Latest Windows identity result (reported2026-10-20): the corrected fixture reuses the existing identity and passes TLS1.2/TLS1.3 encrypted round trips plus wrong-IP, untrusted-certificate and plaintext rejection. Saved report stem: alliance-transport-20261019-165349-386-09cf43f88ef94e64a4314f0021d642a4. Only console text was returned; raw reports and WAN-disconnection status were not supplied. No repeated Python fixture is needed.

## Native connection component handoff

Client `alliance_native/transport.hpp/.cpp` is a new reusable component, outside the pinned upstream engine. It validates a typed trusted public profile, accepts only native TLS preamble1 followed by0, verifies the numeric-IP certificate and exact DER pin with an isolated trust store, and permits framed application bytes only after verification. It does not discover/trust arbitrary remote profiles, follow redirects or reconnect in plaintext.

Its worker-thread API separates connect/send/receive, supports server-push frames, has no outgoing queue, bounds compressed frames to64KiB, and supports monotonic deadlines/cancellation. It does not decompress or interpret WML. Future callers must bound decompression and validate account message schemas. Operations are serialized, accept at most10seconds and close on timeout; future UI integration must provide a network worker and deliberate idle/reconnect behavior. This is an account transport component, not a replacement for the full game relay or its large scenario payloads.

`Test-WindowsAllianceNative.ps1` builds two C++ files into a new owned directory with existing MINGW64 dependencies and runs24 real native checks through `test_alliance_native.py`. It reads the existing public profile only; original private identity and MongoDB runtime remain untouched. Disposable test identities are created in a separate restricted fixture directory. Reports contain version/case/phase/error metadata, not keys or account payloads. Both success and failure preserve reports and build state. This Windows native check is complete; retain its reports. NEXT_TEST.md now covers the next account integration milestone.

Actual Windows native component and standalone LDPlayer execution acceptance are complete, including WAN-disconnected device execution by corrected user report. Administrator saved-change/restart acceptance is also complete. No changed APK/menu is delivered by these fixtures. Trusted profile import, the backend bridge and Alliance login are now integrated and accepted. The first team screens use this same transport; creation, My team, directory and personal-leader comparisons are accepted in LDPlayer. Team restart persistence remains pending.
