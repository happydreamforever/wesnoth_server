# Next Windows step: one file-location comparison

Both requested logs were reviewed. MongoDB failed to rename its new WiredTiger metadata file because Windows reported that it was in use; cleanup deletion failed too, followed by WT_PANIC and assertion50853. This is now confirmed in the fresh disposable database, not only the old game runtime. The installed pins passed. The log does not identify the holder; no new service or malware attribution is established. `process-1.log` is present and empty.

All supplied failures so far occurred under D:\Test. The next bounded question is whether the same file replacement fails under the current user's LOCALAPPDATA, outside the project directory. This is a filesystem-only probe, not another MongoDB start. It creates a new unique subdirectory, performs at most20 synthetic write/sync/close/replace operations and stops at the first failure. Both test files and events.jsonl are retained. No existing game data is moved or reopened.

## 1. Pull the small diagnostic update while temporarily connected

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

## 2. Disconnect WAN, keep local Ethernet and run once in normal PowerShell

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = 'D:\Test\wesnoth-setup\wesnoth_server'
    $python = Join-Path $repo 'build\alliance-venv\Scripts\python.exe'
    $probe = Join-Path $repo 'tools\probe_windows_file_sharing.py'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is missing. Stop and send this output.'
    }
    $parent = Join-Path $env:LOCALAPPDATA 'WesnothAllianceStorageCheck'
    $log = Join-Path $repo ('diagnostics\mongo-profile-probe-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    try {
        Write-Host "Test parent: $parent"
        & $python -I -B $probe --parent $parent
        $probeExit = $LASTEXITCODE
        Write-Host "PROBE_EXIT: $probeExit"
        if ($probeExit -ne 0) {
            throw 'File-location check failed. Send the saved transcript and events.jsonl if present.'
        }
    } finally {
        Stop-Transcript | Out-Null
        Write-Host "Saved log: $log"
    }
}
```

The selected interpreter is the already verified native Windows Python3.14.3 isolated environment. No dependencies are installed. The `--parent` argument changes only where the unique probe directory is created; the historical default diagnostics location and replacement algorithm are unchanged. Do not run the old D-drive probe again or start MongoDB alongside this check.

## Expected result and what to return

If the operations succeed here, expect `FILE PROBE COMPLETED: 20 replacements; scratch files preserved.` and `PROBE_EXIT: 0`. If a file operation fails, expect `FILE PROBE FAILED` with iteration/operation/winerror and `PROBE_EXIT: 1`; any setup error can instead return2. In every case, send the new `diagnostics\mongo-profile-probe-*.txt` and the `events.jsonl` from the exact Scratch folder printed by the probe, if created.

This is a one-run location comparison, not proof that another drive is defective or that MongoDB is fixed. Passing would justify a later MongoDB startup/write/restart test at that location before changing production storage. Failure means stop and review the report; do not extend loops or retry old databases. Keep the existing game runtime, test data and crash dumps. No Process Monitor capture, service/security change, installer or administrator elevation is requested.
