# Offline Wesnoth initial baseline

Audit date: 2026-10-11, user timezone Europe/Berlin. **The initial supplied client/server copies cannot build or run because their implementation files are empty.** Inspect the Windows originals and recover them if intact; collect environment versions before selecting a toolchain or reconstructing custom code. This audit covers source/build entry points, artifact integrity, repository state, dependency metadata and upstream integration; gameplay remains untested.

## Supplied files before audit additions

Counts exclude `.git` and precede the documentation/diagnostics added by this audit.

| Item | Finding |
| --- | --- |
| Client | 148,964 files; 143,605 empty. `src` contains 1,362 files; only two small nonimplementation files are nonempty. `SConstruct`, Gradle configuration/wrapper, Java activities and Windows build scripts are empty. |
| Client outputs | All 244 JNI `.so` files and all 8 APK files are empty; no OBB found. |
| Server | 287 files; 282 empty; total nonempty contents 229 bytes. C++ implementation, `SConstruct`, and `wesnothd.exe` are empty. |
| Git repositories | Each initially tracks only `README.md`; GitHub `main` matches the respective local initial commit. Source files are untracked, so Git history cannot recover them. Client initial commit `eefb439b61ea41c824179e3e32e79594578d5c98`; server `5e2efb79868ff1ee2e251011636f4fb66310f460`. |
| Game data | 26,748 files, 26,735 nonempty, 726,207,542 bytes. Manifest declares core 1.19.26 and music 1.19.18. `status.properties` declares `manual_install=true`. This establishes presence and metadata, not full runtime validity. |
| Public source reference | Intact local `wesnoth` at `ff703ca0919`, described as `1.19.28-38-gff703ca0919` and version `1.19.28+dev`. Tag `1.19.26` is available locally. Do not substitute current master for the custom projects. |
| MSYS2 archive | `msys64.rar`, 1,871,513,389 bytes. Archive listing reports 116,758 files, 116,619 nonempty, 5,339,213,426 uncompressed bytes and 338 package entries. Notes specify `D:\Test\msys64`. |

The archive can be listed by VPS 7-Zip 23.01, but its test exits 2 with unsupported-method errors. Its integrity/extraction is therefore unverified with that decoder; this is not proof of corruption.

## Environment evidence

The VPS runs Ubuntu 24.04.5 LTS, kernel 6.8.0-146-generic, x86_64; Git 2.43.0 and Python 3.12.3 are available. At the initial audit, C/C++ compilers, CMake, Ninja, Java, SCons, ADB and MongoDB binaries were absent from PATH. The copied Windows `.venv` is not a working Linux build environment. No Android runtime test is available on this VPS.

The user reports Windows 11, MSYS2 at `D:\Test\msys64`, and LDPlayer running. The workspace parent is `D:\Test\wesnoth-setup`, containing `wesnoth_client` and `wesnoth_server`. Their first actual Windows report confirms:

| Windows component | Reported value |
| --- | --- |
| Operating system | Microsoft Windows 11 Pro, 10.0.22000, build 22000, 64-bit |
| Windows PowerShell | 5.1.22000.2538, 64-bit process |
| Git for Windows | 2.53.0.windows.2 at `C:\Program Files\Git\cmd\git.exe` |
| MSYS2 Git | 2.55.0 at `D:\Test\msys64\usr\bin\git.exe` |

The report jumped from Git results to the final summary without Java, source, MSYS2 package, Android, emulator or MongoDB results. The user subsequently confirmed that they pressed Ctrl+C or stopped it. Its zero BLOCKED/UNKNOWN counts do **not** establish a complete inventory. Those remaining versions and source integrity still await an uninterrupted report. Do not upgrade or install a proposed toolchain based on this partial run.

