# Windows PowerShell 5.1. Builds the authenticated native multiplayer lobby in a separate stage.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    [string]$CMakePath = 'C:\Program Files\CMake\bin\cmake.exe',
    [switch]$PreservePreviousBuild
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    $diagnostics = Join-Path $repo 'diagnostics'
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $log = Join-Path $diagnostics ('unified-multiplayer-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    Write-Host 'Building the unified native multiplayer lobby offline; the original guest server is preserved.'
    $arguments = @('-I', '-B', (Join-Path $PSScriptRoot 'build_unified_multiplayer.py'), '--msys', $MsysRoot, '--cmake', $CMakePath)
    if ($PreservePreviousBuild) { $arguments += '--preserve-previous' }
    & $PythonPath @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Unified multiplayer build failed. Send the saved log.' }
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
