# Next check: current metadata for the unresolved caller addresses

The complete supplied `module.txt` contains 76 module rows. None contains the 13 unknown callers in `0x1002d3e8`–`0x1010a733`. The known Kernel32 stack address `0x76e96839` is absent too, while the Kernelbase and 32-bit ntdll addresses match. Thus the supplied list does not identify the calling code and is not proven exhaustive. No further broad module export is needed.

The next diagnostic uses Windows [VirtualQueryEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex) and [GetMappedFileNameW](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getmappedfilenamew) to collect current memory-region metadata and any mapped filename for those exact 13 addresses. It does not read process memory contents. It requests only PROCESS_QUERY_INFORMATION, without enabling privileges or attaching a debugger.

## One Windows step

Open **Windows PowerShell → Run as administrator**, under the same Windows account used before. Keep MongoDB stopped and keep the original Process Monitor capture. Temporarily connect for the normal MSYS2 Git pull; the collector itself needs no network or additional packages.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $bash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) {
        throw 'Pull failed. Stop here and send the output.'
    }

    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    & $python -I -B 'D:\Test\wesnoth-setup\wesnoth_server\tools\inspect_windows_caller_regions.py'
    if ($LASTEXITCODE -ne 0) {
        throw 'Collection stopped or was incomplete. Send the saved JSON report and this output.'
    }
}
```

Return the new **diagnostics/caller-regions-*.json** file whose path the collector prints. Success means metadata collection finished; it does not mean MongoDB startup is fixed. If the process is gone, access is denied, or the identity no longer matches, send the report instead of changing its PID/time settings or restarting the probe. No client pull, rebuild, installation or database startup is needed.

## Scope and interpretation

The process handle must match PID4600, `C:\Windows\SysWOW64\svchost.exe`, and local creation time `2026-10-17 03:24:19` at the supplied second precision. A local time-zone change can make that conservative check fail; report it without weakening the guard. The same held handle is used for identity and region queries, with a final identity/liveness check. These checks do not freeze the process, so mappings can still change during collection.

The report records state, allocation/region base, size, type, protection and mapped path or error. Undefined free/reserved fields are not interpreted. A private region, missing file path or unresolved address is not a malware/vendor determination. A current mapped filename is a lead, not proof of the historical captured bytes or of the earlier real MongoDB crash holder. Do not delete/quarantine files or terminate services on the strength of this report alone.

The partial MongoDB runtime, scratch files/report, original CSV/PML/capture, crash evidence and completed game/native/data stages remain preserved. The .env internet server is unused. No process memory dump, ReadProcessMemory, process writes, service/security changes, repair, file-sharing retry or database run is part of this step.
