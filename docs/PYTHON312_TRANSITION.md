**Current Windows step:** Worker compilation and linking passed; final version capture stopped. Follow [the existing-executable version diagnostic](WORLD_WORKER_VERSION_1192624.md). Keep services stopped and return both reports before another build. Earlier instructions below are historical.

**Current Windows step:** Ninja history recovery and guarded configuration passed. Continue with [the Windows profile-reader correction](WORLD_WORKER_PROFILE_1192624.md); keep services stopped and omit the old NinjaReportPath on that retry. Earlier instructions below remain historical.

**Current Windows checkpoint:** Ninja metadata recovery is next; use [WORLD_WORKER_NINJA_RECOVERY_1192624.md](WORLD_WORKER_NINJA_RECOVERY_1192624.md) before any worker retry, Android build or service startup. Accepted dependency/migration/bridge/Room/Python results remain intact.

**Current worker step:** Compiler/resource checks and preservation passed; CMake/Ninja failed while replacing its build log. Follow [the current Ninja metadata diagnostic](WORLD_WORKER_NINJA_1192624.md) before any further build. Accepted Python/migration/bridge/Room work remains preserved.

# Windows Python 3.12 transition

Python 3.12 P1–P3, full worker dependencies, schema-4 migration, bridge/Room builds, compiler preflight and old-stage preservation are accepted on Windows. The worker now stops at resource compilation (575/589). Follow [the resource-only correction](WORLD_WORKER_RESOURCE_1192624.md); no Python reinstall or repeated transition is required. Keep all five services stopped and Python 3.14 installed until G acceptance. Android rebuilding has not started.

## Accepted Windows evidence

- Cold backup: 113 files / 257,065,798 bytes, verified with no schema claim. Private path: `C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192624-20261027-234120-963-9a74eff719334e9d885999ef17b69d7d`.
- The supplied pulls reached server `24129be2cb8c8a82c2943f0cf76beecdd4597a60` and client `5dff239ba895cd02c214c17c1ae1972519e1f697`. The client pull printed unavailable pack indexes; the subsequent read-only full Git check returned `GIT_CHECK_EXIT: 0`. No repository repair is needed on that evidence.
- `WORLD WORKER PACKAGE CACHE VERIFIED` confirms the 107 pinned archives/signatures were prepared. Its supplied console reports original MSYS package records preserved. This is Windows console evidence; the saved JSON and private backup were not opened on the VPS.
- P1 accepted on 2026-10-28: the explicit Windows Python312 interpreter reports CPython 3.12.10, 64-bit AMD64, and PYTHON312_CHECK_EXIT:0. The repeated client Git check returns GIT_CHECK_EXIT:0. P2 reached a folder-layout failure; the two reported diagnostic files are now handled by the verified fix below. P2 retry is now accepted from the supplied Windows console. P3 is also accepted: all 17 packages installed from cache, native-module checks passed and the transition was verified. Saved log: `diagnostics/alliance-python312-install-20261028-005353-591-384583f6976847d78505ea3e714b1606.txt`. The user confirms WAN disconnected/local Ethernet retained for this batch. The isolated worker prefix and schema-4 migration subsequently passed D/E; coordinated builds, worker/service startup and new gameplay acceptance remain pending.

## P1. Install the pinned interpreter alongside 3.14

Accepted from the supplied Windows output. Retain the instructions below for reference; continue at World F builds after accepted D/E without repeating P1–P3.