Archived MSYS2 package metadata lists MINGW64/UCRT64 GCC 16.2.0-3, MINGW64 Boost 1.91.0-3, MSYS GCC 15.3.0-1, MSYS Python 3.12.13-1, UCRT64 Python 3.14.7-1, Git 2.55.0-1, OpenSSL 3.6.3-1, make 4.4.1-3, Ninja 1.13.2-1, Meson 1.12.0-1 and MSYS runtime 3.6.10-3. These are archive labels, not verified active tool versions. SCons/CMake/JDK/Android tools were not found in that archive inventory and may be installed separately.

The surviving custom-client requirement is only `scons>=4.5.0`. Copied environment directory names suggest SCons 4.11.0, and dependency archive filenames suggest Boost 1.88.0 and SDL3 3.4.2; neither proves a working installation. The differing Boost versions need investigation.

## Upstream reference versus intended behavior

[Upstream 1.19.26 Android Gradle configuration](https://github.com/wesnoth/wesnoth/blob/1.19.26/packaging/android/app/build.gradle) declares compile/target SDK 35, minimum SDK 23 and NDK 26.3.11579264. The tag's other build files declare AGP 8.7.0 and Gradle 8.11.1. Its native `build-sources` script defaults to NDK 23.1.7779620 and calls a Linux-specific `llvm-strip` path. These are **reference values**, not confirmed requirements of the missing custom Windows build.

The populated reference Android code imports ZIP game data into its external-files `gamedata` directory and uses `manual_install=true` to bypass downloading. No OBB loader was found in that Android code. The intended OBB workflow requires recovering or implementing the custom loader and determining the package ID, versionCode and asset layout. Merely renaming an archive to `.obb` does not prove integration.

The stock client/server use Wesnoth's native TCP protocol, normally port 15000, with a four-byte handshake and length-prefixed compressed WML. A replacement HTTP/JSON server would not automatically work with this client.

[Upstream 1.19.26 database code](https://github.com/wesnoth/wesnoth/blob/1.19.26/src/server/common/dbconn.hpp) uses optional MariaDB/MySQL integration. MongoDB is the user's intended database, but no surviving custom code implements it or reads `.env`. The existing `.env` has key `DB` containing an SRV-style MongoDB URI with a non-loopback destination; values are intentionally omitted. That configuration does not establish a local offline database. Decide the local MongoDB configuration after confirming the Windows installation. Stock guest LAN play without a database can be an earlier checkpoint; MongoDB persistence remains a separate required integration.

## Repository handling

Initial Git remote URLs contain an embedded access token. Never print raw remotes; rotate the exposed credential and use secure Git authentication. This audit adds `.gitignore` rules to prevent accidental inclusion of `.env`, credentials, reports and generated outputs. It does not publish the empty source trees. Existing source files remain untouched for recovery/comparison.

## Current milestone and next actions

Status: **MSYS2 Git delivery and full Windows inventory verified; source recovery/build setup pending**. Both Windows pulls succeeded and collector version 2026-10-11.2 completed 10/10 sections with exit 0. The user's immediate request is an explanation of the earlier pull failures before proceeding with the next development step. No game build, server launch, APK installation, MongoDB connection or first play is verified.

User clarification on 2026-10-11: Windows will temporarily connect to GitHub to pull updates. GitHub clone/pull is the confirmed normal delivery route; gameplay and offline builds still must work disconnected. The user has not confirmed that intact source exists on Windows. Current GitHub contents provide documentation and diagnostics, not a recovered game implementation.

Latest clarification: the user confirms both repositories are already cloned under `D:\Test\wesnoth-setup` and can see `wesnoth_server\diagnostics`. Use the existing server checkout for its update and diagnostic rerun. This supersedes earlier uncertainty about the copied folders' Git metadata and the proposed separate diagnostics checkout. The existence of the report directory does not establish inventory completion or source integrity.

1. Explain the confirmed local sharing conflict and why MSYS2 Git is a working delivery route, as requested before the next development step. Use the existing MSYS2 Bash/Git command in `WORKFLOW.md` for future Windows pulls. Both updates and the full inventory are now confirmed; do not request another identical run or claim the unidentified background service has been repaired.
2. Use the returned Windows report below for subsequent source/environment planning. The inspected Windows client/server source and build outputs are also empty. Preserve unrelated local README changes and originals; use any independent intact backup if subsequently supplied. The update transfer method is already confirmed.
3. Recover complete custom client/server source if available, excluding secrets/generated artifacts. Compare key sizes/hashes; commit the actual implementation only after review. If originals are unavailable or also empty, reconstruct from a matching upstream revision within the user's authorized project scope and document new behavior explicitly because custom behavior cannot be inferred from empty files.
4. Record/pin the actual Windows build inputs and prepare matching VPS checks and offline dependency packages.
5. Produce a real server executable and APK; verify asset import, local single-player and LAN gameplay using the acceptance checks in `WORKFLOW.md`. Add and test MongoDB persistence.

Initial checks completed: file-size inventories, Git local/remote baseline comparison, upstream version/config/protocol review, game-data manifest review and MSYS2 archive listing.

Initial diagnostics validation: PowerShell 7.4.6 parser passed using a temporary portable Linux verification tool; Bash syntax and missing-tool behavior passed. The report completed against the real VPS files and correctly identified empty build/source artifacts. Controlled Linux fixtures verified paths with spaces, SDK/NDK metadata, Gradle versions/cache discovery, ready versus offline/unauthorized ADB devices, API/ABI output, report saving and exclusion of credential sentinels. The scripts are ASCII/LF-compatible and Git attributes preserve LF for the shell helper. This verification tool is not a selected project build dependency.

## First Windows report correction

The first real Windows PowerShell 5.1 run reached both Git version probes and saved a partial report. The user confirmed that they pressed Ctrl+C or stopped the run. This explains the early exit; it is not evidence of a Java or Windows installation failure. Controlled Linux PowerShell tests reproduced the reporting flaw: pipeline cancellation can run `finally`, skip `catch`, save a report, and exit zero in the original collector.

Collector version `2026-10-11.2` records its own SHA256, prints the current probe before potentially slow work, guards each inventory section, narrows Java registry discovery to known product/version keys, and tracks all ten sections independently of error counts. A full inventory ends with `Collection COMPLETE: 10/10 sections finished`; a failed or interrupted inventory ends with `Collection INCOMPLETE`, identifies unfinished sections and the last probe, and exits 2. COMPLETE describes inventory coverage only; missing tools or empty source can still be reported as BLOCKED.

The corrected collector completed all ten sections against the real VPS files. `tests/Test-CollectWindowsEnvironment.ps1` passed 116 assertions across helper checks and six isolated process scenarios, including early return, failed sections, injected pipeline interruption and report-save failure. A separate real Ctrl+C test saved INCOMPLETE 2/10 and exited 2. Environment fixtures confirmed Git/SDK discovery still reaches later sections and a Java failure produces INCOMPLETE 9/10 while the remaining sections run. All these checks used Linux PowerShell 7.4.6. **The corrected collector still needs the user's Windows PowerShell 5.1 rerun; full MSYS2, Java, Android, LDPlayer and MongoDB inventory remains pending.**

## Windows Git update failure

The next Windows attempts reached GitHub and received objects, but both repositories failed with `Permission denied`, `failed to write object` and `unpack-objects failed`. Server failures named `.git/objects/3c/5b8ba048292a2d0c653a82b63a1200954960a4` and `.git/objects/55/f35e7bc6a52888fb99d49961e547b7eafc661e`; the client failure named `.git/objects/1a/38d17a9f4e05ee1e2a9b38a23c6bc0bc448308`. The collector command was correctly stopped after the failed pull. No successful Windows update or corrected collector rerun is established.

In the installed Git for Windows version, this error comes from [finalizing a temporary object into its hash filename](https://github.com/git-for-windows/git/blob/v2.53.0.windows.2/object-file.c#L626-L689). Windows access rules or a restrictive file handle are possible causes; the error alone does not prove corruption or identify the cause. Read-only Git object files are normal. Do not delete object files, reset the repository, clear all read-only attributes, disable protection, or create another checkout as a first response.

The access check ran as the same ordinary Windows user who ran Git. It inspected attributes/access rules and tested temporary file creation, rename and deletion in the object directories. Actual Git objects, source files and ACLs were not modified. The code is retained in `WORKFLOW.md` for reference.

The returned report `wesnoth-git-access-20261011-065011.txt` provides the following evidence:

- The inspected directories and existing server object grant Authenticated Users Modify access. Four of the five create/write/rename/delete probes passed.
- The server `objects\55` probe created and wrote its temporary file, but rename failed with "The process cannot access the file because it is being used by another process." This is the documented [Windows sharing-violation message](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-). No cleanup failure was reported.
- Server object `55f35e7...` exists as a 183-byte ReadOnly/Archive file. Server object `3c5b8ba...` and client object `1a38d17...` were absent. This metadata does not verify object integrity and does not warrant deleting objects or clearing attributes.

A file-sharing conflict is now observed independently of Git; the locking process and whether it caused every earlier pull failure remain unknown. Do not grant more permissions or request administrator-mode Git on this evidence. A one-time restart and retry were recommended, but successful updates have not been established. Do not repeatedly reboot, blindly kill processes or disable antivirus.

The next returned retry log fails at server object `.git/objects/c6/c5d903ddb2331e8ce69b20b3be9a5d2c397913` with `Permission denied` and `unpack-objects failed`. The script throws before attempting the client, so this run provides no new client result. The user explicitly reports no matching handles in Resource Monitor when searching for `wesnoth-setup`. The reboot itself was not explicitly confirmed; that does not change the next diagnostic step. A missing live handle does not contradict the earlier sharing violation, since interference may be brief. Next: record one server retry with Process Monitor filtered to its `.git\objects` path, retaining events from all processes and all results; return the displayed events as CSV. Process Monitor needs elevation for tracing, while Git remains in the normal user's PowerShell window. No locking process, repair or successful collector rerun is established yet.

The IDE's open `diagnostics/windows-environment-20261011-011856-959.txt` is an older Linux/VPS collector test using PowerShell 7.4.6 and a deliberately missing MSYS2 path. It is not new Windows inventory evidence; do not substitute its missing-tool results for the user's actual Windows report.

## Process Monitor finding

The user supplied workspace-root `git-objects.CSV`: UTF-8 BOM, 604 events, SHA256 `ffd0435cf7528a8b098cdcfdc697009a3da8c986a169bdf1195e472d22ee67bf`. The raw trace remains a local diagnostic and is not committed. CSV line references below count the header as line 1.

The direct conflicting handle owner is **svchost.exe, PID 15800**. Two sequences show it opening a newly created Git temporary file with **ShareMode: Read, Write**, omitting Delete. Windows requires compatible [delete sharing for rename/delete access](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea).

| CSV line | Time in capture | Event |
| --- | --- | --- |
| 228 | 08:26:50.6595596 | svchost 15800 opens `25\tmp_obj_t7Q84k` without delete sharing. |
| 234, 236 | 08:26:50.6632212 / .6640069 | Git 25144 closes its own write handle, then requests Delete access and receives SHARING VIOLATION. |
| 257, 266, 270 | 08:26:50.6659062 onward | svchost closes the handle; Git obtains Delete access and deletes its failed temporary object. This is cleanup, not a successful fetch. |
| 554, 562 | 08:27:12.3194636 / .3220562 | Same conflict on `f6\tmp_obj_pfWOR9`, with Git 5804. |
| 591, 600, 604 | 08:27:12.3259551 onward | svchost closes; Git can open for Delete and clean up. |
| 530, 534, 537 | 08:27:12.3069810 onward | In a successful comparison, svchost closes `c6\tmp_obj_iKJZwc` before Git requests Delete; Git renames it to the final `c6c5d903...` object. |

The conflicting handles last approximately 6.35 and 6.49 milliseconds, consistent with Resource Monitor missing them. The trace contains nine SHARING VIOLATION events and no ACCESS DENIED result. Git's displayed `Permission denied` therefore obscures the captured sharing conflict. Normal file-mapping statuses such as FILE LOCKED WITH ONLY READERS are not counted as these failures.

`MsMpEng.exe` PID 4176 also maps/queries the files, including in successful sequences, but this CSV does not establish it as the conflicting handle owner. Do not attribute the failure to Defender or add antivirus exclusions from this evidence. `svchost.exe` hosts services; its name alone does not identify the specific service. The next read-only command is recorded in `WORKFLOW.md`. PIDs can change or be reused after exit/restart, so a later PID lookup must correspond to the captured process. No service has been stopped and Windows recovery is not yet verified.

## Tasklist result and temporary update workaround

The user's next command returned `svchost.exe`, PID `15800`, Services `N/A`. This does not identify a hosted service, establish the executable's path or publisher, or justify stopping it. Query only this PID's executable path, command line, creation time and parent PID, plus services whose ProcessId matches. Blank executable details can reflect access restrictions. Compare creation time with the trace before assuming the current PID still refers to the captured process. Do not diagnose malware, Defender or a particular service from `N/A`.

A separate route to resume updates is `git -c fetch.unpackLimit=1 -C <repo> pull --ff-only origin main`. The [installed Git for Windows version's documentation](https://github.com/git-for-windows/git/blob/v2.53.0.windows.2/Documentation/config/fetch.adoc#L29-L38) specifies that received objects at or above this threshold remain in a pack. For nonempty incoming packs this avoids unpacking each new object into the loose-file paths involved in the trace. The setting applies only to the command; it does not change saved repository/global configuration or Windows security settings. Pack, index, reference and worktree operations may still encounter interference, so this is an unverified Windows workaround rather than a service repair.

Verification: an isolated Linux Git 2.43.0 fixture passed 14 checks. The command fast-forwarded HEAD, stored the new commit in a newly received pack with no corresponding loose object, updated expected files, preserved unrelated edits/untracked files, left `.git/config` byte-identical, did not persist the command setting, and passed object-integrity checks. A default-fetch comparison produced loose objects; a conflicting local-edit case correctly blocked the pull and preserved the edit and HEAD. The temporary verification fixture is `/tmp/verify-wesnoth-packed-fetch.py`; no real repository configuration was changed. This verified Git's behavior, not a fix for Windows interference; the actual Windows attempt below failed.

## Packed update failed and process metadata was restricted

The normal-user CIM query returned `ProcessId=15800`, `Name=svchost.exe`, blank ExecutablePath and CommandLine, `ParentProcessId=4152`, and `CreationDate=10/7/2026 1:50:57 AM`. The service query returned no rows. That creation time predates the capture, but executable identity and service ownership remain unresolved. Empty metadata does not establish malware or a particular Windows service.

The server packed update received 52 objects (36.05 KiB), resolved 31 deltas with four local objects, then failed to rename a temporary reverse index to `.git/objects/pack/pack-cff741f5ca80d444cb3d8d7cf7c3f4d5259e13ee.rev`, reporting `Permission denied` and `fetch-pack: invalid index-pack output`. The client was not attempted because the guard stopped the loop. The workaround did not restore updates. This is a different file path from the earlier trace; the latest error alone does not prove which process held this specific pack file.

Next: use Windows PowerShell **Run as administrator** for a targeted read of PID 15800, its currently reported parent, executable metadata/signatures and matching services. Additional privileges may expose the previously hidden [process path](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process). Keep the lookup read-only and Git in a normal-user session. Check creation times for PID reuse, including the parent. If metadata remains unavailable even elevated, use the saved Process Monitor process properties rather than inferring identity. No process, service, ACL, antivirus setting or Git configuration has been changed; the elevated lookup and Windows recovery are pending.

## Elevated result: parent service NetActvity

The user returned `ADMIN: True`. Target PID 15800 resolves to `C:\Windows\SysWOW64\svchost.exe`, with command line containing only that quoted executable path, parent PID 4152 and CreationDate `10/7/2026 1:50:57 AM`. Its file metadata is Microsoft Corporation / Host Process for Windows Services / `10.0.22000.1 (WinBuild.160101.0800)`, and its Authenticode status is Valid with a Microsoft Windows signer. There is still no matching service for PID 15800.

Current parent PID 4152 resolves to the same executable path, metadata and valid signature, has parent PID 968 and CreationDate `10/1/2026 9:09:23 PM`. It maps to a Running service whose Name and DisplayName are both **`NetActvity`**; preserve that exact spelling. The parent's creation time precedes the child's, which supports the reported parent relationship rather than a newly reused PID. The prior helper did not print the parent's command line.

This connects the direct blocking child to a parent hosting NetActvity. It does not yet identify the service implementation, its publisher or purpose, prove that the service caused the child's behavior, or demonstrate a Git repair. A valid signature on the svchost file verifies that file, not all code executing within its process. A focused public search found no authoritative identification of the exact service name; absence of such results is not evidence of malware or legitimacy.

Next: collect the named service's description, configured PathName, account/start mode/stop capability, current host command line, root/Parameters DLL settings, and dependency relationships using the read-only block in `WORKFLOW.md`. Its syntax is checked with Linux PowerShell 7.4.6; actual Windows execution remains pending. Do not prematurely stop/delete the service or kill svchost. If a later temporary service stop is appropriate, check whether the separately running blocking child actually exits and restore the original running state. The packed workaround remains failed, both Windows updates and the complete inventory remain unverified, and game build/run is still blocked.

## Running service with unavailable registration

The user completed the NetActvity configuration check. CIM reports Name/DisplayName `NetActvity`, State Running, PID 4152, AcceptStop True, StartMode Unknown, and blank Description, StartName and PathName. Its process is `C:\Windows\SysWOW64\svchost.exe` with command line `C:\Windows\SysWOW64\svchost.exe -k netsvcs -p` and the unchanged CreationDate `10/1/2026 9:09:23 PM`. Both `HKLM:\SYSTEM\CurrentControlSet\Services\NetActvity` and its Parameters subkey returned `Key not present.`. Get-Service returned Running/CanStop True, blank ServicesDependedOn and empty DependentServices (`{}`). There is no configured DLL path or component publisher in this report.

The mismatch between a running service and absent registration remains unexplained. Do not infer a known malware family, a legitimate Windows service, or that the service is marked for deletion. The normal [DeleteService lifecycle](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-deleteservice) alone does not explain the observed missing key while still Running. CanStop True does not establish that Start-Service could restore it. The earlier possible stop/test/start plan is deferred while registration and purpose remain unresolved; no service or process change is requested.

Next: obtain direct SCM `qc`/`queryex` results and exit codes, up to five retained System event 7045 installation records for the exact service name, and LastBootUpTime with the new read-only block. Native errors distinguish outcomes that CIM's empty fields cannot; historical installation records may identify the original executable configuration. Missing events mean no matching records were found in the retained log, not that the service was never installed. An actual full Windows restart remains unverified. VPS checks cover PowerShell syntax only; native SCM/event execution awaits the user. Both Git pulls, the corrected full environment inventory, source recovery, and game build/run remain unverified.

## Native results and confirmed October 1 boot

The returned native output shows `sc.exe qc NetActvity` failing with exit 2 specifically at `QueryServiceConfig2 (delayed autostart flag)`, reporting that the system cannot find the file specified. This is a configuration-query failure; it does not establish that svchost.exe is missing or identify a missing DLL. `sc.exe queryex NetActvity` succeeds with exit 0: TYPE 10 WIN32_OWN_PROCESS, STATE 4 RUNNING, STOPPABLE, NOT_PAUSABLE, IGNORES_SHUTDOWN, PID 4152, zero service/Win32 exit codes, checkpoint and wait hint zero. No matching installation event was found in the retained System log. The service's identity and registration mismatch remain unexplained.

LastBootUpTime is `10/1/2026 9:09:03 PM`, twenty seconds before the previously reported parent process start. This confirms the current Windows boot predates this troubleshooting; the earlier proposed restart cannot be counted as a completed/failed test. The reported IGNORES_SHUTDOWN flag concerns accepted service controls, not an ability to survive a full Windows restart. See [service control flags](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/ns-winsvc-service_status_process) and [Windows power states](https://learn.microsoft.com/en-us/windows/win32/power/system-power-states).

Next: save work, close applications and use Windows Start → Power → Restart. Then record the new boot time and service status, and retry ordinary guarded `pull --ff-only origin main` in both existing checkouts using normal PowerShell. This is a Windows recovery test, not a guarantee that the service restarts or that Git is fixed. Query error 1060 is an acceptable possible observation; judge recovery by successful Git updates. Only afterward reopen LDPlayer and run the corrected environment collector. The new command blocks pass the Linux PowerShell parser; actual Windows restart, pulls, full inventory, source recovery and gameplay are still pending. Old captured PIDs must not be used for process actions after restart.

## Full restart confirmed; existing MSYS2 Git is the next test

The user returned LastBootUpTime `10/11/2026 9:28:14 AM`. NetActvity is Running under new PID 4172 with the same reported type/control flags and queryex exit 0. The server pull enumerated 82 objects and failed writing `.git/objects/55/eb0340cb3a6018aee02ed2e87cecf41a08bc0b`, followed by `failed to write object`/`unpack-objects failed`. The guard stopped before the client update and collector. A full restart has now been tested and did not restore updates. The new failure was not traced: do not identify PID 4172 as the direct locker or reuse old PID 15800. The prompt's current directory alone does not establish whether PowerShell was elevated.

Primary-source review found a concrete implementation difference: [Git for Windows 2.53.0.windows.2](https://github.com/git-for-windows/git/blob/v2.53.0.windows.2/compat/mingw.c#L2970-L2978) returns immediately if opening the rename source with DELETE access fails. The [MSYS2 runtime](https://github.com/msys2/msys2-runtime/blob/cf8cb2aaf2102d0e8ca382790970b2b2ded0680b/winsup/cygwin/syscalls.cc#L2632-L2650) waits and retries STATUS_SHARING_VIOLATION on that source-open operation. [MSYS2 documents](https://www.msys2.org/docs/git/) distinct runtime-based and native Git packages. The existing usr/bin Git was previously reported as 2.55.0; this makes it a targeted alternative for the earlier roughly six-millisecond conflicts, without installing tools or changing service settings. Actual runtime version and Windows behavior remain to be observed; no successful workaround is claimed.

Next: in normal PowerShell invoke the existing MSYS2 Bash without startup profiles, explicitly select /usr/bin/git, print Git/runtime versions and try guarded ordinary fast-forward pulls of the same two checkouts. The PATH prefix is limited to each child process. Stop on any failure, including different authentication/helper behavior. After both succeed, reopen LDPlayer and run the unchanged corrected collector. The new PowerShell/Bash snippets pass syntax checks on the VPS; Windows pulls, full inventory, source recovery and game runtime remain unverified. Preserve the unexplained service for further investigation; a successful alternate-Git pull would not establish its identity or resolve normal native-Git behavior.

## Successful Windows delivery and complete inventory

The user's attachment `d04aeaf9-e801-40db-9978-f01fb5c744a9/Pasted text.txt` confirms MSYS2 Git 2.55.0 with runtime `3.6.10-8fbd9808.x86_64` completed both ordinary fast-forward pulls in the existing checkouts. Server advanced e1112b9 → ebfb18df282ced1ba1f5322635460456e5ec3d63 (82 received objects); client advanced 8183d41 → f35d0af04945f9395505015026ee776b1e83f43a (78 objects). Both retain modified README.md files. Preserve those changes. This establishes the MSYS2 update route on the user's Windows machine; use it for subsequent Windows pulls.

The following collector ran at `2026-10-11 09:46:24 -06:00`, version `2026-10-11.2`, and ended `Collection COMPLETE: 10/10 sections finished`, exit 0. Report: `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\windows-environment-20261011-094624-248.txt`. Its script SHA256 `901900b60799da397217391f9704db30b3522531840c0afbaa357f91ac00890e` matches the VPS file. Top-level totals are 27 BLOCKED and 10 UNKNOWN; MSYS2 helper lines contain additional findings. Completion establishes coverage, not build readiness. The raw attachment is not committed.

| Windows evidence | Confirmed result |
| --- | --- |
| OS and PowerShell | Windows 11 Pro 10.0.22000, 64-bit; PowerShell 5.1.22000.2538. |
| Java | Android Studio JBR java/javac both run as 21.0.9. |
| Python and SCons | Windows Python 3.14.3, MSYS Python 3.12.13 and UCRT Python 3.14.7 run; SCons is absent from tested installations. Copied client venv launchers are zero bytes. |
| Native tools | Windows CMake 4.3.0 and Strawberry CMake 3.29.2; Strawberry Ninja 1.12.0. MSYS GCC/G++ 15.3.0 and make 4.4.1; MINGW64 and UCRT64 GCC/G++ 16.2.0; MSYS/UCRT Ninja 1.13.2. |
| MSYS2 packages | Local pacman inventory completed, including runtime 3.6.10-3, MINGW64 Boost 1.91.0-3 and UCRT SDL3 3.4.14-1. Package presence does not establish project compatibility. |
| SDK metadata | APIs 34/35/36; build-tools 33.0.1, 34.0.0, 35.0.0, 36.1.0; command-line tools 20.0; SDK CMake 4.1.2; NDK 30.0.14904198-beta1. These component versions come from source.properties, not a build. |
| Gradle metadata | Wrapper directories 8.9 and 9.3.1; cached AGP 8.7.3; 75 cached dependency groups. Gradle was not executed; offline completeness remains unverified. |
| LDPlayer / ADB | LDPlayer 9.5.3.0 registration/files identified; SDK ADB 1.0.41 / 37.0.0-14910828 runs. Device enumeration failed connecting to 127.0.0.1:5037; no Android API/ABI or ready device was established. |
| MongoDB | Server/shell executables and service not located; running mongod count zero. No database connection attempted. |

Windows source inspection confirms client src 1,306/1,306 files empty and server src 128/128 empty. Both SConstruct files are empty. Client outputs include 16 EXEs, 8 APKs and 1,778 SOs, all empty; server has 20 empty EXEs. No OBB was found. Key Android build scripts, InitActivity.java, wesnoth.cpp and Gradle declarations/wrapper properties are empty. No upstream wesnoth or gamedata-1.19.26 directories were found at the inspected Windows workspace paths. These results rule out those inspected copies as intact custom-source backups; they do not establish whether an independent backup exists elsewhere. This source issue predates and is separate from the Git locking failure.

Interpretation limits for later work: WindowsApps Python entries may be legitimate zero-byte app-execution aliases, so the collector's BLOCKED labels there do not establish a broken Python installation; the real interpreter runs. The ADB probe explicitly selected host 127.0.0.1/port 5037 and reported it could not start a server on a remote host; this does not prove LDPlayer was closed or broken. Inspect that probe before drawing an emulator conclusion. No collector fixes, source reconstruction or toolchain changes are started in this turn because the user asks for the Git explanation first.

Explanation to retain: GitHub communication/download succeeded; the old Process Monitor capture proves a local sharing conflict at temporary-object finalization. PID 15800 held handles without delete sharing for roughly six milliseconds. The native Git path returned an error immediately at the blocked source-open operation, producing Permission denied. MSYS2 has retry handling for this class of conflict, and the successful update is consistent with that difference. The successful run was not traced, so do not claim an observed internal retry or that changing the version number alone fixed it. The captured blocking process's parent hosted NetActvity, but its implementation/purpose and continued interference remain unresolved. The achieved result is working delivery through MSYS2 plus a complete inventory, not removal of the background software or a successful game build.
