# Windows PowerShell 5.1; provisions a separate identity and tests Python loopback TLS.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    [string]$ServerAddress = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$Port = 15001
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$originalPath = $env:PATH
$transcriptStarted = $false
$result = 1
try {
    $diagnostics = Join-Path $repoRoot 'diagnostics'
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $runName = 'alliance-transport-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $logPath = Join-Path $diagnostics ($runName + '.txt')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    $dllRoot = Join-Path $MsysRoot 'mingw64\bin'
    $openssl = Join-Path $dllRoot 'openssl.exe'
    $pythonCheck = Join-Path $repoRoot 'tools\alliance_dependencies.py'
    $transport = Join-Path $repoRoot 'tools\alliance_transport.py'
    foreach ($path in @($PythonPath, $pythonCheck, $transport, $openssl)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required file is missing or empty: $path"
        }
    }

    $env:PATH = $dllRoot + ';' + $originalPath
    & $PythonPath -I -B $pythonCheck check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Windows x86_64 CPython 3.12.10 is required; no version was changed.' }

    Write-Host 'Preparing a separate TLS identity and testing it with Python on loopback.'
    $arguments = @('-I', '-B', $transport,
        '--identity-root', (Join-Path $repoRoot 'runtime\alliance-transport'),
        '--server-address', $ServerAddress,
        '--port', ([string]$Port),
        '--openssl', $openssl,
        '--report', $reportPath,
        '--require-openssl-version', '3.6.3')
    & $PythonPath @arguments | Out-Host
    $result = $LASTEXITCODE
    if ($result -ne 0) { throw "Alliance transport fixture failed with exit $result. Return the saved log and report if present." }
    Write-Host 'ALLIANCE TRANSPORT FIXTURE COMPLETE'
    Write-Host 'This checks Python loopback TLS; native game account integration and Android acceptance remain pending.'
    Write-Host ('Transport report: ' + $reportPath)
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $result = 1
} finally {
    $env:PATH = $originalPath
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $logPath)
    }
}
exit $result
