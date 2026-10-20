# Windows PowerShell 5.1. Existing database and administration windows stay open.
[CmdletBinding()]
param(
    [AllowEmptyString()][string]$RuntimeRoot,
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64'
)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
$oldPath = $env:PATH
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    if (-not $PSBoundParameters.ContainsKey('RuntimeRoot')) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
        $RuntimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'
    }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $diagnostics = Join-Path $repo 'diagnostics'
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $log = Join-Path $diagnostics ('alliance-bridge-run-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $env:PATH = (Join-Path $MsysRoot 'mingw64\bin') + ';' + $oldPath
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'The verified isolated Python 3.14.3 is required.' }
    & $python -I -B (Join-Path $PSScriptRoot 'build_alliance_bridge.py') --verify | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Account bridge artifact verification failed. Preserve the existing build.' }
    $bridge = Join-Path $repo 'build\alliance-account-bridge\alliance-account-bridge.exe'
    $identity = Join-Path $repo 'runtime\alliance-transport'
    Write-Host 'Starting the account listener. Keep the existing database and admin service windows open.'
    & $bridge --runtime $RuntimeRoot --identity $identity | Out-Host
    $result = $LASTEXITCODE
    if ($result -ne 0) { throw 'Account listener stopped with an error. Send the saved log.' }
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    if ($result -eq 0) { $result = 1 }
} finally {
    $env:PATH = $oldPath
    if ($started) {
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $log)
    }
}
exit $result