While connected, download the installer (or copy it from a connected computer). Use the official [Python 3.12.10 release](https://www.python.org/downloads/release/python-31210/) and its **Windows installer (64-bit)**. This is the last official full Windows installer in the 3.12 series, not the latest source-only security release. Do not use the embeddable package, ARM64 or 32-bit installer.

Choose Customize installation, retain pip and venv support, and install for the current user at `%LOCALAPPDATA%\Programs\Python\Python312`. A PATH change is unnecessary: every project helper selects an explicit interpreter. Leave Python 3.14 installed until the new environment and subsequent five-service startup pass.

## P2. Preparation accepted

The successful retry reached server `acd35a27984837a171e031eed984e83103d0768f` and verified all 17 wheels, retaining both MongoDB dumps. `ALLIANCE PYTHON 3.12 CACHE READY` appeared. Saved log: `diagnostics/alliance-python312-prepare-20261028-005052-213-cb166be869bd477fbf6c44e3b8e48c61.txt`. This is supplied-console evidence; the saved Windows file itself was not opened on the VPS. **P3 has also passed; continue at World F builds after accepted D/E. Do not repeat the commands below**, which are retained as preparation history.

The earlier pulls delivered Python 3.12 support to both repositories. The returned folder listing now identifies the two extra files that stopped preparation: `bin/mongod.2026-10-19T19-37-33.mdmp` (517,241 bytes) and `bin/mongod.2026-10-20T04-02-35.mdmp` (523,111 bytes). The saved metadata log is `diagnostics/mongo-install-layout-20261028-004222-844-eca9687d4aec4ca79d45e2bf43dab384.txt`. Their contents were not supplied. No further listing or dump upload is needed.

Server fix `e936b29` retains timestamped ordinary diagnostic files in an existing installation while still checking its ownership receipt and all six pinned MongoDB files. Fresh extraction remains strict. The original P2 rejection was reproduced and the correction verified on the VPS; the Windows P2 retry has now passed.

The following preparation command was run while connected and is retained for reference. Keep all five services stopped and Python 3.14 installed; the next current step is World F builds after accepted D/E. The client helpers are already current. This downloads about 1 MB when the previously verified cache is present: fourteen wheels are reused, while CFFI, MarkupSafe and PyMongo receive their CPython 3.12 x64 builds. Dependency versions and MongoDB 8.0.32 remain unchanged. The MongoDB ZIP is neither downloaded nor extracted.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $pythonBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $pythonBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull failed. Stop and send the output.' }

    & $pythonBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check failed. Stop and send the output.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsAlliancePython312.ps1' `
        -Download
    if ($LASTEXITCODE -ne 0) { throw 'Python preparation stopped. Send the saved prepare log.' }
}
```

Expected:

- Successful server pull and printed commit ID, including the correction in its history.
- `Pinned MongoDB files verified; retained diagnostic dumps: 2.`
- `ALLIANCE PYTHON 3.12 CACHE READY`

Report: `wesnoth_server\diagnostics\alliance-python312-prepare-*.txt`. The returned console is accepted and subsequent P3 has passed; continue at World F builds after accepted D/E. Keep the diagnostic dumps in place; do not send them. No database initialization, client rebuild, new backup or repeat worker-package download is required.

## P3. Offline installation accepted

The returned Windows output contains both expected success markers below and successful installation of all 17 packages. The user explicitly confirms WAN stayed disconnected while local Ethernet remained connected. Saved log: `diagnostics/alliance-python312-install-20261028-005353-591-384583f6976847d78505ea3e714b1606.txt`. Keep this network state and all five services stopped; continue at World F builds after accepted D/E. The installation command is retained for reference, not repetition.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Install-WindowsAlliancePython312.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Python transition stopped. Preserve both environments and send the saved install log.' }
}
```

Expected:

- `ALLIANCE PYTHON NATIVE MODULE CHECK PASSED`
- `ALLIANCE PYTHON 3.12 TRANSITION VERIFIED`

Report: `wesnoth_server\diagnostics\alliance-python312-install-*.txt`. The check exercises native Argon2, CFFI, BSON, MarkupSafe, Flask and TLS support locally; it does not sign in or change accounts. Installation uses pinned wheels with `--no-index`, no dependency resolution or downloads.

The new environment is `wesnoth_server\build\alliance-venv-py312`. The old `build\alliance-venv` and MongoDB files are inventoried before and after. Runtime-v2, database schema, accounts and saves are not opened or changed. Recovery records are retained in `build\alliance-python312-transition`; do not delete its locks or journals if a run stops. Completed reruns verify rather than reinstall.

P1–P3 and their WAN-disconnected confirmation remain accepted. The targeted archive diagnostic, full World D preparation and E schema-4 migration now also pass on Windows. Continue only at [F coordinated builds](WORLD_ACCEPTANCE_1192624.md#f-rebuild-the-coordinated-binaries-offline), returning its console and saved logs before G five-service readiness. These later gates remain pending.

## P4. Remove the old system Python after successful cutover

After P3 and World G pass, use Windows Settings → Apps → Installed apps → **Python 3.14.3 (64-bit)** → Uninstall. Keep Python 3.12.10, the Python Launcher, both retained build environments and recovery journals. Do not manually delete the old interpreter folder as an uninstall method. Old virtual environments depend on their original base installation; the retained 3.14 environment is a recovery artifact after uninstall, not a working fallback. The archived dependency pins allow deliberate recovery if later needed.

The isolated MINGW worker package closure contains its own Python 3.14.7 dependency for the pinned native libraries. It is not the Windows application interpreter and is not selected for project scripts or CMake Python execution. Do not delete or downgrade files inside that verified package prefix. The reviewed 107-package lock remains unchanged.

## Verification scope

See [the transition verification record](PYTHON312_VERIFICATION.json) and [the focused diagnostic-retention correction](PYTHON312_MONGO_DIAGNOSTICS_VERIFICATION.json). VPS checks use actual CPython 3.12.10, disposable local MongoDB, retained APK/signature verification and real pinned archive contents, with networking disabled. Windows wrappers are exercised in Linux PowerShell simulations. P1 Windows base-interpreter execution is now user-reported and accepted. Windows P2 dependency preparation is now accepted from the supplied console. P3 isolated-environment installation and native-module execution are now accepted from the supplied Windows transcript with explicit WAN-disconnected confirmation. World prefix preparation and schema-4 migration now pass at supplied Windows-console scope; builds, worker/service startup and gameplay tests remain pending.

The historical Dockerfile remains the earlier 3.14 baseline. Exact 3.12 checks explicitly invoke the separately built pinned 3.12.10 interpreter inside the existing Mongo-compatible container; they do not use its default Python. Earlier APK/native execution evidence remains bound to its original inputs. No new game compilation or gameplay result is claimed for this interpreter-only change.
