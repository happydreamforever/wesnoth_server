# Windows Python 3.12 transition

This checkpoint interrupts the pending 1192624 World rollout only to change the project interpreter. Keep all five services stopped. Keep the accepted cold backup, package cache, installed game, saves and runtime-v2. Do not repeat database initialization or the 107-package download.

## Accepted Windows evidence

- Cold backup: 113 files / 257,065,798 bytes, verified with no schema claim. Private path: `C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192624-20261027-234120-963-9a74eff719334e9d885999ef17b69d7d`.
- The supplied pulls reached server `24129be2cb8c8a82c2943f0cf76beecdd4597a60` and client `5dff239ba895cd02c214c17c1ae1972519e1f697`. The client pull printed unavailable pack indexes; the subsequent read-only full Git check returned `GIT_CHECK_EXIT: 0`. No repository repair is needed on that evidence.
- `WORLD WORKER PACKAGE CACHE VERIFIED` confirms the 107 pinned archives/signatures were prepared. Its supplied console reports original MSYS package records preserved. This is Windows console evidence; the saved JSON and private backup were not opened on the VPS.
- No Windows Python 3.12 installation, isolated worker prefix, schema-4 migration, worker build or new gameplay acceptance has been reported yet.

## P1. Install the pinned interpreter alongside 3.14

While connected, download the installer (or copy it from a connected computer). Use the official [Python 3.12.10 release](https://www.python.org/downloads/release/python-31210/) and its **Windows installer (64-bit)**. This is the last official full Windows installer in the 3.12 series, not the latest source-only security release. Do not use the embeddable package, ARM64 or 32-bit installer.

Choose Customize installation, retain pip and venv support, and install for the current user at `%LOCALAPPDATA%\Programs\Python\Python312`. A PATH change is unnecessary: every project helper selects an explicit interpreter. Leave Python 3.14 installed until the new environment and subsequent five-service startup pass.

## P2. Pull and prepare the three replacement wheels while connected

This downloads about 1 MB when the previously verified cache is present. Fourteen wheels are reused; CFFI, MarkupSafe and PyMongo receive their CPython 3.12 x64 builds. Dependency versions and MongoDB 8.0.32 remain unchanged. The MongoDB ZIP is neither downloaded nor extracted by this transition.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
    $python312 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path -LiteralPath $python312 -PathType Leaf)) { throw 'Install Python 3.12.10 x64 first.' }
    & $python312 -I -B -c 'import sys,platform; print(sys.version); print(platform.machine()); sys.exit(sys.version_info[:3] != (3,12,10) or sys.maxsize <= 2**32)'
    if ($LASTEXITCODE -ne 0) { throw 'Expected CPython 3.12.10 x64. Stop here.' }

    $pythonBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $pythonBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $pythonBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Commit check failed for $name." }
    }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsAlliancePython312.ps1' `
        -Download
    if ($LASTEXITCODE -ne 0) { throw 'Python preparation stopped. Send the saved prepare log.' }
}
```

Expected: Python `3.12.10`, architecture `AMD64`, then `ALLIANCE PYTHON 3.12 CACHE READY`. Report: `wesnoth_server\diagnostics\alliance-python312-prepare-*.txt`. Keep services stopped. On any unexpected output, stop and return the console and log before P3.

## P3. Install and check offline

Disconnect WAN while retaining local Ethernet. Record this once for the new interpreter/World test batch. Keep all five services stopped; the helper holds their ports while installing.

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

Send P2/P3 output and batch WAN status. After review, resume [World step D](WORLD_ACCEPTANCE_1192624.md#d-download-once-then-prepare-the-isolated-worker-offline) at **offline prefix preparation**, using the accepted 107-package cache. Then continue E migration, F coordinated builds and G five-service readiness. Do not skip these World gates because Python passed.

## P4. Remove the old system Python after successful cutover

After P3 and World G pass, use Windows Settings → Apps → Installed apps → **Python 3.14.3 (64-bit)** → Uninstall. Keep Python 3.12.10, the Python Launcher, both retained build environments and recovery journals. Do not manually delete the old interpreter folder as an uninstall method. Old virtual environments depend on their original base installation; the retained 3.14 environment is a recovery artifact after uninstall, not a working fallback. The archived dependency pins allow deliberate recovery if later needed.

The isolated MINGW worker package closure contains its own Python 3.14.7 dependency for the pinned native libraries. It is not the Windows application interpreter and is not selected for project scripts or CMake Python execution. Do not delete or downgrade files inside that verified package prefix. The reviewed 107-package lock remains unchanged.

## Verification scope

See [the verification record](PYTHON312_VERIFICATION.json). VPS checks use actual CPython 3.12.10, disposable local MongoDB, retained APK/signature verification and real pinned archive contents, with networking disabled. Windows wrappers are exercised in Linux PowerShell simulations. No Windows execution is claimed until P1–P3 and the remaining World tests are reported.

The historical Dockerfile remains the earlier 3.14 baseline. Exact 3.12 checks explicitly invoke the separately built pinned 3.12.10 interpreter inside the existing Mongo-compatible container; they do not use its default Python. Earlier APK/native execution evidence remains bound to its original inputs. No new game compilation or gameplay result is claimed for this interpreter-only change.
