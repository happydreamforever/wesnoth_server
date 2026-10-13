# Windows PowerShell 5.1 compatible. Local metadata only; no connection or firewall changes.
[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 15000)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$logPath = $null
$result = 1
try {
    $logRoot = Join-Path $repoRoot 'diagnostics'
    $null = New-Item -ItemType Directory -Path $logRoot -Force
    $logPath = Join-Path $logRoot ('lan-address-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    & {
        if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
        "SERVER LISTENERS ON TCP $Port"
        $listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq $Port | ForEach-Object {
            $name = 'Unknown'
            try { $name = (Get-Process -Id $_.OwningProcess -ErrorAction Stop).ProcessName } catch {}
            [pscustomobject]@{LocalAddress=$_.LocalAddress; LocalPort=$_.LocalPort; PID=$_.OwningProcess; Process=$name}
        })
        $listeners | Format-Table -AutoSize | Out-String -Width 200

        'ACTIVE PHYSICAL WINDOWS IPv4 ADDRESSES'
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4)
        $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
        $rows = @(
            foreach ($adapter in @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up')) {
                foreach ($address in @($addresses | Where-Object {
                    $_.InterfaceIndex -eq $adapter.InterfaceIndex -and $_.AddressState -eq 'Preferred' -and
                    $_.IPAddress -notmatch '^(127\.|169\.254\.|0\.)'
                })) {
                    $category = (@($profiles | Where-Object InterfaceIndex -eq $adapter.InterfaceIndex |
                        Select-Object -ExpandProperty NetworkCategory -Unique) -join ',')
                    if (-not $category) { $category = 'Unknown' }
                    [pscustomobject]@{Adapter=$adapter.Name; IPv4=$address.IPAddress; Profile=$category}
                }
            }
        )
        $rows | Format-Table -AutoSize | Out-String -Width 200
        if ($listeners.Count -eq 0) { throw "No listener on TCP $Port. Check the server window and return both logs." }
        if ($rows.Count -eq 0) { throw 'No active physical LAN IPv4 address. Keep the local Wi-Fi or Ethernet connection and return this log.' }

        $targets = @(
            foreach ($row in $rows) {
                $matching = @($listeners | Where-Object {
                    $_.Process -eq 'wesnothd' -and ($_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq $row.IPv4)
                })
                if ($matching.Count -gt 0) {
                    [pscustomobject]@{Adapter=$row.Adapter; Server=($row.IPv4 + ':' + $Port); Profile=$row.Profile}
                }
            }
        )
        if ($targets.Count -eq 0) {
            throw "No wesnothd IPv4 listener covers these LAN addresses on TCP $Port. Return this report and the server log."
        }
        'SERVER ADDRESSES TO TRY IN THE ANDROID GAME'
        $targets | Format-Table -AutoSize | Out-String -Width 200
        'LAN ADDRESS REPORT COMPLETE'
        'Local metadata only. Android connectivity is untested; joining the server tests the actual connection.'
    } 2>&1 | Tee-Object -FilePath $logPath
    $result = 0
} catch {
    $message = 'ERROR: ' + $_.Exception.Message
    if ($logPath) { $message | Tee-Object -FilePath $logPath -Append } else { Write-Host $message }
} finally {
    if ($logPath) { Write-Host ('Saved log: ' + $logPath) }
}
exit $result
