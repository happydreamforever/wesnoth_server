# Windows Python 3.12 transition

This checkpoint interrupts the pending 1192624 World rollout only to change the project interpreter. Keep all five services stopped. Keep the accepted cold backup, package cache, installed game, saves and runtime-v2. Do not repeat database initialization or the 107-package download.

## Accepted Windows evidence

- Cold backup: 113 files / 257,065,798 bytes, verified with no schema claim. Private path: `C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192624-20261027-234120-963-9a74eff719334e9d885999ef17b69d7d`.
- The supplied pulls reached server `24129be2cb8c8a82c2943f0cf76beecdd4597a60` and client `5dff239ba895cd02c214c17c1ae1972519e1f697`. The client pull printed unavailable pack indexes; the subsequent read-only full Git check returned `GIT_CHECK_EXIT: 0`. No repository repair is needed on that evidence.
- `WORLD WORKER PACKAGE CACHE VERIFIED` confirms the 107 pinned archives/signatures were prepared. Its supplied console reports original MSYS package records preserved. This is Windows console evidence; the saved JSON and private backup were not opened on the VPS.
- P1 accepted on 2026-10-28: the explicit Windows Python312 interpreter reports CPython3.12.10, 64-bit AMD64, and PYTHON312_CHECK_EXIT:0. The repeated client Git check returns GIT_CHECK_EXIT:0. P2 dependency preparation and P3 isolated-environment installation are still pending, along with the isolated worker prefix, schema-4 migration, worker build and new gameplay acceptance.

## P1. Install the pinned interpreter alongside 3.14

Accepted from the supplied Windows output. Retain the instructions below for reference; continue at P2 without reinstalling or repeating the base-interpreter check.

While connected, download the installer (or copy it from a connected computer). Use the official [Python 3.12.10 release](https://www.python.org/downloads/release/python-31210/) and its **Windows installer (64-bit)**. This is the last official full Windows installer in the 3.12 series, not the latest source-only security release. Do not use the embeddable package, ARM64 or 32-bit installer.

Choose Customize installation, retain pip and venv support, and install for the current user at `%LOCALAPPDATA%\Programs\Python\Python312`. A PATH change is unnecessary: every project helper selects an explicit interpreter. Leave Python 3.14 installed until the new environment and subsequent five-service startup pass.

## P2. Pull and prepare the three replacement wheels while connected

The latest attempt stopped at the folder-layout check. Use the diagnostic below before retrying these retained preparation instructions.

This downloads about 1 MB when the previously verified cache is present. Fourteen wheels are reused; CFFI, MarkupSafe and PyMongo receive their CPython 3.12 x64 builds. Dependency versions and MongoDB 8.0.32 remain unchanged. The MongoDB ZIP is neither downloaded nor extracted by this transition.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
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

Expected: both pulls succeed and print their commit IDs, followed by `ALLIANCE PYTHON 3.12 CACHE READY`. The preparation helper validates the selected interpreter automatically. Report: `wesnoth_server\diagnostics\alliance-python312-prepare-*.txt`. Keep services stopped. On any unexpected output, stop and return the console and log before P3.

## Current P2 stop: inspect the MongoDB installation folder

The 2026-10-28 supplied console confirms both pulls (server810988e/client044af5d) but preparation stops with `MongoDB directory contains unexpected files; preserved.` P2 has not passed. The code stopped before wheel preparation and before checking the known MongoDB file contents. An entry-name mismatch alone does not establish corruption or reveal which entry differs.

Keep the five services stopped and Python3.14 installed. Do not repeat P2 or proceed to P3 yet. Run this read-only listing; it reads only directory metadata and writes a new diagnostic transcript. It does not open file contents, recurse into extra folders, execute MongoDB or access runtime-v2.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = 'D:\Test\wesnoth-setup\wesnoth_server'
    $mongoInstall = Join-Path $repo 'build\alliance-mongodb'
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('mongo-install-layout-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')

    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    try {
        foreach ($folder in @($mongoInstall, (Join-Path $mongoInstall 'bin'))) {
            $item = Get-Item -LiteralPath $folder -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Unexpected folder type or redirected path. Files were preserved.'
            }
            Write-Host "FOLDER: $folder"
            Get-ChildItem -LiteralPath $folder -Force |
                Sort-Object Name |
                Select-Object Name,PSIsContainer,Length,Attributes,LastWriteTimeUtc |
                Format-List
        }
        Write-Host 'READ-ONLY MONGODB FOLDER CHECK COMPLETE'
    } finally {
        Stop-Transcript | Out-Null
        Write-Host "Saved log: $log"
    }
}
```

Expected: two folder listings and `READ-ONLY MONGODB FOLDER CHECK COMPLETE`. This marker means collection completed, not that MongoDB passed verification. Send the saved text log and console. Do not send any extra files shown by the listing. Choose the correction and affected retest only after those actual names are reviewed. No new pull is needed for this inline command.

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

Return each step separately: P2 output first, then P3 output and batch WAN status after preparation is accepted. After review, resume [World step D](WORLD_ACCEPTANCE_1192624.md#d-download-once-then-prepare-the-isolated-worker-offline) at **offline prefix preparation**, using the accepted 107-package cache. Then continue E migration, F coordinated builds and G five-service readiness. Do not skip these World gates because Python passed.

## P4. Remove the old system Python after successful cutover

After P3 and World G pass, use Windows Settings → Apps → Installed apps → **Python 3.14.3 (64-bit)** → Uninstall. Keep Python 3.12.10, the Python Launcher, both retained build environments and recovery journals. Do not manually delete the old interpreter folder as an uninstall method. Old virtual environments depend on their original base installation; the retained 3.14 environment is a recovery artifact after uninstall, not a working fallback. The archived dependency pins allow deliberate recovery if later needed.

The isolated MINGW worker package closure contains its own Python 3.14.7 dependency for the pinned native libraries. It is not the Windows application interpreter and is not selected for project scripts or CMake Python execution. Do not delete or downgrade files inside that verified package prefix. The reviewed 107-package lock remains unchanged.

## Verification scope

See [the verification record](PYTHON312_VERIFICATION.json). VPS checks use actual CPython 3.12.10, disposable local MongoDB, retained APK/signature verification and real pinned archive contents, with networking disabled. Windows wrappers are exercised in Linux PowerShell simulations. P1 Windows base-interpreter execution is now user-reported and accepted. Windows dependency preparation, isolated-environment execution and the remaining World tests are still pending.

The historical Dockerfile remains the earlier 3.14 baseline. Exact 3.12 checks explicitly invoke the separately built pinned 3.12.10 interpreter inside the existing Mongo-compatible container; they do not use its default Python. Earlier APK/native execution evidence remains bound to its original inputs. No new game compilation or gameplay result is claimed for this interpreter-only change.
