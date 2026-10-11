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

The user reports Windows 11, MSYS2 at `D:\Test\msys64`, and LDPlayer running. The workspace parent is `D:\Test\wesnoth-setup`, containing `wesnoth_client` and `wesnoth_server`. Windows build number, MSYS2 package versions, LDPlayer version/API/ABI, MongoDB version and active compiler/JDK/SDK/NDK versions are **awaiting the Windows report**. Do not upgrade or install a proposed toolchain before reviewing that report.

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

Further clarification: the initial Windows client/server folders were downloaded/copied from the VPS, not cloned from GitHub. They reside under `D:\Test\wesnoth-setup`, and whether `.git` was retained is unknown. These copies are not an independent source-recovery backup. LDPlayer is already running. No pull is needed for the initial diagnostic when the copied server contains its `tools` directory.

1. Run `D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1` with `-WorkspaceRoot D:\Test\wesnoth-setup -MsysRoot D:\Test\msys64`, as described in `WORKFLOW.md`. Use the separate fallback checkout only if those diagnostic tools are missing.
2. Return the report to establish whether Windows originals have real content and identify installed tools. Preserve any originals before a pull that might collide with untracked files. The update transfer method is already confirmed.
3. Recover complete custom client/server source if available, excluding secrets/generated artifacts. Compare key sizes/hashes; commit the actual implementation only after review. If originals are unavailable or also empty, reconstruct from a matching upstream revision within the user's authorized project scope and document new behavior explicitly because custom behavior cannot be inferred from empty files.
4. Record/pin the actual Windows build inputs and prepare matching VPS checks and offline dependency packages.
5. Produce a real server executable and APK; verify asset import, local single-player and LAN gameplay using the acceptance checks in `WORKFLOW.md`. Add and test MongoDB persistence.

Initial checks completed: file-size inventories, Git local/remote baseline comparison, upstream version/config/protocol review, game-data manifest review and MSYS2 archive listing.

Diagnostics validation: PowerShell 7.4.6 parser passed using a temporary portable Linux verification tool; Bash syntax and missing-tool behavior passed. The report completed against the real VPS files and correctly identified empty build/source artifacts. Controlled Linux fixtures verified paths with spaces, SDK/NDK metadata, Gradle versions/cache discovery, ready versus offline/unauthorized ADB devices, API/ABI output, report saving and exclusion of credential sentinels. The scripts are ASCII/LF-compatible and Git attributes preserve LF for the shell helper. **Windows PowerShell 5.1, MSYS2 tool execution and real LDPlayer/phone behavior remain unverified.** This verification tool is not a selected project build dependency.
