# Prepare only the Python 3.12 wheels; existing MongoDB is reused.
[CmdletBinding()]
param(
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    [switch]$Download
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$diagnostics = Join-Path $repo 'diagnostics'
$null = New-Item -ItemType Directory -Path $diagnostics -Force
$log = Join-Path $diagnostics ('alliance-python312-prepare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
$code = 1
Start-Transcript -LiteralPath $log -NoClobber | Out-Null
try {
    $arguments = @('-I', '-B', (Join-Path $PSScriptRoot 'alliance_dependencies.py'), 'prepare-python312')
    if ($Download) { $arguments += '--download' }
    & $PythonPath @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 cache preparation stopped. Preserve existing files and send this log.' }
    $code = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) }
finally { Stop-Transcript | Out-Null; Write-Host "Saved log: $log" }
exit $code
