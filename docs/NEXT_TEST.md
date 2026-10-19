# Next test: initialize the local Alliance database and administrator

The latest Windows log confirms successful cache verification, all 17 pinned Python packages installed, no broken package requirements, exact installed versions and `ALLIANCE OFFLINE ENVIRONMENT INSTALLED`. MongoDB's executable version check precedes those steps in the installer and therefore also passed. Database and administrator initialization have not run yet.

Saved report: `diagnostics/alliance-install-20261019-123832-178-5f6bc73476924db79fd820be123d47e2.txt`. The attachment contains no new pulled heads or automatic rename retries. The user subsequently confirms internet/WAN access was still available during installation. Local-cache installation passed; physically disconnected installation was not demonstrated. No reinstallation is needed to proceed with offline database initialization.

## Do this one step now

Disconnect internet/WAN now while retaining the local network. The initialization script is already in your checkout; no pull, repeat installation, package download or Android rebuild is needed for this documentation-only update.

Run interactively in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Initialize-WindowsAlliance.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Initialization failed. Send the error text only; keep private runtime files and passwords private.'
    }
}
```

The helper checks the installed environment, creates the dedicated local MongoDB database and asks for:

1. `New admin username:` — choose 3–24 ASCII letters, digits or underscores.
2. `New admin password (12-128 characters):` — choose a password of 12–128 characters. Input is hidden.
3. `Repeat admin password:` — enter the same password again.

Keep this login for the administrator website. Do not put the password in a command, chat or saved transcript. The helper deliberately does not create a console transcript for initialization.

Expected final output:

```text
ALLIANCE INITIALIZATION PASSED
MongoDB 8.0.32; authenticated single-node replica set; scoped application user; admin account ready.
Owned database stopped. Start the database window, then the service window.
```

Wait until PowerShell returns. Stop after this step and return only the final status/error lines. Do not send files from `runtime\alliance` or your password. If it fails, preserve the runtime and stop; report the error before deleting anything or retrying. The runtime's ownership/lock checks protect existing data.

## Scope and next milestone

Initialization creates the owned `runtime\alliance` database/configuration/credentials, uses MongoDB on `127.0.0.1:27018` and temporarily starts that database for setup. It shuts down the owned process before returning. The old `.env` and its database are not used. The game still uses the existing guest protocol; this step does not add player login or Alliance Battle to the Android app.

Database and website run windows, browser login and persistence testing follow a successful initialization report. Their full commands remain in [ALLIANCE_RUNTIME.md](ALLIANCE_RUNTIME.md), but do not advance to them yet.

This delivery changes documentation only. The existing initialization helper and prompt/validation flow were reviewed, and the exact PowerShell handoff was parsed. Unchanged implementation tests were not repeated. Earlier VPS results include real MongoDB initialization/restart/authentication and the current 38 artifact/PowerShell checks; actual Windows initialization and website testing remain pending.
