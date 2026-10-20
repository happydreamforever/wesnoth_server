# Next Windows test: initialize the game database in the profile folder

The returned text and JSON reports confirm all eight MongoDB startup/persistence checks passed under your Windows profile. Both processes stopped with exit0. This is actual Windows database evidence; authenticated game setup and administrator login have not yet passed. The user now confirms WAN was disconnected while local Ethernet stayed connected during that test. The reports themselves do not measure WAN connectivity.

Use the installed MongoDB8.0.32 and Python3.14.3 environment. This step creates a new persistent runtime at `%LOCALAPPDATA%\WesnothAlliance\runtime` (normally `C:\Users\Uni\AppData\Local\WesnothAlliance\runtime`). It does not reuse the disposable test data or the failed repository runtime. Keep all those directories intact. No download, installer, game build or repeated startup fixture is needed.

## 1. Pull the update while temporarily connected

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

## 2. Disconnect WAN, keep local Ethernet, then initialize once

Use normal PowerShell under the same Windows account as the successful test. Leave other MongoDB instances stopped; the helper refuses an occupied port rather than stopping another database. Run this block without adding a transcript or redirecting input:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is missing. Stop and send this output.'
    }
    $runtimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Initialize-WindowsAlliance.ps1' `
        -RuntimeRoot $runtimeRoot

    if ($LASTEXITCODE -ne 0) {
        throw 'Game database initialization failed. Send the console error without passwords or private runtime files.'
    }
}
```

The new `-RuntimeRoot` parameter selects the same permanent location for initialization, database launch, website and checks. Always include it in later commands. Omitting it retains the historical repository runtime; there is no automatic migration or fallback. Empty, relative, UNC, file and redirected paths are rejected. Initialization creates and restricts only its new owned runtime. Existing unowned folders are rejected; an existing valid owned runtime can resume while retaining its credentials and accounts. A stale operation lock is not automatically deleted.

## Expected result and what to return

Expect the selected path under `C:\Users\Uni\AppData\Local\WesnothAlliance\runtime`, followed by prompts for:

1. A new administrator username: 3–24 letters, digits or underscores.
2. A password: 12–128 characters.
3. The same password again. Password entry is hidden.

The initializer creates authenticated replica set `wesnoth-rs` on `127.0.0.1:27018`, the `wesnoth_game` schema, a restricted database application user and your administrator account. It then stops its database. Expected completion:

```text
ALLIANCE INITIALIZATION PASSED
MongoDB 8.0.32; authenticated single-node replica set; scoped application user; admin account ready.
Owned database stopped. Start the database window, then the service window.
```

Send the completion/error text and confirm whether WAN was disconnected. This interactive step intentionally creates no console transcript. Never send the password, `.env`, `root.json`, `config.json` or `keyfile`. If startup fails, send the new runtime's `logs\mongodb.log`; stop at that failure instead of deleting data or repeatedly retrying.

After this result, the next step is to run the database and local administrator website, then verify login, a saved area and restart persistence. The game UI does not yet expose persistent accounts, leader progression or Alliance battles.
