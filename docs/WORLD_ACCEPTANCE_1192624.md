# Windows acceptance — Companies and Territorial Wars 1192624

Current checkpoint (2026-10-28): A–E, Python P1–P3, full D preparation, F bridge rebuild and F native Room server build pass at supplied Windows-console scope. The World worker failed at string.h lookup; Android rebuilding did not start. Follow [the compiler correction and worker-only retry](WORLD_WORKER_SYSROOT_1192624.md). Keep five services stopped and Python3.14 installed. Do not repeat accepted stages. Full F worker/Android and G–Z remain pending.

Use the existing `runtime-v2`, accounts, Teams, earned heroes, campaign saves, bundled public profile, original Android signer and one LDPlayer. This release explicitly upgrades schema 3 to 4 in place. It does not initialize another database, create founding Teams automatically or grant replacement heroes. Previously accepted results remain historical evidence; untested new behavior is NOT RUN.

Record WAN status once for this batch. GitHub and reviewed pinned missing-package preparation require connectivity before the offline build/test phase. Keep local Ethernet connected when WAN is disconnected. Stop at the first unexpected result, retain its logs and report the step, expected result and actual result. Retest the failed step and affected regressions after the fix; do not repeat unrelated accepted work.

## Before A: inventory reviewed

The supplied `world-worker-inventory-20261027-230551-870.txt` console lists 24 installed/cached MINGW64 packages. Their names, versions and sizes match the reviewed signed repository snapshot. This is user-supplied inventory evidence, not verification of installed files or native worker execution. The copied VPS MSYS headers/executables remain unusable placeholders.

The worker needs 107 pinned packages in total. The 83 additional archives total 100,641,401 bytes, plus small signatures and the official signing keyring. Existing cached archives are reused after exact size/SHA256 checks. The new helper downloads into `build/world-worker-packages-1192624`; it never installs into MSYS2, updates repositories, changes its keyring or upgrades the compiler.

The isolated prefix is assembled from verified archives, not from installed files that package scripts may have changed. Internal package hardlinks become independent files; installer scripts and hooks are not executed. The exact 57,474-file prefix occupies 1,686,953,610 bytes. Keep at least 3 GB free for dependency preparation, plus the additional space required by the full worker and retained Android builds. Cold backup, migration and build storage need their own headroom.

A–E and F's successful bridge/Room commands below retain the completed rollout sequence; do not repeat them. The current next command is the linked worker-only correction. Do not rerun the preliminary inventory or use `pacman -Syu`. Details and provenance: [worker dependency preparation](WORLD_WORKER_DEPENDENCIES_1192624.md).

## A. Save and stop

Save the current campaign under a new name. Finish or explicitly resolve existing active battles and pending results; do not erase them to satisfy the migration guard. Quit the game and stop any companions. Stop the five services with Ctrl+C in this order: native Room server, shared battles, account bridge, admin backend, MongoDB. Wait for all five PowerShell prompts.

Do not uninstall the app, clear its data, replace the OBB, remove operation locks, delete journals or edit database records. Keep the existing LDPlayer instance available.

## B. Make a private cold backup

Keep this PowerShell window and the exact backup path for E and Z:

```powershell
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
$worldRuntime = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'
$worldBackup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192624-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
    -Operation Backup -RuntimeRoot $worldRuntime -DestinationPath $worldBackup
if ($LASTEXITCODE -ne 0) { throw 'B stopped. Send the saved diagnostic log.' }
Write-Host ('Retain this exact private BackupPath: ' + $worldBackup)
```

Expected: `ALLIANCE BACKUP VERIFIED`, then MA03 completion. `schema_checked:false` describes a cold file backup; isolated restore checks the schema later. The backup contains credentials and player data. Keep it locally and send only the sanitized console/log.

## C. Pull the coordinated release

With services still stopped, temporarily connect to GitHub:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $worldRepo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $worldBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $worldRepo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Preserve local changes and stop." }
        & $worldBash --noprofile --norc -c ('/usr/bin/git -C ' + $worldRepo + ' rev-parse HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit." }
    }
}
```

Expected: both pulls succeed and print the release commits. Preserve unrelated README edits. Retain the existing ignored client `.env` and public profile; do not regenerate identity or paste private configuration.

## D. Download once, then prepare the isolated worker offline

The following online download already passed on 2026-10-27; retain it as historical instructions, not the next command:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsWorldWorkerPackages.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -Download
    if ($LASTEXITCODE -ne 0) { throw 'Package preparation stopped. Send the saved text and JSON reports; do not migrate.' }
}
```

Expected: `WORLD WORKER PACKAGE CACHE VERIFIED`, 107 pinned archives/signatures verified, and the original package inventory preserved. Reports: `diagnostics\world-worker-packages-*.txt` and `.json`. Keep the cache and its journals. Existing mismatched files, a changed toolchain or failed signature stop preparation instead of being overwritten. No database or service is started. Stop here and return the console plus saved text/JSON reports, including on success. Continue with offline preparation only after this result has been reviewed.

