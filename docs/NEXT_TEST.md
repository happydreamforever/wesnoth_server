# Next Windows test: resume administrator setup with the corrected prompt

The latest Windows initialization reached administrator setup, then rejected the username. Its username prompt appeared after the password prompts. We reproduced the ordering defect with PowerShell piping native stdout: a prompt without a newline was held until later output. The correction prints a full flushed username line and validates it before asking for a password. The actual username entered is unknown; no password or username needs to be returned for diagnosis.

Use the same `%LOCALAPPDATA%\WesnothAlliance\runtime` directory (normally `C:\Users\Uni\AppData\Local\WesnothAlliance\runtime`). The initializer retains its existing credentials/configuration and completes the missing administrator step. Keep the directory intact. MongoDB8.0.32 and Python3.14.3 are already installed; no installer, build, repeated standalone fixture or new runtime path is needed. The earlier standalone profile startup/write/restart passed with user-confirmed WAN disconnection.

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

## 2. Disconnect WAN, keep local Ethernet, then retry initialization once

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

Expect the selected path under `C:\Users\Uni\AppData\Local\WesnothAlliance\runtime`. The username prompt must appear first on its own line. At that prompt, type a username such as `UniAdmin` and press Enter, then complete:

1. A new administrator username: 3–24 ASCII letters, digits or underscores. An invalid username now shows the allowed format and asks again before any password prompt, up to five attempts.
2. A password: 12–128 characters.
3. The same password again. Password entry is hidden.

The initializer resumes authenticated replica set `wesnoth-rs` on `127.0.0.1:27018`, verifies the `wesnoth_game` schema and restricted database application user, and creates your administrator account. It then stops its database. Expected completion:

```text
ALLIANCE INITIALIZATION PASSED
MongoDB 8.0.32; authenticated single-node replica set; scoped application user; admin account ready.
Owned database stopped. Start the database window, then the service window.
```

Send the completion/error text, confirm the username prompt appeared before the password prompts, and confirm whether WAN was disconnected for this retry. This interactive step intentionally creates no console transcript. Never send the password, `.env`, `root.json`, `config.json` or `keyfile`. If startup fails, send the new runtime's `logs\mongodb.log`; stop at that failure instead of deleting data or repeatedly retrying.

After this result, the next step is to run the database and local administrator website, then verify login, a saved area and restart persistence. The game UI does not yet expose persistent accounts, leader progression or Alliance battles.
