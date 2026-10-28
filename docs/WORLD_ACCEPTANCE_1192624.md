# Windows acceptance — Companies and Territorial Wars 1192624

Status: implementation and VPS verification complete. Actual Windows worker dependency inventory remains the delivery gate. Do not begin migration or the offline build batch until that audit is reviewed; Windows A-Z is not yet accepted. Final coordinated commits are supplied in the release handoff.

Use the existing `runtime-v2`, accounts, Teams, earned heroes, campaign saves, bundled public profile, original Android signer and one LDPlayer. This release explicitly upgrades schema 3 to 4 in place. It does not initialize another database, create founding Teams automatically or grant replacement heroes. Previously accepted results remain historical evidence; untested new behavior is NOT RUN.

Record WAN status once for this batch. GitHub and reviewed pinned missing-package preparation require connectivity before the offline build/test phase. Keep local Ethernet connected when WAN is disconnected. Stop at the first unexpected result, retain its logs and report the step, expected result and actual result. Retest the failed step and affected regressions after the fix; do not repeat unrelated accepted work.

## Before A: read-only dependency inventory

The full Windows game engine needs more libraries than the account bridge. A copied MSYS folder on the VPS is not proof of usable Windows dependencies. Resolve the read-only inventory before scheduling the offline batch. The release does not run `pacman -Syu`, upgrade unrelated tools or substitute another compiler ABI.

Run this read-only collection in Windows PowerShell and return its saved text log. It does not require a new repository pull or any service restart:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldMsys = 'D:\Test\wesnoth-setup\msys64'
    $worldDiagnostics = 'D:\Test\wesnoth-setup\wesnoth_server\diagnostics'
    $null = New-Item -ItemType Directory -Path $worldDiagnostics -Force
    $worldLog = Join-Path $worldDiagnostics ('world-worker-inventory-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    Start-Transcript -LiteralPath $worldLog -NoClobber | Out-Null
    try {
        'INSTALLED MINGW64 PACKAGE RECORDS'
        Get-ChildItem -LiteralPath (Join-Path $worldMsys 'var\lib\pacman\local') -Directory |
            Where-Object { $_.Name -like 'mingw-w64-x86_64-*' } |
            Select-Object -ExpandProperty Name
        'CACHED MINGW64 PACKAGES'
        Get-ChildItem -LiteralPath (Join-Path $worldMsys 'var\cache\pacman\pkg') -File |
            Where-Object { $_.Name -like 'mingw-w64-x86_64-*' -and $_.Name -notlike '*.sig' } |
            Select-Object Name,Length | Format-List
        'READ-ONLY WORKER INVENTORY COMPLETE'
    } finally {
        Stop-Transcript | Out-Null
        Write-Host "Saved log: $worldLog"
    }
}
```

Expected: installed package names/versions, cached archive names/sizes and the saved log path. This preliminary inventory is not a full dependency PASS; D verifies package contents and versions before E can run.

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

## D. Verify and isolate worker dependencies

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsWorldWorkerDependencies.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency audit is incomplete. Send its JSON report; do not migrate or upgrade packages.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Isolated dependency preparation stopped. Send the saved log.' }
}
```

Expected: `WORLD WORKER DEPENDENCY AUDIT COMPLETE`, installed package integrity verified, then `WORLD WORKER ISOLATED DEPENDENCIES PREPARED` or `VERIFIED`. The helper checks installed package ownership, recorded SHA256s and dependency versions, then copies the exact closure into `build\world-worker-prefix`. It does not install packages. Reports: `diagnostics\world-worker-dependencies-*.json` and `world-worker-prepare-*.txt`.

If libraries are missing, stop here. A reviewed, pinned offline package batch must be prepared from the actual report before continuing. A header-only audit or successful bridge build is not full-engine acceptance. Once dependency preparation is complete, disconnect WAN while retaining Ethernet and record that state once.

## E. Preserving schema 3 → 4 migration

```powershell
$ErrorActionPreference = 'Stop'
if (-not $worldBackup -or -not (Test-Path -LiteralPath (Join-Path $worldBackup 'manifest.json') -PathType Leaf)) {
    throw 'Restore the exact verified B backup path in $worldBackup first.'
}
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Migrate-WindowsAllianceRuntime.ps1' `
    -RuntimeRoot $worldRuntime -BackupPath $worldBackup
if ($LASTEXITCODE -ne 0) { throw 'Migration stopped. Keep the same backup and journals; send the saved log.' }
```

Expected: schema_version 4, status complete/already_complete, `ALLIANCE SCHEMA 4 MIGRATION COMPLETE`. A retry uses the same command and exact B backup. Preserve the old schema-2→3 journal and the new schema-3→4 journals. No world, starter soldiers or new account is created here. Log: `diagnostics\alliance-migration-*.txt`.

## F. Rebuild the coordinated binaries offline

Run sequentially; stop immediately if any helper fails:

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

Expected markers: `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`, `UNIFIED MULTIPLAYER BUILD PASSED`, `FULL NATIVE WORLD WORKER BUILD PASSED`, `ANDROID ACCOUNT GAME REBUILD COMPLETE`. The full worker is a new build; it can take substantially longer than the bridge. Native tools remain GCC 16.2.0, CMake 4.3.0 and Ninja 1.13.2. Reports stay in each repository's `diagnostics` directory. Old completed stages, signer, OBB and journals remain retained.

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
