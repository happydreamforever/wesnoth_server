# Freeze verified installed MINGW64 dependencies; no package download or upgrade.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$null = New-Item -ItemType Directory -Path (Join-Path $repo 'diagnostics') -Force
$log = Join-Path $repo ('diagnostics\world-worker-prepare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
$result = 1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    & $PythonPath -I -B (Join-Path $PSScriptRoot 'build_world_worker.py') --msys $MsysRoot --prepare-dependencies | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Worker dependency preparation stopped. Preserve installed tools and send this log with the dependency audit.' }
    $result = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) }
finally { Stop-Transcript | Out-Null; Write-Host "Saved log: $log" }
exit $result
