# Offline Wesnoth development workflow

The project is a custom Android game client with a Windows 11 server on a local network, using Wesnoth as its starting point and MongoDB as the intended database. Development takes place on the Linux VPS. The user builds and runs the Windows server and Android app on Windows, with LDPlayer first and an Android phone afterward. Gameplay must work without internet access.

## Persistent project context

This workflow records the user's instructions from 2026-10-11. `AGENTS.md` tells future coding sessions to read this file and `BASELINE.md`. Keep both documents in the client and server repositories. Update facts and test results as work progresses; retain the user's workflow unless the user changes it. Repository files provide continuity when chat context is unavailable.

| Directory | Purpose |
| --- | --- |
| `wesnoth_client` | Custom Android client and Windows Android build scripts |
| `wesnoth_server` | Custom Windows server and intended MongoDB integration |
| `wesnoth` | Public upstream source reference; record the exact tag/commit before copying code |
| `msys2-full` | Supplied MSYS2 archive; Windows notes specify `D:\Test\msys64` |
| `gamedata-1.19.26` | Initial data intended for offline Android packaging, potentially OBB |

## Every development cycle

1. Read the current baseline and the latest Windows report. Inspect Git status and preserve unrelated changes.
2. Make the smallest complete change toward the current milestone. Keep client protocol, server protocol, native libraries and game data compatible.
3. Run meaningful available checks on the VPS. Identify separately what needs Windows, LDPlayer, a physical phone, or MongoDB. A Linux build does not establish Windows or Android runtime success.
4. Review and stage explicit files. Never stage credentials, `.env`, private keys, signing stores, reports, generated binaries, dependency caches, or incomplete placeholder source accidentally.
5. Commit and push the changed repositories to their configured GitHub remotes. The user has authorized this cycle. Report the actual branch and commit IDs, and say explicitly if a push fails. Do not force-push or overwrite user work.
6. Give the user exact transfer/pull, build, run and test commands with the working directory, shell, selected device/ABI and required paths. Include expected visible results and log filenames. If the current delivery is diagnostic-only, say that game build/run is blocked rather than supplying an unverified success command.
7. The user tests on Windows and returns results/logs. Compare observed and expected behavior, update the baseline and continue with the next fix. Ask focused questions whenever missing information matters.

## Version matching and offline operation

Inventory Windows before selecting or upgrading tool versions. Record the active MSYS2 environment, compiler/dependencies, Python/SCons, JDK, Gradle/AGP, Android SDK/NDK/build-tools, LDPlayer Android API/ABI, MongoDB server/shell and Git versions. Pin supported versions after reviewing the report. Maintain separate Linux and Windows host tools where required; matching project/toolchain inputs is possible, identical operating systems and executable binaries are not.

Do not infer an installed version from a directory or archive filename alone. Test the actual selected tools. Keep MINGW64 and UCRT64 runtimes/dependencies consistent. Record exact source/data revisions and APK package ID, versionCode, versionName and ABI once recovered.

Offline builds need the pinned dependencies and Gradle artifacts already cached locally. Prepare missing installers, archives, checksums, Gradle dependencies and package metadata on a connected computer before moving them to Windows. Never run package upgrades or download-dependent commands as part of offline testing. Use Gradle `--offline` when the build is ready and verify that native dependency scripts also avoid downloads.

GitHub pull requires connectivity. If Windows is permanently disconnected, transfer Git bundles or source archives using USB or an approved LAN computer. Confirm which route the user uses. For a Git bundle, record the source commit, transfer the bundle, verify it, and import with Git; do not treat a copied folder as a verified revision. Subsequent clean worktrees can use `git pull --ff-only` against their accessible remote. Never erase uncommitted Windows source to make a pull succeed.

## First environment check

The initial source copies are incomplete. Preserve the Windows originals. Obtain the diagnostics tools using a **new checkout in a separate directory**, or copy the tools from this repository; do not pull over the original client/server folders yet. Newly tracked files could collide with the user's untracked files.

If Windows can access GitHub, run in PowerShell, replacing `D:\Test` if needed:

```powershell
Set-Location D:\Test
git clone https://github.com/happydreamforever/wesnoth_server.git wesnoth-setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\wesnoth-setup\tools\Collect-WindowsEnvironment.ps1 -WorkspaceRoot D:\Test -MsysRoot D:\Test\msys64
```

`WorkspaceRoot` must contain the existing `wesnoth_client` and `wesnoth_server` folders. If GitHub is unavailable on Windows, transfer the new checkout or its `tools` directory from a connected computer, then run the same script with its actual path. `ExecutionPolicy Bypass` applies only to this PowerShell process.

This handoff also includes a self-contained `wesnoth_server.bundle` for offline transfer. After placing it on a USB drive (for example `E:\transfer`), use a fresh destination:

```powershell
Set-Location D:\Test
git clone E:\transfer\wesnoth_server.bundle wesnoth-setup
git -C .\wesnoth-setup bundle verify E:\transfer\wesnoth_server.bundle
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\wesnoth-setup\tools\Collect-WindowsEnvironment.ps1 -WorkspaceRoot D:\Test -MsysRoot D:\Test\msys64
```

Choose one of the two clone routes; do not clone twice into the same directory. A bundle clone's `origin` points to that bundle, so subsequent updates must use newly transferred bundles or an explicitly configured accessible GitHub remote.

The report is written under `wesnoth-setup\diagnostics` when using the checkout above. It reports missing tools as unknown/blocked, checks source file sizes, and collects installed version information without installing packages, starting the game/server/database, or reading `.env` values. ADB inspection may start its normal local background daemon. Start LDPlayer before the report to include its Android API and ABI. If SDK, emulator or ADB are outside standard locations, pass the optional path parameters documented in the script.

Return the report and explain whether the Windows source is intact and how updates reach Windows. Local filesystem paths and device serials appear in the report; remove those if desired. Do not send `.env`, access tokens, keystores or full environment-variable dumps.

## First play acceptance

The first milestone is complete only when all relevant checks have actual evidence:

- Source files are recovered, tracked and matched to compatible game data. Versions and offline dependency caches are recorded.
- A nonempty Android APK builds on Windows; a nonempty server executable starts with its DLLs. Preserve build logs and exact commit IDs.
- The Android app launches in LDPlayer and reads local game data with internet unavailable. Offline asset import and any OBB support must be implemented and tested before claiming support.
- A local single-player scenario loads and completes at least one turn.
- The server listens on the agreed LAN interface/port. The client reaches the server, enters the lobby, creates/joins a game and completes a turn. Confirm the emulator's route to the Windows host instead of assuming that Android `localhost` is the Windows computer. A phone uses the Windows LAN IP on a reachable local network.
- MongoDB runs locally on Windows and the chosen persistence behavior is exercised after integration. Guest LAN play may be a useful earlier checkpoint, but does not establish MongoDB integration.
- Close/reopen behavior, save/load when supported, and relevant logs are checked. Repeat the offline launch and gameplay checks on the physical Android device.
- At least one complete fix → commit → push → transfer/pull → build → run → report cycle succeeds.

## Test report format

Include the client and server commit IDs; Windows report filename; exact command and shell; selected emulator/device and ABI; expected result; actual result; full relevant build error or server log; and Android logcat around the failure. Record the last successful step. Remove secrets before sharing logs.

Future handoffs should update `BASELINE.md` with confirmed versions, commands that actually ran, results, remaining blockers and the next action.
