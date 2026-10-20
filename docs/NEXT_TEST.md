# Next Windows step: local MongoDB startup and persistence check

The user now prioritizes the local database for Alliance Battle. MongoDB Community Edition is free and can run entirely offline ([official overview](https://www.mongodb.com/products/self-managed/community-edition)). Keep our pinned version8.0.32; the MongoDB archive and all17 Python packages were already downloaded, verified and installed on this Windows computer. No new installer, subscription or version upgrade is required for this step.

The earlier failure occurred when WiredTiger tried to rename/delete its metadata during startup. Reinstalling does not establish that this file-sharing problem is fixed. The partial game database and crash evidence must be preserved. The new diagnostic starts the existing executable against a separate empty test directory, verifies a synthetic write/read, shuts down cleanly, restarts that test database and verifies its data survived. It never opens the partial game database or internet `.env` connection.

## 1. Pull this update while temporarily connected

Run in a normal PowerShell window:

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

## 2. Disconnect WAN, retain local Ethernet, then run the isolated check

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsMongoStartup.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'MongoDB startup check failed. Send the saved text and JSON reports if present.'
    }
}
```

The helper verifies the existing isolated Python3.14.3 environment, pinned package versions and installed MongoDB file hashes before invoking MongoDB. Installation is not repeated. A new retained `build\alliance-mongo-startup-<runid>` contains only disposable test data/logs; the helper prints the exact path. Each process is limited to127.0.0.1 on a temporary port, separate from the real game database port27018. Only the helper's own child process can be stopped. This standalone diagnostic deliberately uses synthetic data without game accounts; it is not the final authenticated replica-set deployment.

## Expected result and what to return

Expect installed-environment verification, MongoDB8.0.32, successful startup, journaled write/read, clean shutdown, restart with the same test record, and another clean shutdown. Final markers:

```text
ALLIANCE MONGODB STARTUP CHECK PASSED
ALLIANCE MONGODB STARTUP FIXTURE COMPLETE
```

Return the matching new **`diagnostics\alliance-mongo-startup-*.txt` and `.json`** files, whether the run passes or fails, and confirm WAN was disconnected. If failure happens before JSON creation, return the text log. Keep the test directory, process logs and any dumps; the JSON identifies the failed phase. If MongoDB fails after launch, also return the new test directory's `logs\mongodb-1.log` (or `mongodb-2.log` for a restart failure), if present. A Windows crash may add a timestamped dump beside installed mongod.exe; keep it locally rather than attaching it. Do not send old runtime credentials, key files or `.env`.

A failure stops this test; do not repeatedly retry or delete/repair the old database. A pass proves fresh-data startup and clean-restart persistence only. After reviewing the result, continue with guarded initialization/resumption of the real authenticated game database, its administrator, transaction check and local admin website. Those later commands are documented as reference in ALLIANCE_RUNTIME.md and are not the current step.
