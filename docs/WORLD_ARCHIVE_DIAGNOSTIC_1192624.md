# World D: first-package archive diagnostic

## Current checkpoint: full preparation passed

The resumed Windows full preparation reached package 107/107 and `WORLD WORKER ISOLATED DEPENDENCIES PREPARED`. Saved log: `diagnostics/world-worker-prepare-20261028-054104-451-ff7e6753e7d5430fa8fabdfa86549405.txt`. Accept full D at pasted-console scope; the saved log itself was not supplied. Preserve the cache, completed prefix, journal and diagnostic scratch. The original ReadError cause remains unknown; worker compilation/execution is not established by extraction.

E schema-4 migration has subsequently passed. Proceed only to [F coordinated builds](WORLD_ACCEPTANCE_1192624.md#f-rebuild-the-coordinated-binaries-offline). No new pull, download or repeated diagnostic/preparation is needed. The commands below are completed history.

## Completed full preparation resume — do not repeat

The returned Windows console confirms all diagnostic phases, including extraction and verification, and both PASSED/COMPLETE markers. Report stem: `diagnostics/world-worker-archive-20261028-053027-599-5b4e9714eeaa43a080042af7a50937a2`; the text/JSON files themselves were not supplied. Retain `build/world-worker-archive-check-464cf0e81cff4a5d859a1080f47528bc`.

This accepts the one-package Windows check. It does not establish why the earlier attempt failed or verify the full prefix. The existing journal and partial files can now be checked by the normal resume path; unknown or changed contents stop without being replaced.

Keep all five services stopped, WAN disconnected and local Ethernet connected. Keep Python 3.14 installed. No new pull, download, Python installation or backup is needed. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Prepare-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'

    if ($LASTEXITCODE -ne 0) {
        throw 'Worker preparation stopped. Preserve the cache and journal; send the new saved log.'
    }
}
```

The helper revalidates all 107 cached packages and resumes matching partial files in the original owned staging directory. Allow several minutes. Expected: `WORLD WORKER PACKAGE CACHE VERIFIED`, then `WORLD WORKER ISOLATED DEPENDENCIES PREPARED` (or `VERIFIED` if already complete).

Return the full console and new `diagnostics/world-worker-prepare-*.txt`, even on success, before E migration. If it stops, retain the reported classification and every preparation file; do not repeat the command until reviewed. Python P1–P3 and the accepted cold backup remain accepted. There is no new network-status measurement in the diagnostic console.

## Earlier diagnostic handoff — completed, do not repeat

The Windows worker preparation verified the 107-package cache, then stopped with `Pinned package archive could not be read: ReadError` during the first package's extraction. Saved Windows log: `diagnostics/world-worker-prepare-20261028-005845-045-7179b8b6b7e74460bc97558c5ec94cc5.txt`. World D has not passed; do not migrate or build yet.

The preparation path scans every package before printing `Preparing worker package 1/107`, so this failure occurred during its second pass, while writing files. The pinned first package (`mingw-w64-x86_64-aom`) passes repeated actual Python 3.12.10 scans and extraction on the VPS: 24 files, 23,735,199 bytes. A deliberately shortened decoder timeout reproduces the old generic `ReadError`, but that does **not** establish the Windows cause. The returned console contains no decoder exit status, timeout flag or precise read-error reason.

The diagnostic update retains those details without printing raw decoder stderr or arbitrary exception messages. The existing 300-second decoder limit, size limits, pins, signatures, path checks and publication rules remain in force. This is a verified error-reporting correction and targeted collection step, not a claim that the original Windows extraction failure is resolved.

## 1. Get the server diagnostic

Keep all five services stopped. Temporarily connect for this server-only fast-forward pull. No client update or repeated Python installation is required.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull failed. Stop and send the output.' }

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check failed. Stop and send the output.' }
}
```

## 2. Check only the failing package offline

Disconnect WAN again and retain local Ethernet. Keep Python 3.14 installed for the existing recovery path and leave all services stopped. The already accepted Python 3.12 interpreter is selected automatically.

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsWorldWorkerArchive.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'

    if ($LASTEXITCODE -ne 0) {
        throw 'Archive diagnostic reported a failure. Send the saved text and JSON reports.'
    }
}
```

This verifies the first locked archive and its signature bytes, checks the pinned decoder, scans the package, and extracts only that package to a new retained `build/world-worker-archive-check-*` directory. It does not download packages, execute package hooks, change the live MSYS2 installation, access runtime-v2 or change the existing worker prefix/staging/journal. It does not rescan all 107 archive contents. The preceding full cache/signature verification remains recorded separately.

Expected on success: `PASS preflight`, `PASS extract`, `PASS verify`, then `WORLD WORKER ARCHIVE DIAGNOSTIC PASSED`. A failure instead reports `WORLD WORKER ARCHIVE DIAGNOSTIC FAILED` and saves the failed phase with available elapsed time, bytes read, timeout flag, decoder exit code and numeric OS error codes.

Return the console and `diagnostics/world-worker-archive-*.txt` plus matching `.json`, even if this single-package check succeeds. Keep its scratch directory and the earlier preparation files. Do not upload the package archive, scratch payload, private runtime, environment file or backup. Full World D extraction, E migration and later acceptance remain pending until the result is reviewed. The next instruction will target the observed cause; do not redownload the cache or repeatedly run the full preparation now.

Python P1–P3 and the prior accepted backup remain accepted. Their tests, account/game state and previous acceptance are not repeated for this diagnostic-only update.
