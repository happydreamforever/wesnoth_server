# Next Windows test: preserve the stale marker and verify restart

The returned report records legacy `operation.lock` PID7400, started_at `2026-10-20T12:36:21.894725+00:00`, 63bytes. At 07:07:19-06:00 the recorded owner and matching Python/MongoDB processes were absent and ports27018/18765 had no listeners. Together with the previous MongoDB storage-shutdown log, this supports recovery of the stale launcher marker. The helper rechecks current conditions before acting; the earlier observation is not a substitute for live checks.

The fix uses a permanent `operation.guard` file with a lock held by the operating system throughout the database launcher/cleanup lifetime. This lock is released when the launcher exits, including abrupt process exit. The guard file itself remains and must not be deleted. A leftover legacy `operation.lock` is refused until the separate recovery succeeds. Credentials, database contents, administrator and earlier areas are preserved. No MongoDB/Android rebuild, dependency install or initialization is needed.

## 1. Pull while temporarily connected

Keep both applications stopped as in the returned report. Use the existing MSYS2 Git route. Do not start another launcher during update/recovery, and do not mix old checkout versions with the updated launcher; old code did not recognize the new OS guard.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
    }
}
```

After both pulls succeed, disconnect WAN again while keeping local Ethernet connected.

## 2. Preserve the stale legacy marker

Use normal PowerShell under the same Windows account:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Repair-WindowsAllianceRuntimeLock.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
        -ExpectedPid 7400 `
        -ExpectedStartedAt '2026-10-20T12:36:21.894725+00:00'
    if ($LASTEXITCODE -ne 0) { throw 'Lock recovery stopped. Send the saved recovery log; do not restart yet.' }
}
```

Expected: **Preserved legacy marker:** with a unique `operation.lock.recovered-*.json` path inside the runtime, then **ALLIANCE RUNTIME LOCK RECOVERY PASSED**. Keep that backup. The helper checks the supplied marker identity, current processes and listeners twice while holding the new guard. It refuses ambiguous files, mismatched records, current owner/Python/MongoDB processes, occupied ports or failed queries. It archives the exact open marker with no overwrite; it does not connect to MongoDB, change database data or terminate a process. A new permanent operation.guard is normal.

The report is `diagnostics\alliance-runtime-recovery-*.txt`. If the helper reports any error, stop and return the saved log. Do not remove locks manually or rerun initialization. This recovery is needed once for this old marker; successful absence of the marker on future launches is normal.

## 3. Start the updated database launcher

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for **Alliance MongoDB running on 127.0.0.1:27018**. If it fails, stop and send the output.

To test this fix, press **Ctrl+C once** in this database window and wait for the PowerShell prompt. Then run the **same database command once more**. Expected: the running message again, without a legacy-marker error. Keep this second run open. If shutdown reports an error, hangs or restart fails, stop and send the output; do not repeatedly interrupt, force-close or remove the guard. A guard-busy error should be reported, not bypassed.

## 4. Start the website in a second window

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected: **ALLIANCE DATABASE CHECK PASSED**, then **Alliance admin: http://127.0.0.1:18765/**. The website automatically checks the authenticated primary/schema/administrator and transaction rollback. Leave both windows running.

## 5. Check existing saved records and report

Open `http://127.0.0.1:18765/` in the Windows browser and sign in as `Uni` with the same password. If you created Area 2 (or another area) before the failed restart, confirm its same name/identifier under **Areas**, and the corresponding `create_area` Target under **Audit log**. Do not recreate a missing area to make the check pass. If no area was created earlier, report that; first complete this launcher restart test before scheduling the new-area persistence test.

Return the pull output, saved recovery log, database start/stop/restart and website output, and whether any previously created area/audit entry survived. Mention whether you had completed area creation, audit and sign-out before the original failure. Keep WAN disconnected through this test and mention if connectivity changed.

Database and service transcripts are `diagnostics\alliance-database-*.txt` and `diagnostics\alliance-serve-*.txt`; exact paths print when those commands stop. Healthy restarted windows may remain open while you return their visible output. Do not send passwords, `.env`, private configuration/keys or cookies. Preserve all profile data, earlier runtimes/scratch/logs/dumps and completed game builds/OBB/receipts. Android custom accounts/teams remain a later integration milestone.
