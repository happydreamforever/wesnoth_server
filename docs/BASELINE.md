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

Status: **environment/source recovery pending**. No game build, server launch, APK installation, MongoDB connection or first play is verified.

User clarification on 2026-10-11: Windows will temporarily connect to GitHub to pull updates. GitHub clone/pull is the confirmed normal delivery route; gameplay and offline builds still must work disconnected. The user has not confirmed that intact source exists on Windows. Current GitHub contents provide documentation and diagnostics, not a recovered game implementation.

Latest clarification: the user confirms both repositories are already cloned under `D:\Test\wesnoth-setup` and can see `wesnoth_server\diagnostics`. Use the existing server checkout for its update and diagnostic rerun. This supersedes earlier uncertainty about the copied folders' Git metadata and the proposed separate diagnostics checkout. The existence of the report directory does not establish inventory completion or source integrity.

1. Resolve the Windows Git sharing violation recorded below. The access check is complete: four probes passed and the server `objects\55` rename was blocked by another process. Save work, restart Windows once, and retry both existing clones with `--ff-only origin main` before reopening editors/Git GUI clients. If a pull fails again, identify open handles as described in `WORKFLOW.md`. After successful pulls, start LDPlayer and run the server collector with `-WorkspaceRoot D:\Test\wesnoth-setup -MsysRoot D:\Test\msys64`. Confirm collector version `2026-10-11.2` and return the latest report, even if incomplete.
2. Return the report to establish whether Windows originals have real content and identify installed tools. Preserve any originals before a pull that might collide with untracked files. The update transfer method is already confirmed.
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

A file-sharing conflict is now observed independently of Git; the locking process and whether it caused every earlier pull failure remain unknown. Do not grant more permissions or request administrator-mode Git on this evidence. Next attempt: save work and restart Windows once, then retry both pulls as the normal user with editors/Git GUI clients closed. A repeat failure requires process identification using Resource Monitor; short-lived locks may require a Process Monitor capture. Do not repeatedly reboot, blindly kill processes or disable antivirus. A restart/retry, successful pulls and the corrected environment collector are all still unverified on Windows.
