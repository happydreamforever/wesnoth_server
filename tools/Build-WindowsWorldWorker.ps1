[CmdletBinding()]
param([string]$MsysRoot='D:\Test\wesnoth-setup\msys64', [string]$PythonPath=(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'), [string]$CMakePath='C:\Program Files\CMake\bin\cmake.exe', [string]$GameDataRoot='D:\Test\wesnoth-setup\gamedata-1.19.26', [switch]$PreservePreviousBuild, [string]$NinjaReportPath)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$null=New-Item -ItemType Directory -Path (Join-Path $repo 'diagnostics') -Force
$log=Join-Path $repo ('diagnostics\world-worker-build-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[guid]::NewGuid().ToString('N')+'.txt')
$result=1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    if($PSBoundParameters.ContainsKey('NinjaReportPath')) {
        if(-not $PreservePreviousBuild -or [string]::IsNullOrWhiteSpace($NinjaReportPath)) {
            throw 'Ninja recovery requires -PreservePreviousBuild and the saved diagnostic JSON path.'
        }
    }
    $arguments=@('-I','-B',(Join-Path $PSScriptRoot 'build_world_worker.py'),'--msys',$MsysRoot,'--cmake',$CMakePath,'--game-data',$GameDataRoot)
    if($PreservePreviousBuild){$arguments+='--preserve-previous'}
    if($PSBoundParameters.ContainsKey('NinjaReportPath')){$arguments+=@('--ninja-report',$NinjaReportPath)}
    & $PythonPath @arguments | Out-Host
    if($LASTEXITCODE -ne 0){throw 'Full native World worker build stopped. Send this log and the compiler-check report if produced.'}
    $result=0
} catch {Write-Host ('ERROR: '+$_.Exception.Message)} finally {Stop-Transcript | Out-Null;Write-Host "Saved log: $log"}
exit $result
