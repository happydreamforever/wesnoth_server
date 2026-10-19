# Next test: retry offline Alliance installation after the MongoDB rename fix

Windows reverified all 17 cached Python wheels and the MongoDB 8.0.32 archive. Installation then failed with WinError 5 while renaming `build\alliance-mongodb.extract-z9xofzmh` to `build\alliance-mongodb`. That operation follows extraction and verification of the selected files. The log does not identify why Windows denied the rename. The old cleanup may have removed the temporary extraction; leave any surviving files alone. MongoDB execution, Python environment installation and database initialization were not reached.

Saved report: `diagnostics/alliance-install-20261019-122858-565-8a4bac95f26b4c7b8d6ec812d1cb03a6.txt`. This inline result does not independently establish WAN disconnection. Last confirmed Windows commits remain server e9b42e7/client d8ab444; the documentation-only commits after them were not confirmed pulled.

## Pull the fix while temporarily connected

Run in PowerShell:

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

After both pulls succeed, disconnect internet/WAN while keeping the local network connected. Then run:

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

## Expected result

The installer uses the existing verified cache. If Windows denies the final directory rename with error 5, 32 or 33, it retries that operation up to six total attempts, waiting 0.5, 1, 2, 4 and 8 seconds. It rechecks the completed extraction's ownership, file hashes, contents and identity, and refuses an existing destination. Retries within this invocation do not repeat extraction or downloads. Installed files are verified again before MongoDB execution.

If the rename succeeds and subsequent installation checks pass, the final messages are:

```text
ALLIANCE OFFLINE ENVIRONMENT INSTALLED
Database and administrator accounts have not been initialized.
```

If publication still fails, the helper reports the preserved extraction/destination paths and stops before starting MongoDB or creating the Python environment. Keep those files and send the log; do not delete, rename or change permissions manually. Preserved extraction directories are not automatically adopted by a later invocation. Other later installation errors also require the complete log.

Return `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\alliance-install-*.txt`, including any error, and confirm whether WAN stayed disconnected. Stop after installation. Database/admin initialization follows its successful result; the full sequence is recorded in [ALLIANCE_RUNTIME.md](ALLIANCE_RUNTIME.md).

## Validation and scope

VPS tests cover Windows-error injection, bounded exhaustion, competing destinations, altered source/receipt/metadata/identity, interrupts, foreign paths, final hash checks and no binary execution after failed publication. The real 807,312,757-byte pinned MongoDB archive was extracted with Python 3.14.3 and external networking disabled: injected errors 5 and 32 used the same verified extraction before a successful real Linux rename, followed by pin verification and installed-tree reuse. This does not reproduce the Windows filesystem denial or prove the Windows correction.

Only the dependency installer and its tests change. Existing downloaded archives, package versions, native game/Android stages, .env and database code remain unchanged. The preparation success marker is now flushed immediately to keep its output in order. No Android rebuild, reinstall, old network recovery, service investigation or tool upgrade is needed.
