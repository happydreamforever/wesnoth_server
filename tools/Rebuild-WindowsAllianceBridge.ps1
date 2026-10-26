# Windows PowerShell 5.1. Preserve one completed bridge build, then build updated sources.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    [string]$CMakePath = 'C:\Program Files\CMake\bin\cmake.exe'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $repo 'build\alliance-account-bridge'
$legacyInputs = @('alliance_bridge/CMakeLists.txt', 'alliance_bridge/main.cpp', 'tools/build_alliance_bridge.py')
$inputs = @('alliance_bridge/CMakeLists.txt', 'alliance_bridge/main.cpp', 'alliance_bridge/progression_protocol.hpp', 'alliance_bridge/unified_protocol.hpp', 'alliance_bridge/flexible_protocol.hpp', 'tools/build_alliance_bridge.py')
$started = $false
$result = 1
$log = $null

function Assert-OrdinaryDirectory([string]$Path) {
    $cursor = $Path
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The bridge stage and parent directories must not be links or special paths. Nothing was renamed.'
        }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
function Test-CompletedBridge([bool]$CurrentSources) {
    Assert-OrdinaryDirectory $stage
    foreach ($name in @('owner.json', 'receipt.json', 'alliance-account-bridge.exe')) {
        $file = Get-Item -LiteralPath (Join-Path $stage $name) -Force -ErrorAction Stop
        if ($file.PSIsContainer -or $file.Length -eq 0 -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The completed bridge stage contains a missing, empty or linked input. Preserve it and send the log.'
        }
        if ($name -ne 'alliance-account-bridge.exe' -and $file.Length -gt 32768) {
            throw 'The saved bridge metadata exceeds its size limit. Preserve it and send the log.'
        }
    }
    try {
        $owner = Get-Content -LiteralPath (Join-Path $stage 'owner.json') -Raw | ConvertFrom-Json
        $receipt = Get-Content -LiteralPath (Join-Path $stage 'receipt.json') -Raw | ConvertFrom-Json
    } catch {
        # A parser exception can include invalid JSON text. Keep file contents
        # out of console/transcript even when local metadata is damaged.
        throw 'The completed bridge metadata could not be read or parsed. Existing files were preserved.'
    }
    $exe = Get-Item -LiteralPath (Join-Path $stage 'alliance-account-bridge.exe') -Force
    # Completed pre-progression builds may be preserved with their original
    # three/four/five-input bindings. New output must bind every protocol header.
    $bindingInputs = $inputs
    if (-not $CurrentSources -and @($owner.inputs.PSObject.Properties.Name).Count -eq $legacyInputs.Count) {
        $bindingInputs = $legacyInputs
    } elseif (-not $CurrentSources -and @($owner.inputs.PSObject.Properties.Name).Count -eq 5) {
        $bindingInputs = @('alliance_bridge/CMakeLists.txt', 'alliance_bridge/main.cpp', 'alliance_bridge/progression_protocol.hpp', 'alliance_bridge/unified_protocol.hpp', 'tools/build_alliance_bridge.py')
    } elseif (-not $CurrentSources -and @($owner.inputs.PSObject.Properties.Name).Count -eq 4) {
        $bindingInputs = @('alliance_bridge/CMakeLists.txt', 'alliance_bridge/main.cpp', 'alliance_bridge/progression_protocol.hpp', 'tools/build_alliance_bridge.py')
    }
    foreach ($binding in @($owner, $receipt.binding)) {
        if (@($binding.PSObject.Properties.Name).Count -ne 3 -or
            -not ($binding.format -is [int] -or $binding.format -is [long]) -or $binding.format -ne 1 -or
            $binding.purpose -cne 'wesnoth-alliance-account-bridge' -or
            @($binding.inputs.PSObject.Properties.Name).Count -ne $bindingInputs.Count) {
            throw 'The saved bridge ownership or receipt binding is invalid. Preserve it and send the log.'
        }
        foreach ($name in $bindingInputs) {
            $hash = $binding.inputs.$name
            if (@($binding.inputs.PSObject.Properties.Name) -cnotcontains $name -or
                $hash -isnot [string] -or $hash -cnotmatch '^[0-9a-f]{64}$') {
                throw 'The saved bridge source binding is invalid. Preserve it and send the log.'
            }
        }
    }
    foreach ($name in $bindingInputs) {
        if ($owner.inputs.$name -cne $receipt.binding.inputs.$name) {
            throw 'The completed bridge ownership and receipt disagree. Preserve them and send the log.'
        }
        if ($CurrentSources -and $owner.inputs.$name -cne (Get-FileHash -LiteralPath (Join-Path $repo $name) -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'The rebuilt bridge receipt does not match the current sources. Send the saved build log.'
        }
    }
    if (@($receipt.PSObject.Properties.Name).Count -ne 3 -or $null -eq $receipt.versions -or
        @($receipt.executable.PSObject.Properties.Name).Count -ne 3 -or
        $receipt.executable.name -cne $exe.Name -or $receipt.executable.bytes -ne $exe.Length -or
        $receipt.executable.sha256 -isnot [string] -or $receipt.executable.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.executable.sha256) {
        throw 'The completed bridge receipt or executable differs. Preserve the stage and send the log.'
    }
}
function Assert-BridgeStopped {
    $running = @(Get-CimInstance Win32_Process -Filter "Name = 'alliance-account-bridge.exe'" -ErrorAction Stop)
    if ($running.Count -ne 0) {
        throw 'An account bridge is running. Keep its files and send this output; no process was stopped.'
    }
}
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on the Windows computer.' }
    Assert-OrdinaryDirectory $repo
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    Assert-OrdinaryDirectory $diagnostics
    $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $log = Join-Path $diagnostics ('alliance-bridge-rebuild-' + $stamp + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    Assert-BridgeStopped
    Test-CompletedBridge $false
    $backupName = 'alliance-account-bridge-before-update-' + $stamp
    $backup = Join-Path (Split-Path $stage -Parent) $backupName
    if (Test-Path -LiteralPath $backup) { throw 'The unique backup destination already exists. Nothing was renamed.' }
    Assert-BridgeStopped
    Rename-Item -LiteralPath $stage -NewName $backupName -ErrorAction Stop
    Write-Host "Completed bridge build preserved: $backup"
    Write-Host 'Building only the updated Alliance listener. The database and completed game stages are preserved.'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot 'Build-WindowsAllianceBridge.ps1') `
        -MsysRoot $MsysRoot -PythonPath $PythonPath -CMakePath $CMakePath
    if ($LASTEXITCODE -ne 0) { throw 'The updated bridge build failed. The old build remains in its backup. Send both saved logs.' }
    Test-CompletedBridge $true
    Write-Host 'ALLIANCE ACCOUNT BRIDGE REBUILD PASSED'
    Write-Host 'Next: run tools/Run-WindowsAllianceBridge.ps1 with the existing profile runtime.'
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($started) { Stop-Transcript | Out-Null }
    if ($log) { Write-Host "Saved rebuild log: $log" }
}
exit $result
