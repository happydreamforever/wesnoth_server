# Windows PowerShell 5.1 compatible. Run in a normal, non-administrator window.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\msys64',
    [ValidateRange(1, 65535)][int]$Port = 15000
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $repoRoot 'build\windows-mingw64\bin\wesnothd.exe'
$config = Join-Path $repoRoot 'configs\lan.cfg'
$runtimeRoot = Join-Path $repoRoot 'build\windows-mingw64\run'
$logRoot = Join-Path $repoRoot 'diagnostics'
$originalPath = $env:PATH
$locationChanged = $false
$transcriptStarted = $false
$serverExit = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    foreach ($path in @($binary, $config)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required file is missing or empty: $path. Complete the server build first."
        }
    }
    $dllRoot = Join-Path $MsysRoot 'mingw64\bin'
    if (-not (Test-Path -LiteralPath $dllRoot -PathType Container)) { throw "Missing MINGW64 runtime directory: $dllRoot" }
    $env:PATH = $dllRoot + ';' + $originalPath
    New-Item -ItemType Directory -Path $runtimeRoot, $logRoot -Force | Out-Null
    $logPath = Join-Path $logRoot ('server-run-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    Start-Transcript -LiteralPath $logPath | Out-Null
    $transcriptStarted = $true
    & $binary --version
    if ($LASTEXITCODE -ne 0) { throw 'Server could not load. Return this log; check MINGW64 runtime dependencies.' }
    Push-Location -LiteralPath $runtimeRoot
    $locationChanged = $true
    Write-Host ("Starting guest LAN server on TCP port $Port. Use matching 1.19.26 clients.")
    Write-Host 'Keep this window open. Press Ctrl+C to stop the server.'
    Write-Host ('Server log: ' + $logPath)
    & $binary --config $config --port ([string]$Port) --log-info=server
    $serverExit = $LASTEXITCODE
    if ($serverExit -ne 0) { throw "Server exited with code $serverExit. Return the server log." }
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $serverExit = 1
} finally {
    if ($locationChanged) { Pop-Location }
    $env:PATH = $originalPath
    if ($transcriptStarted) { Stop-Transcript | Out-Null; Write-Host ('Saved log: ' + $logPath) }
}
exit $serverExit
