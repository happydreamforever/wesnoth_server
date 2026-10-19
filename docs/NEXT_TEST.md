# Next check: finish transferring the retained module list

The user supplied 31 module rows. The paste cuts off in the CRYPTSP.dll version field at `WinBuild.160`; it cannot yet establish a complete module inventory. A direct range comparison of all 31 rows against all 13 unknown stack addresses found no matches.

The unknown callers range from `0x1002d3e8` to `0x1010a733`. The returned `libeay64.dll` entry covers `[0x732f0000, 0x73307000)`, so it does not identify those callers. Its Company and Version fields are blank; its publisher, signature and role remain unverified. The two `svchost.exe` entries likewise do not establish a cause. No component is classified as malicious or safe on this evidence.

## One step: attach the existing text

1. Use the same retained event's **Event Properties → Process** tab. The event is **2:23:41.9316899 PM / svchost.exe / PID4600 / CreateFile / SUCCESS**, scratch path ending `mongo-file-probe-sdynefqx\WiredTiger.turtle.set`.
2. If the complete copied text is already in Notepad, use it. Otherwise click **Copy All** and paste into Notepad. Keep only the **Modules** section, including all rows and the columns Module, Address, Size, Path, Company and any version information.
3. Save it as a new `D:\Test\mongo-modules.txt` (choose another name if that file already contains different evidence), then attach the file instead of pasting the long text into chat. Do not include command lines, environment or the entire PML.
4. If the retained Modules table itself ends at CRYPTSP.dll, or the clipboard also ends mid-field, report that exact result. Screenshots of the existing table are an acceptable fallback; no new capture is needed.

Expected result: a complete file without the chat cutoff, or confirmation that the retained source itself is incomplete. The visible rows are in ascending address order, so do not promise that later rows will match the lower unknown addresses. Completing this transfer establishes what was recorded and allows the next diagnostic to be selected on that basis.

Keep the capture stopped and MongoDB stopped. No pull, command, build, download, probe rerun, new capture, database repair/deletion or process/service/security change is needed. Preserve the existing runtime, scratch files/report, CSV/capture, MongoDB crash evidence and all completed game/native/data stages. The internet .env URL remains unused.

If the complete inventory still has no matching module, proceed to a narrowly scoped, process-identity-guarded memory-region metadata query for the exact caller addresses. Do not repeat broad inventories or infer a module identity from its filename or missing version fields. No new memory query is delivered in this step. Local MongoDB initialization, administrator setup and offline Alliance validation remain pending.
