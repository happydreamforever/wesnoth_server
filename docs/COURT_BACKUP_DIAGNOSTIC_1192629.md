#1192629 interrupted account-stage backup — read-only collection

The Windows backend health check passed (HTTP200). Update preparation preserved
android-account-engine, then exhausted five unchanged-stage retries while Windows
refused to rename android-account-game with WinError5. Compilation and installation
did not start. This attempt did not update the installed game.

The immutable journal was written before the first move. The existing helper can
resume by verifying the retained engine backup and handling the remaining game
stage, once the access problem is understood. No source/helper change is presently
justified. Access Denied alone does not identify an owning process or establish
that permissions, Gradle, an editor or security software caused the failure.

Keep the five services and LDPlayer open. Preserve all stages, journals and the
saved rebuild log. Collect evidence before another build, folder rename/deletion,
lock deletion, permission change or process shutdown. No new pull is needed.

Run the following in the same normal PowerShell session. It reads existing build
metadata and writes only a new diagnostic transcript. It never prints target_inputs,
full snapshots, operation tokens or process command lines.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = 'D:\Test\wesnoth-setup\wesnoth_client'
    $buildRoot = Join-Path $repo 'build'
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('account-backup-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    $suffix = '-before-menu-polish-20261102T122510Z-8a56994163fc4aaa8cb8ec98b813e349'

    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    try {
        $journalPath = Join-Path $buildRoot '.wesnoth-account-game-update-1192629.json'
        $journalItem = Get-Item -LiteralPath $journalPath -Force
        if ($journalItem.PSIsContainer -or ($journalItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Unexpected journal path type. Preserve it and stop.'
        }
        $journal = Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host 'UPDATE JOURNAL SUMMARY'
        $journal | Select-Object schema_version,kind,target_version | Format-List
        foreach ($stage in @('android-account-engine', 'android-account-game')) {
            $entry = $journal.stages.$stage
            [pscustomobject]@{
                Stage = $stage
                Backup = $entry.backup
                RecordedFiles = @($entry.snapshot.files.PSObject.Properties).Count
                RecordedDirectories = @($entry.snapshot.directories).Count
            } | Format-List
        }

        Write-Host 'EXISTING PATHS AND ATTRIBUTES'
        foreach ($name in @('', 'android-account-engine', 'android-account-game',
                ('android-account-engine' + $suffix), ('android-account-game' + $suffix),
                '.wesnoth-account-game-update-1192629.json', '.wesnoth-account-game-operation.json')) {
            $path = if ($name) { Join-Path $buildRoot $name } else { $buildRoot }
            try { $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop }
            catch [System.Management.Automation.ItemNotFoundException] {
                Write-Host "MISSING: $path"
                continue
            }
            $item | Select-Object FullName,PSIsContainer,Length,Attributes,LastWriteTimeUtc | Format-List
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'A listed path is redirected. Preserve it and stop.'
            }
            if ($name -eq '' -or $name -eq 'android-account-game') {
                Get-Acl -LiteralPath $path | Select-Object Owner,AccessToString | Format-List
            }
        }

        Write-Host 'CURRENT RELEVANT PROCESSES (no command lines)'
        Get-CimInstance Win32_Process -Property Name,ProcessId,ParentProcessId |
            Where-Object { $_.Name -in @('java.exe','javaw.exe','studio64.exe','gradle.exe','cmake.exe','ninja.exe','python.exe','Code.exe','explorer.exe') } |
            Select-Object Name,ProcessId,ParentProcessId | Sort-Object Name,ProcessId | Format-Table -AutoSize
        Write-Host 'READ-ONLY COLLECTION COMPLETE. No build or recovery was attempted.'
    } finally {
        Stop-Transcript | Out-Null
        Write-Host "Saved log: $log"
    }
}
```

Return the complete output and saved transcript. Missing canonical engine and
missing game backup may reflect the partial move; report actual values. Any
unexpected read error is useful evidence; do not recreate a missing journal.

Also open Resource Monitor (`resmon.exe`), choose CPU, expand Associated Handles,
and search for `android-account-game`. Report matching Image/process name, PID
and handle path, or “No matching handles”. Leave processes running. A match alone
is a candidate, not proof that its handle prevented this rename. ACLs and process
lists likewise do not establish rename readiness.

Source review: prepare_update writes and validates the immutable journal before
moves, verifies every already-retained backup on resume, and preserves the
unchanged remaining stage on rename failure. operation uses guarded cleanup of its
own lock in finally; actual lock presence is not presumed. The existing tests cover
an interrupted second move/resume, unchanged-byte retry and changed-stage rejection.
No unchanged tests/builds were rerun for this evidence-only checkpoint.

This exact collector parses with zero errors in existing PowerShell7.4.6; commands
were not executed on Windows. Proof: client build/audit-account-backup-denied-1192629/
final-parse-result.json. The user-confirmed WAN-disconnected/Ethernet-connected
condition remains recorded once for this batch.
