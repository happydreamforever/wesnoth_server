# Windows PowerShell 5.1. Cold backup/restore; stop all Alliance service windows first.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Backup','Restore')][string]$Operation,
    [Parameter(Mandatory=$true)][string]$DestinationPath,
    [string]$BackupPath,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $DestinationPath = Resolve-AllianceRuntimeRoot -Path $DestinationPath
    if ($Operation -eq 'Restore') {
        $BackupPath = Resolve-AllianceRuntimeRoot -Path $BackupPath
    } elseif ($PSBoundParameters.ContainsKey('BackupPath')) { throw 'BackupPath is only used for Restore.' }
    $python = Join-Path $repo 'build\alliance-venv-py312\Scripts\python.exe'
    $helper = Join-Path $PSScriptRoot 'alliance_maintenance.py'
    foreach ($file in @($python, $helper)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'The installed maintenance runtime is missing.' }
    }
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('alliance-maintenance-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    Write-Host 'MA01: Verify the installed offline tools.'
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-installed | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned offline dependency check failed.' }
    Write-Host 'MA02: Require stopped services and preserve the existing runtime.'
    Write-Host 'Backup and restored folders contain private credentials and player data. Keep them locally; do not send them as diagnostics.'
    $arguments = @('-I','-B',$helper,$Operation.ToLowerInvariant(),'--runtime',$RuntimeRoot,'--destination',$DestinationPath)
    if ($Operation -eq 'Restore') {
        $arguments += @('--backup',$BackupPath,'--mongod',(Join-Path $repo 'build\alliance-mongodb\bin\mongod.exe'))
    }
    & $python @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Maintenance did not complete. Keep the new destination and send only this sanitized log.' }
    Write-Host 'MA03: Maintenance complete. Existing runtime selection was not changed.'
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $log) }
}
exit $result
