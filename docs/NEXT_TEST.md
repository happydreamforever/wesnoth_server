# Next check: match the unknown stack addresses to recorded modules

The user supplied 39 stack frames from the retained successful file-open event. The stack includes Windows filesystem/WOW64 layers and the 32-bit `CreateFileW` entry points. Frames **23–35** contain 13 `<unknown>` callers with no module/path. Their addresses range from `0x1002d3e8` to `0x1010a733`; the first is `0x100fe806`.

This does not identify the software behind those calls. Unknown frames do not by themselves prove malicious injection, and the named Windows frames do not identify a Windows component as the cause. The established facts remain: PID4600 blocks scratch-file replacement, its current parent4196 hosts NetActvity, and the actual earlier MongoDB-crash holder was not traced directly.

## One observation from the same retained event

The original Process Monitor capture is still open by user confirmation. Keep capture stopped and keep that session intact. No pull, command, download, new capture, probe run or MongoDB startup is needed.

1. In **the same Event Properties window**, switch from **Stack** to **Process**. If the window was closed, double-click the same **2:23:41.9316899 PM / svchost.exe / PID4600 / CreateFile / SUCCESS** event for the scratch `WiredTiger.turtle.set` again.
2. Look at the lower **Modules** table. Its columns include **Module, Address, Size, Path, Company**. Address is the module base address. Widen the window/columns if necessary.
3. Click **Copy All**, paste into Notepad and send only the **Modules** section with all rows. You can save that section as a new `D:\Test\mongo-modules.txt` file and attach it if long. If Copy All copies only the upper process information, send screenshot(s) of the lower Modules table with those columns visible; overlapping screenshots are fine if it scrolls. Do not send command lines, environment or the whole PML.
4. If the list is empty or unavailable, report that result. Do not start another capture to populate it.

You do not need to calculate address ranges. We will check whether a listed image covers `0x100fe806` and the other unknown callers. [Microsoft's Process-tab screenshot](https://learn.microsoft.com/en-us/sysinternals/downloads/media/procmon/procmon-proc.png) shows those table columns and Copy All. [Microsoft describes the Process tab's process and DLL details](https://techcommunity.microsoft.com/blog/askperf/troubleshooting-with-process-monitor/372401), and [Process Monitor documentation](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon) describes its per-event information and stacks.

## Limits and preserved state

A recorded image range may connect an address to a file; it still does not establish that a service can safely be stopped or identify all code executing there. No match can reflect incomplete capture/module information or code not represented by that list; it is not a malware determination. A later narrowly scoped current memory-region metadata query could inspect those exact addresses with VirtualQueryEx/GetMappedFileName without dumping memory, but no such query is requested now.

Do not repeat the historical service/registry/event/reboot experiments. Leave MongoDB stopped and do not terminate processes, modify services/security settings, remove/repair database metadata or read .env. Preserve the original runtime, scratch files/report, CSV/retained session, MongoDB crash evidence and completed game/native/data stages. Local MongoDB initialization/admin/offline Alliance validation remain pending. This is a documentation-only evidence update; backend/probe code is unchanged.
