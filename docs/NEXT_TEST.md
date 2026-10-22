# Check the reported plan state before practice

The exact screen for plan `100599c9-610f-4d81-b8bb-1cb1b79e5f27` now confirms `State: cancelled`. It still says the saved lineups match current teams and shows UniRival's saved Ready flag despite the reported departure. Practice A–H is paused. Keep MongoDB, the admin service, account bridge and the current LDPlayer app open. Leave the existing team and plan exactly as they are; do not repeat leave/cancel, reapply, restore members or create another plan during collection.

The current backend intentionally keeps the saved lineup/readiness history. A fresh read should nevertheless show changed validity after a selected player leaves and state=cancelled after successful cancellation. The client also has a reproduced stale first-detail display race. The report below distinguishes stored state/current membership from saved consent; it does not yet prove the cause of the Windows discrepancy.

## 1. Pull the diagnostic and workflow records

Temporarily connect to GitHub and run in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
}
```

Return to disconnected WAN with local Ethernet retained. These new scripts read the existing local database directly; no service restart is needed. Client changes in this delivery are documentation only.

## 2. Collect the existing plan and membership facts

Run in a separate PowerShell window while the three services stay open:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop

    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is missing. Stop and send this output.'
    }
    $runtimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'
    $python = Join-Path (Get-Location).Path 'build\alliance-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'The existing Alliance Python is missing. Stop and send this output.'
    }
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $report = Join-Path (Get-Location).Path ('diagnostics\alliance-plan-state-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.json')

    & $python -I -B '.\tools\check_alliance_plan.py' `
        --runtime $runtimeRoot --username 'UniPlayer' `
        --battle-id '100599c9-610f-4d81-b8bb-1cb1b79e5f27' --report $report
    if ($LASTEXITCODE -ne 0) {
        throw 'Plan state collection was incomplete. Send the console output and saved JSON report if present.'
    }
}
```

Expected completion marker: `ALLIANCE PLAN STATE COLLECTED`, with the saved report path. This means collection succeeded, not that the reported bug is fixed. There is no password prompt. The collector does not load `.env`, log in, reset passwords, clear readiness, modify teams/plans or initialize MongoDB. It reads only the owned local127.0.0.1:27018/wesnoth_game configuration and writes the new report outside the runtime.

The bounded report includes plan IDs/state/validity, saved side/player/leader/readiness information and current team membership. `saved_ready` is historical consent, not proof that a player still belongs to the team or may start the plan. This command selects only the exact plan shown on screen, avoiding confusion between plans with identical team names. Without an exact ID, the helper is limited to the latest10 relevant plans and reports whether more exist. No unbounded collection or automatic repair is performed. Derived validity comes from the current disk source; current service/bridge code and installed APK are not inspected by this collector.

## Return the result

Send the new `diagnostics/alliance-plan-state-*.json`. The exact screen plan ID and cancelled state have already been received; no repeat screen check is needed. Also report whether WAN stayed disconnected during collection. Do not send passwords, private runtime files or `.env`. Stop here; wait for the report review before further team changes or practice testing. The previous1192609 practice instructions remain in Git history at client1bc4e3b/server5239c21; they are not the current next step.
