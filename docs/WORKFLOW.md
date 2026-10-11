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

The user confirmed on 2026-10-11 that Windows temporarily connects to GitHub to pull updates, then returns to offline use. GitHub is the normal delivery route; do not ask the user to choose a transfer method again. Use `git pull --ff-only origin main` in the appropriate clean checkout. Never erase uncommitted Windows source to make a pull succeed. Git bundles remain an optional fallback if connectivity changes.

## First environment check

The user downloaded/copied the initial client and server folders from the VPS to Windows, rather than cloning them. Their confirmed layout is:

| Windows path | Purpose |
| --- | --- |
| `D:\Test\wesnoth-setup` | Workspace parent |
| `D:\Test\wesnoth-setup\wesnoth_client` | Copied client folder |
| `D:\Test\wesnoth-setup\wesnoth_server` | Copied server folder |
| `D:\Test\msys64` | Installed MSYS2 folder |

Keep LDPlayer running. Run the existing diagnostic in Windows PowerShell; no clone or pull is needed for this check:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1" `
  -WorkspaceRoot "D:\Test\wesnoth-setup" `
  -MsysRoot "D:\Test\msys64"
```

The report is written to `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\windows-environment-<timestamp>.txt`. `ExecutionPolicy Bypass` applies only to this PowerShell process. A `.git` directory is not required for diagnostics; Git metadata availability will be reported. The companion `collect-msys2-environment.sh` should be present beside the PowerShell script.

If the copied server folder predates the diagnostic tools, temporarily connect to GitHub and obtain a separate diagnostics checkout at `D:\Test\wesnoth-diagnostics`. This destination is outside the existing workspace:

```powershell
git clone --branch main https://github.com/happydreamforever/wesnoth_server.git D:\Test\wesnoth-diagnostics
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\Test\wesnoth-diagnostics\tools\Collect-WindowsEnvironment.ps1" `
  -WorkspaceRoot "D:\Test\wesnoth-setup" `
  -MsysRoot "D:\Test\msys64"
```

If that separate GitHub checkout already exists, update it with `git -C D:\Test\wesnoth-diagnostics pull --ff-only origin main` instead of cloning again. A report from this fallback checkout is saved under `D:\Test\wesnoth-diagnostics\diagnostics`. Preserve the existing project copies and verify their Git metadata before setting up future pulls; do not clone into `D:\Test\wesnoth-setup` itself.

The report collects installed versions and file sizes without installing packages, starting the game/server/database, or reading `.env` values. ADB inspection may start its normal local background daemon. Missing tools, Git metadata, upstream source or game data are recorded without preventing the remaining inventory. If SDK, emulator or ADB are outside standard locations, pass the optional path parameters documented in the script.

Return the report, including UNKNOWN/BLOCKED entries, so source integrity and installed versions can be checked. Copies downloaded from this VPS are not evidence of an independent intact source backup. Local filesystem paths and device serials appear in the report; remove those if desired. Do not send `.env`, access tokens, keystores or full environment-variable dumps.

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
