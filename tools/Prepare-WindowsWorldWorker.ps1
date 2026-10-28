# Build the isolated prefix from signed pinned archives; no MSYS2 installation.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$null = New-Item -ItemType Directory -Path (Join-Path $repo 'diagnostics') -Force
$log = Join-Path $repo ('diagnostics\world-worker-prepare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
$result = 1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    Write-Host 'Preparing the isolated worker prefix from the verified offline package cache.'
    Write-Host 'Verifying 107 packages and preparing the full engine libraries may take several minutes.'
    Write-Host 'Existing MSYS2 packages remain unchanged; package scripts and hooks are not run.'
    & $PythonPath -I -B (Join-Path $PSScriptRoot 'build_world_worker.py') --msys $MsysRoot --prepare-dependencies | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Worker dependency preparation stopped. Preserve the package cache and preparation journal; send this log.' }
    $result = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) }
finally { Stop-Transcript | Out-Null; Write-Host "Saved log: $log" }
exit $result
