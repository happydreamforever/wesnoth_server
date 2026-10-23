# Windows PowerShell 5.1. Uses the installed offline Python and existing identity.
[CmdletBinding()]
param(
    [AllowEmptyString()][string]$RuntimeRoot,
    [string]$IdentityRoot = (Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\alliance-transport')
)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    if (-not $PSBoundParameters.ContainsKey('RuntimeRoot')) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
        $RuntimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'
    }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('alliance-battles-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'The installed Python 3.14.3 runtime is required.' }
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-installed | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Alliance installation verification failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'run_alliance_battles.py') --runtime $RuntimeRoot --identity $IdentityRoot | Out-Host
    $result = $LASTEXITCODE
    if ($result -ne 0) { throw 'Shared battle service stopped. Send this saved log.' }
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    if ($result -eq 0) { $result = 1 }
} finally {
    if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $log) }
}
exit $result
