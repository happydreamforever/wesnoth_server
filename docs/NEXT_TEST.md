# Next test: identify the process captured blocking replacement

The Windows scratch probe reproduced the failure at iteration 2: Python PID19540, operation replace, errno13 / winerror32. Logfile.CSV identifies svchost.exe PID4600 holding the source file with sharing that excludes delete access. Python's rename-related open requests Delete access and fails while that handle remains open. Its approximately 9.48-millisecond lifetime shows why an after-the-fact handle search can miss this kind of conflict.

This identifies the blocker in the scratch test. The CSV does not identify its hosted service/software or prove it held the earlier actual MongoDB metadata file. MsMpEng.exe mapping events are present, but they do not demonstrate a conflicting open handle. Do not attribute this to the historical service or disable security software from these observations.

## One read-only identity check

No pull, rebuild, new capture, probe repeat or database startup is needed. Keep MongoDB stopped. Open Windows Start, search **Windows PowerShell**, choose **Run as administrator**, and paste:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open Windows PowerShell with Run as administrator, then run this block.'
    }

    $capturedAt = [datetime]'2026-10-19T14:23:41.9345583'
    $target = Get-CimInstance Win32_Process -Filter 'ProcessId = 4600'
    if (-not $target) {
        'Captured PID 4600 is no longer running. Send this result; do not rerun the probe.'
        return
    }

    'CURRENT TARGET'
    $target | Format-List ProcessId,Name,ExecutablePath,ParentProcessId,CreationDate
    if (-not $target.CreationDate -or $target.Name -ne 'svchost.exe' -or $target.CreationDate -gt $capturedAt) {
        'Current PID identity cannot be matched to the capture. Stop here and send this output.'
        return
    }

    'SERVICES IN CURRENT TARGET'
    $services = @(Get-CimInstance Win32_Service -Filter 'ProcessId = 4600')
    if ($services.Count -eq 0) { 'No matching service.' }
    else { $services | Format-List Name,DisplayName,State,ProcessId }

    'CURRENT PARENT'
    if ($target.ParentProcessId -eq 0) {
        'No reportable parent PID.'
        return
    }
    $parent = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $target.ParentProcessId)
    if (-not $parent) {
        'Parent PID is no longer running.'
        return
    }
    $parent | Format-List ProcessId,Name,ExecutablePath,ParentProcessId,CreationDate
    if (-not $parent.CreationDate -or $parent.CreationDate -gt $target.CreationDate) {
        'Parent PID cannot be matched to the original parent; it may have been reused.'
        return
    }

    'SERVICES IN CURRENT PARENT'
    $services = @(Get-CimInstance Win32_Service -Filter ('ProcessId = ' + $parent.ProcessId))
    if ($services.Count -eq 0) { 'No matching service.' }
    else { $services | Format-List Name,DisplayName,State,ProcessId }
}
```

Send the complete output, including blank fields, `No matching service`, absent/reused PID messages or errors. This reads only targeted process metadata and service associations; it does not read command lines, credential files, service configuration or the database, and does not stop/change anything.

Creation-time guards reject a target created after the capture, a mismatched process name, an unavailable creation time, or a parent created after the target. These are current metadata observations, not an immutable historical service mapping. If the target exited/reused its PID or information remains unavailable, keep the original Process Monitor session/PML locally. The captured event's Process properties can provide trace-bound image/parent information later; do not repeat the probe just to obtain a new PID or upload the full PML.

## Evidence and remaining work

CSV lines count the header as line1:

| CSV line | Time | Observed operation |
| --- | --- | --- |
| 57 | 14:23:41.9316899 | svchost4600 opens WiredTiger.turtle.set, Generic Read, ShareMode Read/Write without Delete. |
| 63 | 14:23:41.9344555 | Python19540 closes its writing handle. |
| 64 | 14:23:41.9345583 | Python19540 requests Delete access and receives SHARING VIOLATION. |
| 71 | 14:23:41.9411686 | svchost4600 closes its handle. |

The first iteration succeeds because that process closes its read handle before Python's rename. Windows documents that omitted FILE_SHARE_DELETE blocks later delete-access opens, including renames: [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew). Targeted metadata fields are documented under [Win32_Process](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process) and [Win32_Service](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-service).

Preserve the original MongoDB runtime, failed scratch files/report, CSV, crash log/dump and completed packages/game/data/native stages. Do not terminate a generic svchost process, change services/security settings, retry initialization or repair/delete metadata. The next action depends on identifying the current process. Local Windows MongoDB remains the deployment; the .env internet server is not used. Initialization, admin website and disconnected Alliance runtime remain pending.

Documentation-only delivery: the probe performed its diagnostic role and is unchanged. No MongoDB fix or startup success is claimed. events.jsonl itself was not supplied; the inline output and CSV establish the reported probe result without requiring another run.
