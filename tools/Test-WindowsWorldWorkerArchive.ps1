# Windows PowerShell 5.1. One-package extraction into a new retained scratch folder.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath
)
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

function Invoke-ArchiveDiagnostic([string[]]$Arguments) {
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
    if (((Get-Item -LiteralPath $diagnostics -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Diagnostics path is redirected.'
    }
    $name = 'world-worker-archive-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
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
    $stage = 'paths'
    $diagnostic = Join-Path $PSScriptRoot 'diagnose_world_worker_archive.py'
    foreach ($path in @($PythonPath, $diagnostic)) {
        if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'Python or the diagnostic helper is missing.'
        }
        Assert-OrdinaryAncestors -Path $path
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Length -eq 0 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Python or the diagnostic helper has an unexpected type.'
        }
    }
    $stage = 'run'
    Write-Host 'Checking one pinned package, then extracting it into a new retained diagnostic folder.'
    Write-Host 'This may take several minutes. Keep this window open; no automatic retry or repair is performed.'
    Write-Host 'The existing worker prefix, preparation journal, package cache and game runtime remain unchanged.'
    $result = Invoke-ArchiveDiagnostic -Arguments @('-I', '-B', $diagnostic, '--msys', $MsysRoot, '--report', $reportPath)
    if ($result -ne 0) { throw 'Archive diagnostic reported a failure.' }
    $stage = 'report'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw 'Diagnostic report is missing.' }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 32768 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Diagnostic report has an unexpected type or size.'
    }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-world-worker-archive-diagnostic' -or
        $report.release -ne 1192624 -or $report.scope -cne 'one-pinned-package' -or $report.status -cne 'passed' -or
        $report.package.name -cne 'mingw-w64-x86_64-aom' -or
        $report.whole_prefix_prepared -isnot [bool] -or $report.native_worker_tested -isnot [bool] -or
        $report.whole_prefix_prepared -ne $false -or $report.native_worker_tested -ne $false) {
        throw 'Diagnostic report does not confirm its limited scope.'
    }
    foreach ($phase in @('preflight', 'extract', 'verify')) {
        $rows = @($report.phases | Where-Object { $_.id -ceq $phase })
        if ($rows.Count -ne 1 -or $rows[0].status -cne 'passed') { throw 'Diagnostic phase did not pass.' }
    }
    Write-Host 'WORLD WORKER ARCHIVE DIAGNOSTIC COMPLETE'
    Write-Host 'One package only; return the text and JSON reports before resuming worker preparation.'
    $result = 0
} catch {
    Write-Host ('ERROR: Worker archive diagnostic stopped at stage=' + $stage + '. Send the saved text and JSON reports if present.')
    $result = 1
} finally {
    if ($started) {
        Write-Host ('JSON report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $log)
    }
}
exit $result
