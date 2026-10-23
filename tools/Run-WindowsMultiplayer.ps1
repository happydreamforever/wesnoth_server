[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'),
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$repo = Split-Path $PSScriptRoot -Parent
$originalPath = $env:PATH
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $env:PATH = (Join-Path $MsysRoot 'mingw64\bin') + ';' + $originalPath
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('unified-multiplayer-run-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'run_unified_multiplayer.py') `
        --runtime $RuntimeRoot --identity (Join-Path $repo 'runtime\alliance-transport') | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Multiplayer stopped. Send the saved log.' }
    $result = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red }
finally {
    $env:PATH = $originalPath
    if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $log) }
}
exit $result
