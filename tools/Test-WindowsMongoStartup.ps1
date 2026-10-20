# Windows PowerShell 5.1; check the installed MongoDB using a new disposable data directory.
[CmdletBinding()]
param(
    [AllowEmptyString()]
    [string]$ScratchParent
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$transcriptStarted = $false
$scratch = $null
$result = 1
function Invoke-SelectedPython([string[]]$Arguments) {
    # Windows PowerShell 5.1 wraps redirected native stderr as error records.
    # Print both streams into the transcript, then judge the native exit code.
    $previousPreference = $ErrorActionPreference
    $global:LASTEXITCODE = $null
    try {
        $ErrorActionPreference = 'Continue'
        & $python @Arguments 2>&1 | ForEach-Object { Write-Host $_.ToString() }
    } catch {
        throw 'The selected installed Python could not be executed.'
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($null -eq $global:LASTEXITCODE) { throw 'The selected installed Python could not be executed.' }
    return $global:LASTEXITCODE
}
try {
    $diagnostics = Join-Path $repoRoot 'diagnostics'
    [IO.Directory]::CreateDirectory($diagnostics) | Out-Null
    $runName = 'alliance-mongo-startup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $logPath = Join-Path $diagnostics ($runName + '.txt')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    if ($PSBoundParameters.ContainsKey('ScratchParent')) {
        if ([string]::IsNullOrWhiteSpace($ScratchParent) -or $ScratchParent -notmatch '^[A-Za-z]:[\\/]') {
            throw 'ScratchParent must be a fully qualified Windows drive path to an existing local directory.'
        }
        if (-not (Test-Path -LiteralPath $ScratchParent -PathType Container)) {
            throw 'ScratchParent must be an existing directory; no parent was created.'
        }
        $parentItem = Get-Item -LiteralPath $ScratchParent -Force
        if ($parentItem.PSProvider.Name -ne 'FileSystem') {
            throw 'ScratchParent must be a filesystem directory.'
        }
        $scratch = Join-Path $parentItem.FullName $runName
    } else {
        $scratch = Join-Path (Join-Path $repoRoot 'build') $runName
    }
    $python = Join-Path $repoRoot 'build\alliance-venv\Scripts\python.exe'
    $mongod = Join-Path $repoRoot 'build\alliance-mongodb\bin\mongod.exe'
    $dependencyCheck = Join-Path $PSScriptRoot 'alliance_dependencies.py'
    $fixture = Join-Path $PSScriptRoot 'test_mongodb_startup.py'
    foreach ($path in @($python, $mongod, $dependencyCheck, $fixture)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required installed file is missing or empty: $path"
        }
    }

    $code = Invoke-SelectedPython -Arguments @('-I', '-B', $dependencyCheck, 'check-python')
    if ($code -ne 0) { throw 'Windows x86_64 CPython 3.14.3 is required; no version was changed.' }
    $code = Invoke-SelectedPython -Arguments @('-I', '-B', $dependencyCheck, 'check-installed')
    if ($code -ne 0) { throw 'Installed Alliance dependency verification failed; no MongoDB startup was attempted.' }

    Write-Host ('Testing MongoDB in a new disposable directory: ' + $scratch)
    Write-Host 'The fixture checks local database startup and persistence using the existing installed packages.'
    $arguments = @('-I', '-B', $fixture, '--mongod', $mongod, '--scratch', $scratch, '--report', $reportPath)
    $result = Invoke-SelectedPython -Arguments $arguments
    if ($result -ne 0) { throw "MongoDB startup fixture failed with exit $result. Send the saved log and JSON report if present." }
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf) -or (Get-Item -LiteralPath $reportPath).Length -eq 0) {
        throw 'MongoDB startup fixture did not produce a nonempty JSON report.'
    }
    try { $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw 'MongoDB startup fixture report is not valid JSON.' }
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-mongodb-startup-check' -or $report.status -cne 'passed') {
        throw 'MongoDB startup fixture report does not confirm successful completion.'
    }
    Write-Host 'ALLIANCE MONGODB STARTUP FIXTURE COMPLETE'
    Write-Host 'This verifies only the disposable database startup and persistence. Original game database initialization, accounts and gameplay integration remain pending.'
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $result = 1
} finally {
    if ($transcriptStarted) {
        Write-Host ('Disposable data and logs (if created): ' + $scratch)
        Write-Host ('JSON report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $logPath)
    }
}
exit $result
