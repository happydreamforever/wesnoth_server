# Shared by the Alliance helpers; Windows PowerShell 5.1 compatible.
function Invoke-AllianceCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('prepare','install','init','database','serve','check')][string]$Command,
        [string]$PythonPath,
        [switch]$Download
    )
    $ErrorActionPreference = 'Stop'
    $repoRoot = Split-Path $PSScriptRoot -Parent
    $transcriptStarted = $false
    $locationChanged = $false
    $result = 1
    try {
        if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
        if ($Command -in @('prepare','install')) {
            if (-not $PythonPath) {
                $PythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
            }
        } else {
            if ($PythonPath) { throw 'Runtime commands use the isolated Alliance virtual environment.' }
            $PythonPath = Join-Path $repoRoot 'build\alliance-venv\Scripts\python.exe'
        }
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "Missing Python executable: $PythonPath. Complete the preceding preparation/install step."
        }
        & $PythonPath -I (Join-Path $repoRoot 'tools\alliance_dependencies.py') check-python | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Windows x86_64 CPython 3.14.3 is required; no version was changed.' }
        Push-Location -LiteralPath $repoRoot
        $locationChanged = $true
        # init uses getpass interactively; do not capture the password prompt.
        if ($Command -ne 'init') {
            $diagnostics = Join-Path $repoRoot 'diagnostics'
            $null = New-Item -ItemType Directory -Path $diagnostics -Force
            $logPath = Join-Path $diagnostics ('alliance-' + $Command + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
            Start-Transcript -LiteralPath $logPath | Out-Null
            $transcriptStarted = $true
        }
        if ($Command -in @('prepare','install')) {
            $arguments = @('-I', (Join-Path $repoRoot 'tools\alliance_dependencies.py'), $Command)
            if ($Download) { $arguments += '--download' }
        } else {
            if ($Download) { throw 'Only preparation can download dependencies.' }
            & $PythonPath -I (Join-Path $repoRoot 'tools\alliance_dependencies.py') check-installed | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'The pinned Alliance environment check failed; runtime was not started.' }
            $arguments = @('-E','-s','-m','alliance','--runtime', (Join-Path $repoRoot 'runtime\alliance'))
            if ($Command -in @('init','database')) {
                $mongod = Join-Path $repoRoot 'build\alliance-mongodb\bin\mongod.exe'
                if (-not (Test-Path -LiteralPath $mongod -PathType Leaf)) { throw 'Pinned MongoDB executable is missing. Complete the offline installation step.' }
                $arguments += @('--mongod', $mongod)
            }
            $arguments += $Command
        }
        & $PythonPath @arguments | Out-Host
        $result = $LASTEXITCODE
        if ($result -ne 0) { throw "Alliance $Command failed with exit $result." }
    } catch {
        Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
        $result = 1
    } finally {
        if ($transcriptStarted) {
            Stop-Transcript | Out-Null
            Write-Host ('Saved log: ' + $logPath)
        }
        if ($locationChanged) { Pop-Location }
    }
    return $result
}