The following full D command has now passed on Windows. Retain its cache/prefix/journal and diagnostic scratch; do not rerun it. Continue at E below:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Isolated dependency preparation stopped. Preserve the cache and journal; send the saved log.' }
}
```

Expected: cache verification followed by `WORLD WORKER ISOLATED DEPENDENCIES PREPARED` (or `VERIFIED` on reuse). The helper checks package identity, signatures, dependency pins, every extracted file and the full prefix hash. Owned interrupted extraction resumes; foreign or changed output is retained and rejected. Report: `diagnostics\world-worker-prepare-*.txt`. Original MSYS2 files and package records remain unchanged.

The earlier `Test-WindowsWorldWorkerDependencies.ps1` audits installed MSYS files only. It will still report missing libraries because the new libraries deliberately live in the isolated prefix; it is no longer the release D gate. Native compilation and execution are verified at F/G, not inferred from extraction.

## E. Preserving schema 3 → 4 migration

Accepted on Windows with schema_version4/status complete. The command below is retained history; do not repeat it. Continue at F. The helper has already stopped its owned MongoDB process.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is missing. Stop and send this output.'
    }

    $worldRuntime = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'
    $worldBackup = 'C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192624-20261027-234120-963-9a74eff719334e9d885999ef17b69d7d'

    if (-not (Test-Path -LiteralPath (Join-Path $worldBackup 'manifest.json') -PathType Leaf)) {
        throw 'The accepted backup manifest is missing. Stop and send this output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Migrate-WindowsAllianceRuntime.ps1' `
        -RuntimeRoot $worldRuntime `
        -BackupPath $worldBackup

    if ($LASTEXITCODE -ne 0) {
        throw 'Migration stopped. Preserve the backup and journals; send the saved diagnostic log.'
    }
}
```

Expected: schema_version 4, status complete/already_complete, `ALLIANCE SCHEMA 4 MIGRATION COMPLETE`. Return the console and `diagnostics\alliance-migration-*.txt` before F. If stopped, retain the same exact B backup and all migration journals for review; do not reset or automatically retry. This does not initialize another runtime, create World geography, enlist starter soldiers or create accounts. Keep the private backup/runtime files on Windows; send only the diagnostic output.

## F. Rebuild the coordinated binaries offline

The original four-build batch below is retained history. Its bridge and Room builds passed, the worker failed, and Android did not start. **Do not rerun this whole block.** Use [the server-only correction and worker retry](WORLD_WORKER_SYSROOT_1192624.md), return its result, then resume Android. Keep five services stopped and retain local Ethernet with WAN disconnected during builds:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild failed. Send its saved logs.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Native Room server build failed. Send its saved log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Full native worker build failed. Send its saved log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild failed. Send its saved rebuild/build logs.' }
}
```

Expected markers: `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`, `UNIFIED MULTIPLAYER BUILD PASSED`, `FULL NATIVE WORLD WORKER BUILD PASSED`, `ANDROID ACCOUNT GAME REBUILD COMPLETE`. The full worker is a new build; it can take substantially longer than the bridge. Native tools remain GCC 16.2.0, CMake 4.3.0 and Ninja 1.13.2. Reports stay in each repository's `diagnostics` directory. Old completed stages, signer, OBB and journals remain retained. Return the full console after this batch, or the first error and that helper's saved logs. Review F before G startup and H installation; generic helper suggestions do not skip the checked service sequence.

## G. Start five services and verify worker availability

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles
    if ($LASTEXITCODE -ne 0) { throw 'Startup stopped. Send the workflow text/JSON and failing service log.' }
}
```

Expected W02 database, W03 backend, W04 bridge, W05 shared battles with one verified native worker available, W06 native Room server, then `W07 UNIFIED GAME SERVICES READY`. Keep all five service windows open. Workers start beneath shared battles when a committed engagement is queued; there is no sixth permanent service window. `WORLD NATIVE WORKER UNAVAILABLE` is not a passing G result.

Use the default one worker for initial testing. Additional disjoint-worker acceptance later uses `-WorldWorkers 2` when starting the stack after a deliberate safe restart, not a second stack against the same runtime. Logs: `diagnostics\alliance-workflow-*.txt/.json` and W02–W06 service transcripts.

## H. Install in place

Open the existing LDPlayer instance and wait for Android home:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation stopped. Send the saved install log.' }
}
```

Expected: original-signer/package/artifact checks, streamed installation Success, version **1192624**, `ANDROID ACCOUNT GAME INSTALL COMPLETE`. The accepted Emerald Court startup opens directly into Login; no profile import or replacement account is needed. Log: client `diagnostics\android-account-install-*.txt`.

## I–Z. Touch and gameplay acceptance

Follow [WORLD_MOBILE_ACCEPTANCE_1192624.md](WORLD_MOBILE_ACCEPTANCE_1192624.md). Use [WORLD_RECOVERY_ACCEPTANCE_1192624.md](WORLD_RECOVERY_ACCEPTANCE_1192624.md) only at its targeted T3/T4, U and Z3 steps for exact interruption, reconnect, timeout, worker-count and isolated restore commands. Return one group at a time. Use actual account/hero/soldier values, not remembered historical XP. Retain campaign saves and native replay/receipt evidence. No fake XP, artificial victory or direct database editing is part of normal acceptance.

For a second human-account seat with only one LDPlayer, use the separately authenticated native companion when instructed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsWorldCompanion.ps1' `
    -Username 'YOUR_EXISTING_SECOND_PLAYER'
```

Enter its password only at the hidden prompt and choose its already prepared battle. This helper does not create consent, choose Ready or award results. It controls only that account's assigned side with native AI. Its report is `diagnostics\world-companion-*\report.json`; keep its userdata and private input local. Report this as one LDPlayer plus authenticated AI companion, not multiple-human mobile acceptance.

The host controls world initialization and round boundaries through `http://127.0.0.1:18765/world` using the existing administrator. It must explicitly choose the two founding Teams. Player migration and login do not choose them automatically.

For any failure report: step/substep, actual message, relevant sanitized report paths, WAN status only if it changed, and a screenshot for layout defects. Keep credentials, private runtime files, `.env` contents and backups local. After analysis and a VPS fix, use the specific retest instructions rather than restarting the whole checklist.
