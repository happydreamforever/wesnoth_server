# Windows PowerShell 5.1. Explicit fresh game; never overwrites the prior runtime.
# No transcript: administrator credentials are entered at private prompts only.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [string]$PreviousRuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'),
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3')
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$repo = Split-Path $PSScriptRoot -Parent
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
    $PreviousRuntimeRoot = Resolve-AllianceRuntimeRoot -Path $PreviousRuntimeRoot
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $BackupPath = Resolve-AllianceRuntimeRoot -Path $BackupPath
    $python = Join-Path $repo 'build\alliance-venv-py312\Scripts\python.exe'
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-installed
    if ($LASTEXITCODE -ne 0) { throw 'Pinned offline dependency check failed.' }
    Write-Host "Previous game retained: $PreviousRuntimeRoot"
    Write-Host "New Court game: $RuntimeRoot"
    Write-Host 'All five services must be stopped. Create the new administrator at the private prompts.'
    & $python -I -B (Join-Path $PSScriptRoot 'court_fresh_start.py') `
        --previous-runtime $PreviousRuntimeRoot --backup $BackupPath --runtime $RuntimeRoot `
        --mongod (Join-Path $repo 'build\alliance-mongodb\bin\mongod.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Fresh Court setup stopped. Send the diagnostic lines, never credentials or private runtime files.' }
    exit 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
