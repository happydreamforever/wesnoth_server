# Next Windows step: inspect the launcher lock after shutdown

The returned MongoDB log records Ctrl-C, successful completion of the WiredTiger checkpoint/close, and `mongod shutdown complete` at 06:54:54.365-06:00, followed by exitCode12. The 06:55:13 restart stopped before spawning MongoDB because our `operation.lock` marker exists. The marker is separate from MongoDB's storage lock. Its existence alone does not prove its recorded process is still running.

A stale marker after interrupted launcher cleanup is likely, but current process state has not been collected. Do not restart again, initialize, remove/rename any lock or stop additional processes for this check. Leave the current windows as they are. No pull, build, installer or elevated PowerShell is required. The area/audit/logout results and persistence after restart remain pending; no new area should be created to replace a record before recovery.

Run this one block in a normal PowerShell window under the same Windows account. It reads only the launcher marker and selected process/listener metadata, and writes a new diagnostics transcript. It does not read credentials, connect to MongoDB or alter runtime files/processes.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = 'D:\Test\wesnoth-setup\wesnoth_server'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
    $runtimeRoot = Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime'
    $lockPath = Join-Path $runtimeRoot 'operation.lock'
    $diagnostics = Join-Path $repo 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('runtime-lock-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')

    Start-Transcript -LiteralPath $log -NoClobber | Out-Null
    try {
        'CHECK TIME: ' + (Get-Date -Format o)
        $lockOwnerId = 0L
        if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
            $item = Get-Item -LiteralPath $lockPath -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Length -gt 4096) {
                throw 'Unexpected lock file type or size. Existing files were preserved.'
            }
            $record = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
            if (-not [long]::TryParse([string]$record.pid, [ref]$lockOwnerId) -or $lockOwnerId -lt 1 -or $lockOwnerId -gt 2147483647) {
                throw 'Lock PID is invalid. Existing files were preserved.'
            }
            'LAUNCHER LOCK'
            $item | Format-List FullName,Length,LastWriteTimeUtc
            $record | Select-Object pid,started_at | Format-List
        } else { 'No operation.lock file is currently present.' }

        'CURRENT OWNER / PYTHON / MONGODB PROCESSES'
        $filter = "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'mongod.exe'"
        if ($lockOwnerId -gt 0) { $filter += " OR ProcessId = $lockOwnerId" }
        $processes = @(Get-CimInstance Win32_Process -Filter $filter -Property ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate -ErrorAction Stop)
        if ($lockOwnerId -gt 0 -and -not ($processes | Where-Object { $_.ProcessId -eq $lockOwnerId })) {
            'Recorded lock-owner PID is no longer running.'
        }
        if ($processes.Count -eq 0) { 'No matching processes.' }
        else { $processes | Format-List ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate }

        'CURRENT DATABASE / WEBSITE LISTENERS'
        $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -in @(27018,18765) })
        if ($listeners.Count -eq 0) { 'No listeners on TCP 27018 or 18765.' }
        else { $listeners | Format-Table LocalAddress,LocalPort,OwningProcess -AutoSize }
        'READ-ONLY LOCK CHECK COMPLETE. No process or runtime file was changed.'
    } finally {
        Stop-Transcript | Out-Null
        Write-Host "Saved log: $log"
    }
}
```

Expected: the recorded lock PID/start time, any current owner/Python/MongoDB processes, and listeners on ports27018/18765. If the marker is stale and both applications have stopped, expect **Recorded lock-owner PID is no longer running.**, no matching Alliance processes, and **No listeners on TCP 27018 or 18765.** Other Python processes may legitimately appear. A reused PID or incomplete/denied query needs review; do not infer stale ownership from age or blank fields.

Send the saved `diagnostics\runtime-lock-*.txt` report or its complete output, including errors or blank fields. No passwords, `.env`, cookies, private runtime configuration or key files are needed. The new report determines whether an old marker can be preserved under a backup name safely or an existing operation is still active. Do not delete `mongod.lock` or `operation.lock` manually.
