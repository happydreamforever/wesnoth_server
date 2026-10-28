# Windows PowerShell 5.1. Serve the normal backend with one bounded, sanitized login trace.
[CmdletBinding()]
param(
    [AllowEmptyString()][string]$RuntimeRoot,
    [AllowEmptyString()][string]$Username = 'UniPlayer'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$reportPath = $null
$result = 1
$failureMessage = 'The login trace could not start. No service was started by this helper.'

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

    $python = Join-Path $repo 'build\alliance-venv-py312\Scripts\python.exe'
    $traceTool = Join-Path $PSScriptRoot 'trace_alliance_login.py'
    $failureMessage = 'The installed Alliance Python or login trace is missing, empty or redirected. No service was started by this helper.'
    foreach ($path in @($python, $traceTool)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw $failureMessage }
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Length -eq 0 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw $failureMessage
        }
    }

    $failureMessage = 'The diagnostic report directory could not be used. No service was started by this helper.'
    $diagnostics = Join-Path $repo 'diagnostics'
    if (Test-Path -LiteralPath $diagnostics) {
        $item = Get-Item -LiteralPath $diagnostics -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw $failureMessage
        }
    } else {
        [IO.Directory]::CreateDirectory($diagnostics) | Out-Null
    }
    $runName = 'alliance-login-trace-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    Write-Host 'Keep MongoDB and the existing bridge running. The previous admin backend must be stopped first.'
    Write-Host 'This starts the normal backend and observes one login request for up to 300 seconds.'
    Write-Host 'Normal login may update attempts or sessions. This trace does not reset credentials.'
    Write-Host ('Sanitized JSON report: ' + $reportPath)
    Write-Host 'Wait for ALLIANCE LOGIN TRACE READY, then make only the requested Android login attempt.'
    Write-Host 'After ALLIANCE LOGIN TRACE COMPLETE, keep this backend window open and send the JSON report.'

    $failureMessage = 'The installed Alliance Python could not run the login trace backend. Send the JSON report if produced.'
    $global:LASTEXITCODE = $null
    # Invoke directly with the inherited console. No transcript, redirection or nested launcher.
    # The backend keeps serving after capture; the report path is already visible above.
    & $python -I -B $traceTool --runtime $RuntimeRoot --username $Username --report $reportPath
    $traceCode = $LASTEXITCODE
    if ($null -eq $traceCode) { throw $failureMessage }
    if ($traceCode -ne 0) {
        if ($traceCode -in @(1, 2)) { $result = $traceCode }
        throw $failureMessage
    }

    $failureMessage = 'The login trace backend stopped without a valid terminal JSON report.'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw $failureMessage }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 32768 -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw $failureMessage }
    $reportJson = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8
    if ($reportJson -notmatch '^\s*\{') { throw $failureMessage }
    $report = $reportJson | ConvertFrom-Json
    $expectedKeys = @('format', 'purpose', 'status', 'outcome', 'username', 'endpoint', 'capture_seconds', 'http_status')
    $actualKeys = @($report.PSObject.Properties.Name)
    if ($actualKeys.Count -ne $expectedKeys.Count) { throw $failureMessage }
    foreach ($key in $expectedKeys) {
        if ($actualKeys -cnotcontains $key) { throw $failureMessage }
    }
    foreach ($key in @('purpose', 'status', 'outcome', 'username', 'endpoint')) {
        if ($report.$key -isnot [string]) { throw $failureMessage }
    }
    if (($report.format -isnot [int] -and $report.format -isnot [long]) -or $report.format -ne 1 -or
        $report.purpose -cne 'wesnoth-alliance-login-trace' -or $report.status -cne 'completed' -or
        $report.username -cne $Username -or $report.endpoint -cne '127.0.0.1:18765' -or
        ($report.capture_seconds -isnot [int] -and $report.capture_seconds -isnot [long]) -or
        $report.capture_seconds -ne 300) { throw $failureMessage }
    $allowedOutcomes = @(
        'service_authorization_rejected', 'different_username', 'invalid_input', 'account_missing',
        'invalid_stored_hash', 'password_mismatch', 'password_verification_failed', 'account_ineligible', 'session_state_changed',
        'rate_limited', 'login_accepted', 'backend_unavailable', 'backend_error', 'request_rejected',
        'request_failed', 'authorization_or_credentials_rejected', 'capture_timeout_no_request',
        'capture_timeout_in_progress', 'capture_cancelled'
    )
    if ($allowedOutcomes -cnotcontains $report.outcome) { throw $failureMessage }
    if ($null -ne $report.http_status -and
        (($report.http_status -isnot [int] -and $report.http_status -isnot [long]) -or
         $report.http_status -lt 100 -or $report.http_status -gt 599)) { throw $failureMessage }
    Write-Host 'ALLIANCE LOGIN TRACE REPORT VERIFIED'
    Write-Host 'Trace completion is not a successful-login assertion. Use the sanitized report outcome.'
    $result = 0
} catch {
    # Never reflect raw exceptions or malformed report contents into the console.
    Write-Host ('ERROR: ' + $failureMessage) -ForegroundColor Red
} finally {
    if ($null -ne $reportPath) { Write-Host ('JSON report (if produced): ' + $reportPath) }
}
exit $result
