# World D: first-package archive diagnostic

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
