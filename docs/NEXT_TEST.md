# Next check: inspect the captured file-open stack

The elevated Windows result confirms:

| Role | PID | Path | Creation time (Windows local) | Service association |
| --- | --- | --- | --- | --- |
| Captured scratch blocker | 4600 | C:\Windows\SysWOW64\svchost.exe | 2026-10-17 03:24:19 | No matching service |
| Current parent | 4196 | C:\Windows\SysWOW64\svchost.exe | 2026-10-17 03:24:09 | NetActvity, Running |

The parent reports parentPID960. Both creation times precede the capture, and the parent predates the child. The blocker is a child of the process hosting **NetActvity** (exact spelling). This repeats the pattern recorded during the earlier Git sharing failure; it does not identify the service's publisher/implementation or prove which process held the real MongoDB file when it crashed.

Earlier service configuration, registry, installation-event and reboot checks did not identify this component. Do not repeat those experiments or stop the unidentified service. The next useful evidence is which code made the captured file-open call.

## One observation from the retained capture

No pull, command, build, new capture or probe/database run is needed. Keep MongoDB stopped.

The user confirms **the original capture is still open in Process Monitor**. Use that existing session with capture stopped; do not clear it, reopen the CSV or start a new capture. The supplied ordinary event CSV does not contain the required stack data and cannot recreate it. If the session is unexpectedly lost before this step, report that instead of rerunning anything.

In the retained session/PML:

1. Find the row with **Time of Day 2:23:41.9316899 PM**, **Process Name svchost.exe**, **PID4600**, **Operation CreateFile**, **Result SUCCESS**, and Path ending `mongo-file-probe-sdynefqx\WiredTiger.turtle.set`. This is CSV line57 when counting its header as line1. Select this successful open by the blocker, not the later failed Python event.
2. Double-click that row to open **Event Properties**, then select **Stack**.
3. Use **Copy All** to copy the stack text and paste it here, or use the Stack tab's **Save** button to save its stack CSV as `D:\Test\mongo-blocker-stack.csv` (choose a new name if it exists), then attach that file. If those controls are unavailable, a screenshot of the Stack tab with module/path columns visible is sufficient.
4. Keep all available rows, including unknown/unresolved addresses. Do not download symbols or install debugging tools for this check. If Stack is empty/unavailable, report that exact result.

Return only this event's stack, not the full PML, process memory, private runtime or credentials. Leave the retained session/PML on Windows for reference. Viewing available stack frames does not require reproducing the failure. [Microsoft explains the Event Properties Stack tab](https://techcommunity.microsoft.com/blog/askperf/troubleshooting-with-process-monitor/372401); the [Process Monitor documentation](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon) describes per-operation stacks and native capture retention.

## Interpretation and preserved state

A stack may associate the observed file open with a module; it can also be unresolved or incomplete. An unrecognized address, a Microsoft host executable, or a vendor label alone does not establish malware, innocence or a safe service stop. If the original capture is unavailable, a narrowly scoped, identity-guarded loaded-module inventory of current4600/4196 is the next possible diagnostic; no such command or recapture is requested now.

Preserve runtime/alliance, the failed scratch files and events.jsonl, Logfile.CSV, the MongoDB crash log/dump and completed packages/game/native/data stages. The .env internet URL remains unused. No MongoDB repair, manual file deletion, service/process/security change, installation or game rebuild is needed. Local MongoDB initialization, admin website and disconnected Alliance runtime remain pending.

This delivery records the returned identity result and changes only the next observation. Probe/backend code is unchanged. Current service implementation and a safe startup fix are still unknown.
