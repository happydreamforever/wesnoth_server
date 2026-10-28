# Targeted interruption and recovery — 1192624

Use these procedures only when the matching T, U or Z step in the acceptance
checklist is reached. They exercise the existing `runtime-v2`; they do not
replace it. Keep the batch's recorded WAN state and local Ethernet connection.
Stop on the first unexpected result and report the substep, actual message and
sanitized diagnostic paths. Never send passwords, worker input files, runtime
credentials, private backups or raw evidence files.

## T3. Disconnect and reconnect the same mobile account

Preconditions: save any story campaign first; enter an actual prepared World or
Company battle. For a multiplayer check, the other human account must already
be connected using its separately authenticated companion or another real
client. Record the current round/side and a few unit positions. Keep all five
Windows services and the companion open. Do this before a terminal result.

1. In a separate PowerShell window, close only the existing game application:

   ```powershell
   & {
       $ErrorActionPreference = 'Stop'
       if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
       $worldAdb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
       if (-not (Test-Path -LiteralPath $worldAdb -PathType Leaf)) { throw 'The existing SDK ADB is missing. Stop.' }
       $worldDeviceState = & $worldAdb -s '127.0.0.1:5555' get-state
       if ($LASTEXITCODE -ne 0 -or ($worldDeviceState -join '').Trim() -ne 'device') {
           throw 'The selected existing LDPlayer is unavailable. Stop without changing ADB or the emulator.'
       }
       & $worldAdb -s '127.0.0.1:5555' shell am force-stop org.wesnoth.offline
       if ($LASTEXITCODE -ne 0) { throw 'The targeted game interruption failed. Stop and report this output.' }
       Write-Host 'Only the game application was stopped; app data was retained.'
   }
   ```

   This is the deliberate interrupted-app test, not a normal Quit. Do not run
   `pm clear`, uninstall, kill the emulator, or stop the database.
2. The required human controller is now absent. The remaining native engine
   must wait; the worker must not take over this human side or settle an invented
   result. A command already durably accepted before disconnection can remain
   visible; record the resumed state rather than expecting a screenshot rollback.
3. Open the existing Wesnoth icon in LDPlayer. Log in as **the same account**,
   open Team → Battles, select the retained battle and choose **Resume battle**.
   Do not create another engagement or log this account into the companion.
4. Expect the same battlefield reconstructed from the retained command history,
   fixed ownership and continued synchronized play. Complete it normally and
   compare its one History receipt and XP with your earlier values.

Report T3 with the account username, observed pause/resume, outcome and any short
error; no password. One LDPlayer plus an AI-controlled authenticated companion
is not multiple-human mobile evidence. Without another authenticated participant,
record multiplayer T3 as NOT RUN; a Company expedition tests only its own path.

## T4a. Restart the shared battle service during native play

Use an unfinished battle whose participants agree to this test. Record its
current map/turn/units and close its mobile battle view only if prompted by a
connection error. Keep the database, admin backend, account bridge and native
Room server running. Do not submit another battle, cancel the contract, or
advance the host round.

1. Press **Ctrl+C only in the shared battle service window** that displayed
   `ALLIANCE SHARED BATTLE SERVICE READY`. Its supervisor stops its own native
   worker children. Wait for that PowerShell prompt and saved log. If it does not
   return, stop and report; do not kill all `python.exe` or game processes.
2. In that same window, restart exactly this service:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass `
       -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBattles.ps1' `
       -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
       -IdentityRoot 'D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance-transport' `
       -Workers 1
   ```

   Keep this window open. Expect the verified worker and shared battle READY
   messages. If U already explicitly selected two workers, retain `-Workers 2`.
