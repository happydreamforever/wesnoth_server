# Next test: install the Alliance backend offline

The returned Windows transcript confirms successful preparation at server `e9b42e7` and client `d8ab444`, using native Python 3.14.3 x86_64. Eleven cached wheels were verified and reused; the remaining six wheels and MongoDB 8.0.32 archive downloaded and passed pinned size/SHA256 checks. Final marker: `ALLIANCE DEPENDENCIES VERIFIED: 17 wheels; MongoDB 8.0.32.` All new downloads succeeded on attempt 1; this does not exercise Windows automatic backoff.

Saved Windows preparation report: `diagnostics/alliance-prepare-20261019-121753-670-8878f561309b4abc99105f9fcd4b0f09.txt`. Installation and database/admin initialization have not run yet. Existing offline guest gameplay remains passed; this backend is not yet connected to the Android game.

## Do this one step now

Disconnect internet/WAN access while keeping the local network connected. The installer is already in your checkout; no pull or repeat preparation is needed for this documentation update. Run in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-WindowsAlliance.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Offline installation failed. Send the saved log.'
    }
}
```

The helper reverifies the cache, extracts the pinned portable MongoDB files, checks `mongod.exe --version`, creates the isolated `build\alliance-venv` Python environment and installs the 17 packages from local wheels with `--no-index --require-hashes`. It checks package dependencies and installed versions. No download is allowed by this installer.

Expected final messages:

```text
ALLIANCE OFFLINE ENVIRONMENT INSTALLED
Database and administrator accounts have not been initialized.
```

Return the new `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\alliance-install-*.txt`, including any error, and confirm whether WAN stayed disconnected. Stop after this step. If the executable reports a missing Windows runtime, return the exact error before installing anything manually. Initialization, administrator setup and the website test follow after successful installation; their commands are recorded in [ALLIANCE_RUNTIME.md](ALLIANCE_RUNTIME.md).

## Scope and validation

This handoff changes documentation only. Existing VPS results remain: 66 domain/authentication/admin/deployment checks using real MongoDB 8.0.32 and Python 3.14.3, plus the current 28 artifact/PowerShell checks. All 22 artifact cases also pass under Python 3.14.3 with external networking disabled. PowerShell simulations use Linux PowerShell 7.4.6 and do not prove Windows execution. The updated command was checked against the existing helper and parsed with PowerShell; unchanged implementation tests were not rerun.

Actual Windows installation, MongoDB initialization, website/browser persistence checks, Android accounts and playable Alliance battles remain pending. Preserve the current APK/OBB, game-data source, native stages, verified downloads and MSYS2 location. No rebuild, reinstall of the Android app, or repeated guest LAN turn is needed.
