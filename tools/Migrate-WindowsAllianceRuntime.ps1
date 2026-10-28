# Windows PowerShell 5.1. Explicit resumable schema upgrade; all services stopped.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2')
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $BackupPath = Resolve-AllianceRuntimeRoot -Path $BackupPath
    $python = Join-Path $repo 'build\alliance-venv-py312\Scripts\python.exe'
    $helper = Join-Path $PSScriptRoot 'migrate_alliance_runtime.py'
    $mongod = Join-Path $repo 'build\alliance-mongodb\bin\mongod.exe'
    foreach ($file in @($python,$helper,$mongod)) { if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'The pinned migration tools are missing.' } }
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('alliance-migration-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-installed | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned offline dependency check failed.' }
    & $python -I -B $helper --runtime $RuntimeRoot --backup $BackupPath --mongod $mongod | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Migration did not complete. Keep the private backup and journal; resume with the same BackupPath.' }
    $result = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red }
finally { if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $log) } }
exit $result