3. Allow up to two minutes for an old worker lease to expire and the same
   generation to be reacquired. Do not repeatedly restart. Each required human
   account logs in again if needed and chooses **Resume battle**. A companion
   that exited is restarted with the same username and retained battle selection:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass `
       -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsWorldCompanion.ps1' `
       -Username 'YOUR_EXISTING_SECOND_PLAYER'
   ```

4. Verify the retained battlefield and fixed controllers, then finish normally.
   A complete native result saved just before interruption may already be in
   History; inspect that receipt rather than launching another battle. A
   synchronization/evidence dispute must stay blocked for host review, not
   silently restart or award XP.

Report the old/new `diagnostics\alliance-battles-*.txt` logs and companion
`diagnostics\world-companion-*\report.json`, plus the observed outcome. Worker
replay and command files remain private under the runtime and must be retained.

## T4b. Let an unstarted preparation time out

Use a **new Company expedition** with available healthy units so this test does
not consume a territorial engagement or another player's standing permission.
Record hero/soldier XP and wounds first. Start the expedition once, then remain
on Battles without choosing Enter battle.

1. Observe Queued, then Preparing. Start timing only when Preparing appears;
   queue time does not count toward the five-minute preparation deadline.
2. Leave the services open and do not enter that battle. Refresh the list after
   six minutes, allowing the worker heartbeat to enforce the deadline.
3. Expect Cancelled in History, retained cancellation details, no victory/XP,
   no new wounds and released Company assets. The cancelled record itself is
   never restarted. A later expedition is a new contract and needs its normal
   review/start action.

If it remains Preparing/Paused after six minutes, stop and report the shared
battle log and screen. Do not delete locks or use database edits to force expiry.
This does not establish territorial timeout acceptance; a territorial timeout
still retains its round participation history and must not grant another
same-round engagement.

## U. Select two native workers for disjoint execution

Finish or resolve current engagements first and stop companions. Stop **only**
the shared battle service with Ctrl+C and wait for its prompt. Then run the G
stack check with the explicit count; healthy other services are reused:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles -WorldWorkers 2
    if ($LASTEXITCODE -ne 0) { throw 'Two-worker startup stopped. Send the workflow report.' }
}
```

Expect W05 to start with two verified worker slots and W07 READY. A slot count
is not proof of two completed games: U must actually observe disjoint native
engagements with separate authenticated owners. If memory or availability is
insufficient, retain the reports and mark parallel execution NOT RUN; do not
clone LDPlayer or share one account between seats. Return to one worker only
after safely stopping this service again, using `-WorldWorkers 1`.

## Z3. Verify the original schema-3 backup in an isolated directory

Finish/resume/cancel outstanding engagements deliberately first. Save story
games, Quit, stop companions, then stop all five services with Ctrl+C in the A
order. Wait for all prompts. Keep the exact **B** cold-backup path in
`$worldBackup`; if using a new PowerShell window, assign the exact path retained
from B before running this block. Do not substitute a new backup or another
release's backup.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
    if (-not $worldBackup -or -not (Test-Path -LiteralPath (Join-Path $worldBackup 'manifest.json') -PathType Leaf)) {
        throw 'Set $worldBackup to the exact verified B backup path first.'
    }
    $worldOriginal = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2'
    $worldRecovery = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\recovery\schema3-1192624-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Restore -RuntimeRoot $worldOriginal `
        -BackupPath $worldBackup -DestinationPath $worldRecovery
    if ($LASTEXITCODE -ne 0) { throw 'Isolated restore stopped. Keep the new directory and send only the sanitized maintenance log.' }
    Write-Host ('Retain this private isolated recovery path: ' + $worldRecovery)
}
```

Expected: `LEGACY DATABASE RECOVERY VERIFIED`, `ALLIANCE RESTORE VERIFIED`,
`schema_checked:true`, `database_stopped:true`, `original_unchanged:true` and
`activation_performed:false`, then MA03. The helper briefly runs and cleanly
stops only the new copy. The original schema-4 runtime and backup remain intact.
Keep the copy privately. Do not run the current schema-4 application against
that schema-3 recovery copy, migrate it, or point normal service startup at it.

Restart the **original** runtime explicitly (default one worker shown):

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' -IncludeBattles -WorldWorkers 1
    if ($LASTEXITCODE -ne 0) { throw 'Original-runtime restart stopped. Send the workflow report.' }
}
```

Expect all five services READY. Reopen the existing game, log in and compare
current Company/hero/Team values and History with the values recorded before
Z3. Restoration verifies recoverability of B; it does not roll current progress
back to B. Send the sanitized `diagnostics\alliance-maintenance-*.txt` and
startup workflow result. Keep both runtime folders, the backup and journals.
