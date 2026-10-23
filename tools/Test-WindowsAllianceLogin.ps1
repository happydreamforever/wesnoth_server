# Windows PowerShell 5.1. One read-only local password diagnostic with hidden console input.
[CmdletBinding()]
param(
    [AllowEmptyString()][string]$RuntimeRoot,
    [AllowEmptyString()][string]$Username = 'UniPlayer'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$reportPath = $null
$result = 1
$failureMessage = 'The login diagnostic could not start. No service was changed.'

try {
    $failureMessage = 'This helper requires Windows.'
    if ($env:OS -ne 'Windows_NT') { throw $failureMessage }
    $failureMessage = 'Username must contain 3 to 24 ASCII letters, digits or underscores.'
    if ($Username -cnotmatch '\A[A-Za-z0-9_]{3,24}\z') { throw $failureMessage }

    $failureMessage = 'The runtime path helper is missing or could not be loaded.'
    $common = Join-Path $PSScriptRoot 'Alliance-Common.ps1'
    if (-not (Test-Path -LiteralPath $common -PathType Leaf)) { throw $failureMessage }
    . $common
    $failureMessage = 'LOCALAPPDATA is missing; the existing profile runtime could not be selected.'
    if (-not $PSBoundParameters.ContainsKey('RuntimeRoot')) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw $failureMessage }
        $RuntimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'
    }
    $failureMessage = 'RuntimeRoot must be an existing local directory without redirected path components.'
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    if (-not (Test-Path -LiteralPath $RuntimeRoot -PathType Container)) { throw $failureMessage }

    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $diagnostic = Join-Path $PSScriptRoot 'check_alliance_login.py'
    $failureMessage = 'The installed Alliance Python or login diagnostic is missing, empty or redirected. No service was changed.'
    foreach ($path in @($python, $diagnostic)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw $failureMessage }
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Length -eq 0 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw $failureMessage
        }
    }

    $failureMessage = 'The diagnostic report directory could not be used. No service was changed.'
    $diagnostics = Join-Path $repo 'diagnostics'
    if (Test-Path -LiteralPath $diagnostics) {
        $item = Get-Item -LiteralPath $diagnostics -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw $failureMessage
        }
    } else {
        [IO.Directory]::CreateDirectory($diagnostics) | Out-Null
    }
    $runName = 'alliance-login-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    Write-Host 'Keep the existing services open. Enter the player password only at the hidden console prompt.'
    Write-Host 'This diagnostic does not sign in, reset credentials or change account data.'

    $failureMessage = 'The installed Alliance Python could not complete the login diagnostic. Send the JSON report if produced.'
    $global:LASTEXITCODE = $null
    # Keep this a direct statement: getpass requires the inherited console.
    # Do not capture output or add a pipeline, transcript or stream redirection.
    & $python -I -B $diagnostic --runtime $RuntimeRoot --username $Username --report $reportPath
    $diagnosticCode = $LASTEXITCODE
    if ($null -eq $diagnosticCode) { throw $failureMessage }
    if ($diagnosticCode -ne 0) {
        if ($diagnosticCode -in @(1, 2)) { $result = $diagnosticCode }
        throw $failureMessage
    }

    $failureMessage = 'The login diagnostic did not produce a valid completed JSON report.'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw $failureMessage }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 32768 -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw $failureMessage }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-alliance-login-check' -or
        $report.status -cne 'completed' -or $report.username -cne $Username -or
        $report.endpoint -cne '127.0.0.1:27018' -or $report.database -cne 'wesnoth_game' -or
        $report.database_writes -isnot [bool] -or $report.database_writes) { throw $failureMessage }
    $completedChecks = @{
        account_missing = 'not_checked'; account_ineligible = 'not_checked'
        invalid_stored_hash = 'invalid_hash'; unsupported_stored_hash = 'unsupported_hash'
        password_match = 'match'; password_mismatch = 'mismatch'
    }
    if ($completedChecks.Keys -cnotcontains $report.outcome -or
        $report.password_check -cne $completedChecks[$report.outcome]) { throw $failureMessage }
    Write-Host 'ALLIANCE LOGIN DIAGNOSTIC REPORT VERIFIED'
    Write-Host 'Diagnostic completion does not mean a successful login. Send the sanitized JSON report.'
    $result = 0
} catch {
    # Never reflect raw exceptions or malformed report contents into the console.
    Write-Host ('ERROR: ' + $failureMessage) -ForegroundColor Red
} finally {
    if ($null -ne $reportPath) { Write-Host ('JSON report (if produced): ' + $reportPath) }
}
exit $result
