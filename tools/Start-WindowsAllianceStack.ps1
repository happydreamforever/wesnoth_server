# Windows PowerShell 5.1. Reuse healthy services; start missing ones in separate windows.
[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'),
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [switch]$CheckOnly,
    [switch]$IncludeBattles
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$repo = Split-Path $PSScriptRoot -Parent
$started = $false
$result = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $MsysRoot = Resolve-AllianceRuntimeRoot -Path $MsysRoot
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $helper = Join-Path $PSScriptRoot 'alliance_workflow.py'
    foreach ($file in @($python, $helper)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'The installed workflow runtime is missing.' }
    }
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $stem = 'alliance-workflow-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $log = Join-Path $diagnostics ($stem + '.txt')
    $report = Join-Path $diagnostics ($stem + '.json')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    $started = $true
    Write-Host 'W00: Verify the installed offline tools.'
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed.' }
    & $python -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') check-installed | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned offline dependency check failed.' }
    $arguments = @('-I','-B',$helper,'--runtime',$RuntimeRoot,'--msys',$MsysRoot,'--report',$report)
    if (-not $CheckOnly) { $arguments += '--start' }
    if ($IncludeBattles) { $arguments += '--include-battles' }
    & $python @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Workflow stopped. Follow the named step guidance and send this log plus the JSON report; keep unrelated service windows open.' }
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $log) }
}
exit $result
