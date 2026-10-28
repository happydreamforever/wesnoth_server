# Windows PowerShell 5.1. Separate authenticated acceptance companion.
[CmdletBinding()]
param(
    [string]$BattleId,
    [Parameter(Mandatory=$true)][string]$Username,
    [string]$PublicProfile = (Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\alliance-transport\public-profile.json')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python
    if ($LASTEXITCODE -ne 0) { throw 'The installed pinned Python runtime is required.' }
    $companionArgs = @('--username', $Username, '--profile', $PublicProfile)
    if (-not [string]::IsNullOrWhiteSpace($BattleId)) { $companionArgs += @('--battle-id', $BattleId) }
    & $python -I -B (Join-Path $PSScriptRoot 'run_world_companion.py') @companionArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
