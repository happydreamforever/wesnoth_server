# Next test: capture a scratch-file sharing probe

The user reports **no matching handles** in Resource Monitor. This does not contradict the logged MongoDB sharing failure: a brief lock can disappear before inspection. The process responsible remains unknown. Leave the real MongoDB stopped and its runtime intact.

The new probe creates only a unique `diagnostics\mongo-file-probe-*` folder. It makes up to 20 small file replacements using `WiredTiger.turtle.set` and `WiredTiger.turtle`, stops at the first error, and retains all surviving scratch files and `events.jsonl`. It never starts MongoDB or reads its data/configuration or `.env`. This is a generic filesystem reproduction: success does not prove MongoDB is fixed, because its path, executable and timing differ.

## 1. Get the diagnostic helper

In normal PowerShell, temporarily connected to GitHub, update only the existing server checkout:

```powershell
& {
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $bash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Pull failed. Stop and send the output.' }
}
```

Client changes only mirror these records and can be pulled during the next normal update. No game build, MongoDB reinstall or dependency download is needed. The probe and capture work without internet.

## 2. Capture one probe

Use the existing **Microsoft Process Monitor** (`Procmon64.exe` or `Procmon.exe`) from the earlier Git capture. Run it as administrator; keep the probe in your normal PowerShell window. If you cannot find/open Process Monitor, stop here and report that; do not start MongoDB instead. [Microsoft's documentation](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon) describes its filesystem tracing and filtering.

1. Stop capture with **Ctrl+E** if it is active, then clear events with **Ctrl+X**.
2. Open **Filter → Filter** (**Ctrl+L**), reset old filters, and add exactly:
   - **Path** / **begins with** / `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\mongo-file-probe-` / **Include**
3. Click **Add**, then **OK**. Keep filesystem activity enabled. Do not add a Process Name or Result restriction: successful opens by other processes may explain a later sharing failure. Keep default columns **Time of Day, Process Name, PID, Operation, Path, Result, Detail**.
4. Start capture with **Ctrl+E**. Immediately run this once in normal PowerShell:

```powershell
& {
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Native Windows Python is missing. Stop and send this output.'
    }
    & $python -I -B 'D:\Test\wesnoth-setup\wesnoth_server\tools\probe_windows_file_sharing.py'
    "PROBE_EXIT: $LASTEXITCODE"
}
```

5. When the command returns, stop capture immediately with **Ctrl+E**, whether the probe passed or failed. If it remains blocked, stop capture and report that rather than running another copy.
6. **File → Save → Events displayed using current filter → CSV**. Save as `D:\Test\mongo-file-probe.csv` (choose a new name if that already exists).
7. Send that filtered CSV, the printed `events.jsonl` report, and console output. Keep the Process Monitor session/PML local; do not upload an unfiltered trace, credentials, database files or crash dump.

Expected: a printed scratch-folder/report path, then either `FILE PROBE COMPLETED` (exit0), `FILE PROBE FAILED` with operation/errno/winerror (exit1), or `PROBE COLLECTION ERROR` (exit2). Keep any partial report and return errors too. An empty trace means filtering/capture timing needs checking; it is not proof that no conflict occurred. The attempt count and programmed pauses are bounded; individual Windows I/O calls may take longer.

## Interpretation and preservation

A sharing failure captured alongside an incompatible overlapping file open may identify the blocker. Other error codes need separate interpretation. A passing probe is only a negative reproduction; a later isolated MongoDB startup with a new empty data path may be needed. No database startup success or repair is claimed by this test.

Leave the real `runtime\alliance`, its crash log/dump, installed packages, APK/OBB, MSYS2 and native stages in place. Do not retry initialization, delete/rename real WiredTiger files, remove locks, repair the database or terminate/change unidentified processes/services/security settings. The selected deployment remains local Windows MongoDB; the `.env` internet URL must not be used. Initialization, admin website and disconnected Alliance operation remain pending.
