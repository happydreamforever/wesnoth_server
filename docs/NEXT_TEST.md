# Next Windows step: MongoDB startup and persistence under the profile folder

The returned transcript confirms20 synthetic file replacements and exit0 under `C:\Users\Uni\AppData\Local\WesnothAllianceStorageCheck`. The per-event JSONL was not attached and WAN status was not reported. No repeat file probe is needed: the next check runs the actual installed MongoDB8.0.32 against new disposable data under that same parent.

This is a location change for the existing startup fixture. It does not establish that D: is defective or that the earlier conflict is resolved. The original partial game database and all failed-test data remain intact. No installer, version change, data migration or Windows service/security modification is needed.

## 1. Pull the small helper update while temporarily connected

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) {
            throw "Pull failed for $name. Stop and send the output."
        }
    }
}
```

## 2. Disconnect WAN, keep local Ethernet, then run once

Use normal PowerShell under the same Windows account as the successful file test:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is missing. Stop and send this output.'
    }
    $parent = Join-Path $env:LOCALAPPDATA 'WesnothAllianceStorageCheck'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsMongoStartup.ps1' `
        -ScratchParent $parent

    if ($LASTEXITCODE -ne 0) {
        throw 'MongoDB profile startup check failed. Send the new saved text and JSON reports if present.'
    }
}
```

The helper requires the chosen parent to be an existing directory with a drive-qualified Windows filesystem path; it stops if missing rather than choosing another location. It uses a new timestamp/GUID child `alliance-mongo-startup-<runid>` under that parent, so the earlier `mongo-file-probe-nj9j87g3` and all previous database directories remain unchanged. The existing Python3.14.3 environment, package/Mongo file pins and MongoDB8.0.32 executable are verified again before startup; they stay installed under D:\Test. The paired text/JSON reports still go under the repository's diagnostics folder.

The unchanged Python fixture creates and restricts only its new child, starts its owned MongoDB on a temporary loopback port, verifies process identity, writes/reads a journaled synthetic record, shuts down cleanly, restarts the same disposable data and reads that record again, then stops. It never opens runtime/alliance or the internet `.env` URL. A failure stops the fixture and retains logs. A Windows crash may add a timestamped dump beside installed mongod.exe; keep dumps locally.

## Expected result and what to return

The printed disposable directory must be under `C:\Users\Uni\AppData\Local\WesnothAllianceStorageCheck`, not the old repository build directory. Expect these markers:

```text
PASS journaled_write
PASS persisted_read
PASS final_clean_shutdown
ALLIANCE MONGODB STARTUP CHECK PASSED
ALLIANCE MONGODB STARTUP FIXTURE COMPLETE
```

Send both new `diagnostics\alliance-mongo-startup-*.txt` and `.json`, and confirm WAN was disconnected. If it fails before JSON creation, send the text log. For a failure after MongoDB launches, also attach the new directory's `logs\mongodb-1.log` and `logs\process-1.log` (or the corresponding `-2.log` files if restart failed). Do not repeat the failed run before review.

A full pass establishes only this disposable standalone database's startup, journaled write/read and clean-restart persistence. Authenticated replica-set initialization, transactions, local administrator/website and Android accounts remain pending. Review the report before selecting production storage or initializing the real game runtime.
