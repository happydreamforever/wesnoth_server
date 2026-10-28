# Create a separate verified Python 3.12 environment with all services stopped.
[CmdletBinding()]
param([string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$diagnostics = Join-Path $repo 'diagnostics'
$null = New-Item -ItemType Directory -Path $diagnostics -Force
$log = Join-Path $diagnostics ('alliance-python312-install-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
$code = 1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    Write-Host 'Keep all five game services stopped. The old Python environment and database are retained.'
    & $PythonPath -I -B (Join-Path $PSScriptRoot 'alliance_dependencies.py') install-python312 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 transition stopped. Keep both environments and the transition journal; send this log.' }
    $code = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) }
finally { Stop-Transcript | Out-Null; Write-Host "Saved log: $log" }
exit $code
