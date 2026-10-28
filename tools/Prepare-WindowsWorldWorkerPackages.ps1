# Verified pinned cache for the isolated worker; never installs into MSYS2.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    [switch]$Download
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$diagnostics = Join-Path $repo 'diagnostics'
$null = New-Item -ItemType Directory -Path $diagnostics -Force
$stem = 'world-worker-packages-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
$log = Join-Path $diagnostics ($stem + '.txt')
$report = Join-Path $diagnostics ($stem + '.json')
$result = 1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    $arguments = @('-I', '-B', (Join-Path $PSScriptRoot 'world_worker_packages.py'), '--msys', $MsysRoot, '--report', $report)
    if ($Download) {
        Write-Host 'Preparing the pinned package cache. Installed packages will not be changed.'
        $arguments += '--download'
    } else {
        Write-Host 'Verifying the pinned package cache without downloading or installing packages.'
    }
    & $PythonPath @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Worker package operation stopped. Keep the cache and operation journal; send this log and the JSON report if present.'
    }
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Package report (if produced): $report"
    Write-Host "Saved log: $log"
}
exit $result
