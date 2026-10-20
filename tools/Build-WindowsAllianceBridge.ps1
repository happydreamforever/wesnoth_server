# Windows PowerShell 5.1. Builds only the new native account listener.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    [string]$CMakePath = 'C:\Program Files\CMake\bin\cmake.exe'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    $diagnostics = Join-Path $repo 'diagnostics'
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $log = Join-Path $diagnostics ('alliance-bridge-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    Write-Host 'Building the separate Alliance account listener offline; completed game and native stages are preserved.'
    & $PythonPath -I -B (Join-Path $PSScriptRoot 'build_alliance_bridge.py') --msys $MsysRoot --cmake $CMakePath | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Native account bridge build failed. Send the saved log.' }
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($started) {
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $log)
    }
}
exit $result
