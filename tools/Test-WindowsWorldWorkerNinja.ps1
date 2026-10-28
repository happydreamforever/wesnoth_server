# Windows PowerShell 5.1. Collect state without invoking or repairing the build.
[CmdletBinding()]
param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$result = 1
$started = $false
$stage = 'diagnostics'

function Assert-OrdinaryAncestors([string]$Path) {
    $candidate = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($candidate)) {
        if (Test-Path -LiteralPath $candidate) {
            if (((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'A diagnostic path is redirected.'
            }
        }
        $parent = [IO.Directory]::GetParent($candidate)
        $candidate = if ($null -eq $parent) { $null } else { $parent.FullName }
    }
}

function Invoke-NinjaInspection([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    $global:LASTEXITCODE = $null
    try {
        $ErrorActionPreference = 'Continue'
        & $PythonPath @Arguments 2>&1 | ForEach-Object { Write-Host $_.ToString() }
    } finally { $ErrorActionPreference = $previousPreference }
    if ($null -eq $global:LASTEXITCODE) { throw 'Python did not return an exit code.' }
    return $global:LASTEXITCODE
}

try {
    $diagnostics = Join-Path $repo 'diagnostics'
    Assert-OrdinaryAncestors -Path $diagnostics
    [IO.Directory]::CreateDirectory($diagnostics) | Out-Null
    $name = 'world-worker-ninja-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $log = Join-Path $diagnostics ($name + '.txt')
    $reportPath = Join-Path $diagnostics ($name + '.json')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    $stage = 'host'
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    if (-not $PSBoundParameters.ContainsKey('PythonPath')) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
        $PythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    }
    $diagnostic = Join-Path $PSScriptRoot 'inspect_world_worker_ninja.py'
    foreach ($path in @($PythonPath, $diagnostic)) {
        Assert-OrdinaryAncestors -Path $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path -Force).Length -eq 0) {
            throw 'Python or the diagnostic helper is missing.'
        }
    }

    Write-Host 'Collecting existing Ninja metadata and current Windows access checks.'
    Write-Host 'No build, file repair, process shutdown or runtime access is performed.'
    Write-Host ('CHECK TIME: ' + (Get-Date -Format o))
    $auxiliaryComplete = $true
    $stage = 'processes'
    Write-Host 'CURRENT BUILD PROCESSES (no command lines)'
    try {
        $filter = "Name = 'ninja.exe' OR Name = 'cmake.exe' OR Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'gcc.exe' OR Name = 'g++.exe' OR Name = 'cc1.exe' OR Name = 'cc1plus.exe' OR Name = 'ld.exe' OR Name = 'windres.exe'"
        $processes = @(Get-CimInstance Win32_Process -Filter $filter -Property ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate -ErrorAction Stop)
        if ($processes.Count -eq 0) { Write-Host 'No matching build processes.' }
        else { $processes | Format-List ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate | Out-Host }
    } catch {
        $auxiliaryComplete = $false
        Write-Host ('PROCESS SNAPSHOT UNAVAILABLE: ' + $_.CategoryInfo.Category)
    }

    $stage = 'permissions'
    $engine = Join-Path $repo 'build\windows-world-worker\engine'
    $permissionPaths = @($engine)
    foreach ($leaf in @('.ninja_log', '.ninja_log.restat', '.ninja_log.recompact', '.ninja_deps', '.ninja_deps.recompact', 'build.ninja')) {
        $permissionPaths += Join-Path $engine $leaf
    }
    Write-Host 'CURRENT BUILD METADATA PERMISSIONS'
    foreach ($path in $permissionPaths) {
        Write-Host ('PATH: ' + $path)
        try {
            Assert-OrdinaryAncestors -Path $path
            if (-not (Test-Path -LiteralPath $path)) { Write-Host 'MISSING'; continue }
            Get-Item -LiteralPath $path -Force | Format-List FullName,Attributes,Length,LastWriteTimeUtc | Out-Host
            Get-Acl -LiteralPath $path -ErrorAction Stop |
                Format-List Owner,Group,AreAccessRulesProtected,AccessToString | Out-Host
        } catch {
            $auxiliaryComplete = $false
            Write-Host ('PERMISSION SNAPSHOT UNAVAILABLE: ' + $_.CategoryInfo.Category)
        }
    }

    $stage = 'collection'
    $inspectionExit = Invoke-NinjaInspection -Arguments @('-I', '-B', $diagnostic, '--report', $reportPath)
    if ($inspectionExit -ne 0) { throw 'Ninja state collection was incomplete.' }
    $stage = 'report'
    Assert-OrdinaryAncestors -Path $reportPath
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw 'Diagnostic report is missing.' }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 67108864) { throw 'Diagnostic report has an unexpected size.' }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-world-worker-ninja-state' -or
        $report.collection.complete -isnot [bool] -or -not $report.collection.complete) {
        throw 'Diagnostic report does not confirm complete collection.'
    }
    if (-not $auxiliaryComplete) { throw 'Process or permission snapshot was incomplete; the JSON report was retained.' }
    Write-Host 'WORLD WORKER NINJA DIAGNOSTIC COMPLETE'
    Write-Host 'Collection only. Return both reports before another build or metadata recovery.'
    $result = 0
} catch {
    Write-Host ('ERROR: Worker Ninja diagnostic stopped at stage=' + $stage + '. Send the saved text and JSON reports if present.')
    $result = 1
} finally {
    if ($started) {
        Write-Host ('JSON report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $log)
    }
}
exit $result
