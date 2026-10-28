[CmdletBinding()]
param([string]$MsysRoot='D:\Test\wesnoth-setup\msys64', [string]$PythonPath=(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'))
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$null=New-Item -ItemType Directory -Path (Join-Path $repo 'diagnostics') -Force
$report=Join-Path $repo ('diagnostics\world-worker-dependencies-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[guid]::NewGuid().ToString('N')+'.json')
& $PythonPath -I -B (Join-Path $PSScriptRoot 'build_world_worker.py') --msys $MsysRoot --audit $report
$result=$LASTEXITCODE
Write-Host "Dependency report: $report"
Write-Host 'Read-only dependency collection. No packages, services or databases were changed.'
exit $result
