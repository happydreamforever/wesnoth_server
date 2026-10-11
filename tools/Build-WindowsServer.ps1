# Windows PowerShell 5.1 compatible; no downloads or package changes.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\msys64',
    [string]$CMakePath = 'C:\Program Files\CMake\bin\cmake.exe',
    [string]$NinjaPath = '',
    [ValidateSet('Release', 'Debug', 'RelWithDebInfo')][string]$BuildType = 'Release',
    [ValidateRange(1, 64)][int]$Jobs = 2
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$logRoot = Join-Path $repoRoot 'diagnostics'
$transcriptStarted = $false
$buildExit = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows. Use CMake directly for Linux validation.' }
    if (-not $NinjaPath) { $NinjaPath = Join-Path $MsysRoot 'ucrt64\bin\ninja.exe' }
    $bash = Join-Path $MsysRoot 'usr\bin\bash.exe'
    $scriptPath = Join-Path $PSScriptRoot 'build-windows-server.sh'
    foreach ($path in @($bash, $CMakePath, $NinjaPath, $scriptPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required file is missing or empty: $path"
        }
    }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logPath = Join-Path $logRoot ('server-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    Start-Transcript -LiteralPath $logPath | Out-Null
    $transcriptStarted = $true
    Write-Host 'Building the upstream 1.19.26 native guest LAN server.'
    Write-Host ('CMake: ' + $CMakePath)
    Write-Host ('Native Ninja build tool: ' + $NinjaPath)
    Write-Host ('Compiler/dependency root: ' + (Join-Path $MsysRoot 'mingw64'))
    # Passing the script as an argument avoids nested shell command quoting.
    & $bash --noprofile --norc ($scriptPath.Replace('\', '/')) $CMakePath $NinjaPath $BuildType ([string]$Jobs)
    $buildExit = $LASTEXITCODE
    if ($buildExit -ne 0) { throw "Build failed with exit $buildExit. Return the complete build log." }
    Write-Host ('Build log: ' + $logPath)
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $buildExit = 1
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $logPath) }
}
exit $buildExit
