# Windows PowerShell 5.1. Read-only checks of the existing local Alliance backend.
[CmdletBinding()]
param([AllowEmptyString()][string]$RuntimeRoot)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$transcriptStarted = $false
$result = 1

function Get-BackendListenerMetadata {
    try {
        $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -in @(18765, 27018) })
        $rows = @(
            foreach ($listener in $listeners) {
                $name = 'Unknown'
                try {
                    $candidate = (Get-Process -Id $listener.OwningProcess -ErrorAction Stop).ProcessName
                    if ($candidate -cmatch '^[A-Za-z0-9_.-]{1,64}$') { $name = $candidate }
                } catch {}
                [pscustomobject]@{
                    LocalAddress = $listener.LocalAddress
                    LocalPort = $listener.LocalPort
                    PID = $listener.OwningProcess
                    Process = $name
                }
            }
        )
        return @{Available = $true; Rows = $rows}
    } catch {
        return @{Available = $false; Rows = @()}
    }
}

function Invoke-BackendDiagnostic([string[]]$Arguments) {
    # PowerShell 5.1 can wrap native stderr as error records. Capture both
    # streams, then use the diagnostic's exit code to determine its result.
    $previousPreference = $ErrorActionPreference
    $global:LASTEXITCODE = $null
    try {
        $ErrorActionPreference = 'Continue'
        & $python @Arguments 2>&1 | ForEach-Object { Write-Host $_.ToString() }
    } catch {
        throw 'The installed Alliance Python could not be executed.'
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($null -eq $global:LASTEXITCODE) {
        throw 'The installed Alliance Python did not return an exit code.'
    }
    return $global:LASTEXITCODE
}

try {
    $diagnostics = Join-Path $repo 'diagnostics'
    [IO.Directory]::CreateDirectory($diagnostics) | Out-Null
    $runName = 'alliance-backend-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $logPath = Join-Path $diagnostics ($runName + '.txt')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    # PowerShell can transcribe caught cmdlet exceptions. Collect optional
    # metadata first, retaining only these columns and a fixed failure flag.
    $listenerMetadata = $null
    if ($env:OS -eq 'Windows_NT') { $listenerMetadata = Get-BackendListenerMetadata }
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    . (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
    if (-not $PSBoundParameters.ContainsKey('RuntimeRoot')) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
        $RuntimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'
    }
    $RuntimeRoot = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $diagnostic = Join-Path $PSScriptRoot 'check_alliance_backend.py'
    foreach ($path in @($python, $diagnostic)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'The installed Alliance Python or backend diagnostic is missing. No service was changed.'
        }
        if ((Get-Item -LiteralPath $path -Force).Length -eq 0) {
            throw 'The installed Alliance Python or backend diagnostic is empty. No service was changed.'
        }
    }

    Write-Host 'CURRENT LOCAL LISTENERS ON TCP 18765 AND 27018'
    if (-not $listenerMetadata.Available) {
        Write-Host 'WARNING: Listener metadata could not be collected; continuing with the backend HTTP check.'
    } elseif ($listenerMetadata.Rows.Count -eq 0) {
        Write-Host 'No listeners were reported on TCP 18765 or 27018.'
    } else {
        $listenerMetadata.Rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    }

    Write-Host 'Checking the existing backend on 127.0.0.1:18765. Keep the database and admin windows open.'
    $result = Invoke-BackendDiagnostic -Arguments @('-I', '-B', $diagnostic, '--runtime', $RuntimeRoot, '--report', $reportPath)
    if ($result -ne 0) {
        throw 'Alliance backend check failed. Send the saved text and JSON reports if present.'
    }
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        throw 'The backend diagnostic did not produce a JSON report.'
    }
    $item = Get-Item -LiteralPath $reportPath -Force
    if ($item.Length -eq 0 -or $item.Length -gt 32768 -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The backend diagnostic report has an unexpected size or file type.'
    }
    try { $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw 'The backend diagnostic report could not be read or parsed.' }
    if ($report.format -ne 1 -or $report.purpose -cne 'wesnoth-alliance-backend-check' -or
        $report.status -cne 'passed') {
        throw 'The backend diagnostic report does not confirm successful completion.'
    }
    Write-Host 'ALLIANCE BACKEND DIAGNOSTIC COMPLETE'
    Write-Host 'Existing backend health only. Account listener startup, Android login and team gameplay are not tested.'
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $result = 1
} finally {
    if ($transcriptStarted) {
        Write-Host ('JSON report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $logPath)
    }
}
exit $result
