# Save one combined user-observed acceptance report without credentials or runtime files.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$BatchId,
    [Parameter(Mandatory=$true)][ValidateSet('Disconnected','Available','NotRecorded')][string]$WanStatus,
    [string[]]$PassedSteps = @(),
    [string[]]$FailedSteps = @(),
    [string[]]$NotRunSteps = @()
)
$ErrorActionPreference = 'Stop'
$result = 1
try {
    $seen = @{}
    $steps = @()
    foreach ($group in @(
        @{ Names=$PassedSteps; Status='passed' },
        @{ Names=$FailedSteps; Status='failed' },
        @{ Names=$NotRunSteps; Status='not_run' }
    )) {
        foreach ($entry in $group.Names) {
            # Comma-separated strings also work through powershell.exe -File,
            # whose native argument boundary cannot preserve PowerShell arrays.
            foreach ($part in $entry.Split(',')) {
                $name = $part.Trim()
                if ($name -cnotmatch '^[A-Z][0-9]{0,2}$' -or $seen.ContainsKey($name)) {
                    throw 'Use each uppercase step identifier once, for example A, B, C or W01.'
                }
                $seen[$name] = $true
                $steps += [ordered]@{ id=$name; status=$group.Status }
            }
        }
    }
    if ($steps.Count -eq 0 -or $steps.Count -gt 100) { throw 'Supply between 1 and 100 reported steps.' }
    $repo = Split-Path $PSScriptRoot -Parent
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $report = Join-Path $diagnostics ('alliance-acceptance-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.json')
    $record = [ordered]@{
        format=1; purpose='wesnoth-alliance-user-acceptance'; batch_id=$BatchId
        recorded_at_utc=[DateTime]::UtcNow.ToString('o'); evidence='user_reported'
        wan_status=$WanStatus; steps=$steps
        scope='User observations only; no build, network, database or gameplay check was executed by this helper.'
    }
    $json = ($record | ConvertTo-Json -Depth 5) + [Environment]::NewLine
    $stream = [IO.File]::Open($report, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $encoding = New-Object Text.UTF8Encoding($false)
        $bytes = $encoding.GetBytes($json)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
    } finally { $stream.Dispose() }
    Write-Host ('ALLIANCE ACCEPTANCE REPORT SAVED: ' + $report)
    Write-Host ('Batch: ' + $BatchId + '; WAN: ' + $WanStatus + '; reported steps: ' + $steps.Count)
    Write-Host 'Send this JSON and any failing step message. Do not send passwords or private runtime/backup files.'
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
}
exit $result
