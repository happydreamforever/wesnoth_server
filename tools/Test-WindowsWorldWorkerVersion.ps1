# Windows PowerShell 5.1. Inspect the existing executable; never build or publish a receipt.
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

function Invoke-VersionInspection([string[]]$Arguments) {
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
    $name = 'world-worker-version-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
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
    $diagnostic = Join-Path $PSScriptRoot 'inspect_world_worker_version.py'
    foreach ($path in @($PythonPath, $diagnostic)) {
        Assert-OrdinaryAncestors -Path $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path -Force).Length -eq 0) {
            throw 'Python or the diagnostic helper is missing.'
        }
    }
    Write-Host 'Checking the existing worker version once with separate retained user and cache folders.'
    Write-Host 'No build, repair, database access or worker receipt publication is performed.'
    $stage = 'collection'
    $inspectionExit = Invoke-VersionInspection -Arguments @('-I', '-B', $diagnostic, '--report', $reportPath)
    if ($inspectionExit -ne 0) { throw 'Worker version collection was incomplete.' }
    $stage = 'report'
    Assert-OrdinaryAncestors -Path $reportPath
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw 'Diagnostic report is missing.' }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 1048576) { throw 'Diagnostic report has an unexpected size.' }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-world-worker-version-diagnostic' -or
        $report.release -ne 1192624 -or $report.scope -cne 'existing-worker-version-only' -or
        $report.collection.complete -isnot [bool] -or -not $report.collection.complete -or
        $report.receipt_written -isnot [bool] -or $report.receipt_written -ne $false -or
        $report.build_performed -isnot [bool] -or $report.build_performed -ne $false) {
        throw 'Diagnostic report does not confirm complete collection and its limited scope.'
    }
    foreach ($field in @('bin_unchanged', 'owner_unchanged', 'linked_executable_unchanged', 'version_header_unchanged', 'dependency_receipt_unchanged', 'source_binding_unchanged', 'no_receipt_created')) {
        $value = $report.preservation.$field
        if ($value -isnot [bool] -or -not $value) { throw 'Diagnostic report does not confirm preserved inputs.' }
    }
    Write-Host 'WORLD WORKER VERSION DIAGNOSTIC COMPLETE'
    Write-Host 'Version collection only. Return both reports before another build or service startup.'
    $result = 0
} catch {
    Write-Host ('ERROR: Worker version diagnostic stopped at stage=' + $stage + '. Send the saved text and JSON reports if present.')
    $result = 1
} finally {
    if ($started) {
        Write-Host ('JSON report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $log)
    }
}
exit $result
