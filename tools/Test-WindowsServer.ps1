# Windows PowerShell 5.1; uses the Python installation confirmed by inventory.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe')
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $repoRoot 'build\windows-mingw64\bin\wesnothd.exe'
$test = Join-Path $repoRoot 'tests\test_server_protocol.py'
$originalPath = $env:PATH
$testExit = 1
try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    foreach ($path in @($PythonPath, $binary, $test)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required file is missing or empty: $path"
        }
    }
    $dllRoot = Join-Path $MsysRoot 'mingw64\bin'
    if (-not (Test-Path -LiteralPath $dllRoot -PathType Container)) { throw "Missing MINGW64 runtime directory: $dllRoot" }
    $env:PATH = $dllRoot + ';' + $originalPath
    $logRoot = Join-Path $repoRoot 'diagnostics'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logPath = Join-Path $logRoot ('server-protocol-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    & $PythonPath --version
    if ($LASTEXITCODE -ne 0) { throw 'Python could not run.' }
    & $PythonPath $test --server $binary --log-path $logPath
    $testExit = $LASTEXITCODE
    if ($testExit -ne 0) { throw "Protocol test failed with exit $testExit. Return the complete output and saved log." }
    Write-Host ('Protocol test log: ' + $logPath)
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $testExit = 1
} finally {
    $env:PATH = $originalPath
}
exit $testExit
