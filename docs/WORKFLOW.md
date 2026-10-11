# Offline Wesnoth development workflow

The project is a custom Android game client with a Windows 11 server on a local network, using Wesnoth as its starting point and MongoDB as the intended database. Development takes place on the Linux VPS. The user builds and runs the Windows server and Android app on Windows, with LDPlayer first and an Android phone afterward. Gameplay must work without internet access.

## Persistent project context

This workflow records the user's instructions from 2026-10-11. `AGENTS.md` tells future coding sessions to read this file and `BASELINE.md`. Keep both documents in the client and server repositories. Update facts and test results as work progresses; retain the user's workflow unless the user changes it. Repository files provide continuity when chat context is unavailable.

| Directory | Purpose |
| --- | --- |
| `wesnoth_client` | Custom Android client and Windows Android build scripts |
| `wesnoth_server` | Custom Windows server and intended MongoDB integration |
| `wesnoth` | Public upstream source reference; record the exact tag/commit before copying code |
| `msys2-full` | Supplied MSYS2 archive; Windows notes specify `D:\Test\msys64` |
| `gamedata-1.19.26` | Initial data intended for offline Android packaging, potentially OBB |

## Every development cycle

1. Read the current baseline and the latest Windows report. Inspect Git status and preserve unrelated changes.
2. Make the smallest complete change toward the current milestone. Keep client protocol, server protocol, native libraries and game data compatible.
3. Run meaningful available checks on the VPS. Identify separately what needs Windows, LDPlayer, a physical phone, or MongoDB. A Linux build does not establish Windows or Android runtime success.
4. Review and stage explicit files. Never stage credentials, `.env`, private keys, signing stores, reports, generated binaries, dependency caches, or incomplete placeholder source accidentally.
5. Commit and push the changed repositories to their configured GitHub remotes. The user has authorized this cycle. Report the actual branch and commit IDs, and say explicitly if a push fails. Do not force-push or overwrite user work.
6. Give the user exact transfer/pull, build, run and test commands with the working directory, shell, selected device/ABI and required paths. Include expected visible results and log filenames. If the current delivery is diagnostic-only, say that game build/run is blocked rather than supplying an unverified success command.
7. The user tests on Windows and returns results/logs. Compare observed and expected behavior, update the baseline and continue with the next fix. Ask focused questions whenever missing information matters.

## Version matching and offline operation

Inventory Windows before selecting or upgrading tool versions. Record the active MSYS2 environment, compiler/dependencies, Python/SCons, JDK, Gradle/AGP, Android SDK/NDK/build-tools, LDPlayer Android API/ABI, MongoDB server/shell and Git versions. Pin supported versions after reviewing the report. Maintain separate Linux and Windows host tools where required; matching project/toolchain inputs is possible, identical operating systems and executable binaries are not.

Do not infer an installed version from a directory or archive filename alone. Test the actual selected tools. Keep MINGW64 and UCRT64 runtimes/dependencies consistent. Record exact source/data revisions and APK package ID, versionCode, versionName and ABI once recovered.

Offline builds need the pinned dependencies and Gradle artifacts already cached locally. Prepare missing installers, archives, checksums, Gradle dependencies and package metadata on a connected computer before moving them to Windows. Never run package upgrades or download-dependent commands as part of offline testing. Use Gradle `--offline` when the build is ready and verify that native dependency scripts also avoid downloads.

The user confirmed on 2026-10-11 that Windows temporarily connects to GitHub to pull updates, then returns to offline use. GitHub is the normal delivery route; do not ask the user to choose a transfer method again. Use `git pull --ff-only origin main` in the appropriate clean checkout. Never erase uncommitted Windows source to make a pull succeed. Git bundles remain an optional fallback if connectivity changes.

## First environment check

**Current blocker:** the server retry failed again, and Resource Monitor returned no matching handles. See "Capture the recurring Git failure" below for the next step. The original access probe and retry instructions are retained for reference; their results are recorded in `BASELINE.md`.

The user now confirms that both repositories are already cloned at the following paths. Use these existing checkouts; an additional diagnostics checkout is unnecessary.

| Windows path | Purpose |
| --- | --- |
| `D:\Test\wesnoth-setup` | Workspace parent |
| `D:\Test\wesnoth-setup\wesnoth_client` | Existing client clone |
| `D:\Test\wesnoth-setup\wesnoth_server` | Existing server clone |
| `D:\Test\msys64` | Installed MSYS2 folder |

The first collector run was interrupted with Ctrl+C and saved a partial report after Git version results. Keep LDPlayer running and temporarily connect to GitHub to update the existing server. The installed Git for Windows path below is confirmed by the user's report. The client does not need updating for this diagnostic step.

```powershell
Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
& 'C:\Program Files\Git\cmd\git.exe' pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Git pull failed. Send the error output.' }

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '.\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
```

The report is saved under `D:\Test\wesnoth-setup\wesnoth_server\diagnostics`, which the user has confirmed exists. The header must show collector version `2026-10-11.2` and the script's SHA256. Let the process finish; file scans and MSYS2 probes may take several minutes. The expected footer is `Collection COMPLETE: 10/10 sections finished`. This means inventory finished, not that the game builds or runs. Missing dependencies or empty source files may still be BLOCKED. If the report is INCOMPLETE, it names the last check reached and unfinished sections and the command exits 2; send that report too.

`ExecutionPolicy Bypass` applies only to this PowerShell process. No new PowerShell or toolchain installation is needed for this rerun. The script checks local versions and file sizes without installing packages, starting the game/server/database, or reading `.env` values. ADB inspection may start its normal local background daemon. The initial report in the server's `diagnostics` directory remains a record of the earlier attempt.

Preserve uncommitted changes if a pull reports a conflict; send its error rather than resetting or deleting files. Never clone into `D:\Test\wesnoth-setup` itself. If SDK, emulator or ADB are outside standard locations, pass the optional path parameters documented in the script. The MSYS2 scan has a 240-second timeout and prints a progress message before it starts.

Return the complete report, including UNKNOWN/BLOCKED entries. Copies downloaded from this VPS are not evidence of an independent intact source backup. Local filesystem paths and device serials appear in the report; remove those if desired. Do not send `.env`, access tokens, keystores or full environment-variable dumps.

## Windows Git object access check

Use a normal PowerShell window under the same Windows account that ran the failed pulls. Close Git GUI clients and editors using these repositories before checking. Keep the existing clones and files. This command displays attributes and [Windows access rules](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls), then creates, writes, renames and deletes a uniquely named temporary file in each affected directory. It does not change permissions or existing Git objects, and does not read remotes or `.env`.

```powershell
$log = Join-Path $env:TEMP ('wesnoth-git-access-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt')
& {
    $base = 'D:\Test\wesnoth-setup'
    'USER SID: ' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $cases = @(
        @{ Repo='wesnoth_server'; Files=@('3c\5b8ba048292a2d0c653a82b63a1200954960a4','55\f35e7bc6a52888fb99d49961e547b7eafc661e') }
        @{ Repo='wesnoth_client'; Files=@('1a\38d17a9f4e05ee1e2a9b38a23c6bc0bc448308') }
    )
    function Test-GitFolderWrite([string]$folder) {
        if (-not (Test-Path -LiteralPath $folder -PathType Container)) { "MISSING FOLDER: $folder"; return }
        $p = Join-Path $folder ('tmp_obj_wesnoth_probe_' + [guid]::NewGuid().ToString('N'))
        $created = $false; $stream = $null; $step = 'create'
        try {
            $stream = [IO.File]::Open($p, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $created = $true; $step = 'write'
            $stream.WriteByte(87); $stream.Dispose(); $stream = $null
            $step = 'rename'; [IO.File]::Move($p, ($p + '.renamed')); $p += '.renamed'
            $step = 'delete'; [IO.File]::Delete($p); $created = $false
            "PROBE PASS: $folder (create/write/rename/delete)"
        } catch { "PROBE FAIL: $folder; step=$step; $($_.Exception.Message)" }
        finally {
            if ($null -ne $stream) { $stream.Dispose() }
            if ($created) {
                try { [IO.File]::Delete($p) }
                catch { "PROBE CLEANUP FAILED: $p; $($_.Exception.Message)" }
            }
        }
    }
    foreach ($case in $cases) {
        $objects = Join-Path (Join-Path $base $case.Repo) '.git\objects'
        $folders = @($objects) + @($case.Files | ForEach-Object { Join-Path $objects (Split-Path $_ -Parent) })
        $files = @($case.Files | ForEach-Object { Join-Path $objects $_ })
        foreach ($p in ($folders + $files)) {
            try {
                $item = Get-Item -LiteralPath $p -Force -ErrorAction Stop
                'ATTR: {0}; {1}; length={2}' -f $p, $item.Attributes, $item.Length
                'OWNER: ' + (Get-Acl -LiteralPath $p -ErrorAction Stop).Owner
                & "$env:SystemRoot\System32\icacls.exe" $p
            } catch { "INSPECT: $p; $($_.Exception.Message)" }
        }
        foreach ($folder in $folders) { Test-GitFolderWrite $folder }
    }
} 2>&1 | Tee-Object -FilePath $log
"Report saved to: $log"
```

Expected: five `PROBE PASS` lines if the object root directories and the three affected hash directories all allow these operations. A missing final hash file is possible after a failed fetch; the report records it without creating a replacement. Send the complete output, including `PROBE FAIL`, missing-path and cleanup messages. Account identifiers and paths appear in the report. A passing probe does not establish that Git can finalize those exact objects. The helper's syntax and temporary-file operations were checked using Linux PowerShell 7.4.6. The user's actual Windows run returned four passes and one rename sharing violation; this check is complete and the next step is below.

If access rules show a permission problem, back up the affected directory ACLs with `icacls /save` before adding current-user Modify access. Preserve other users' grants and explicit denies; do not use `Everyone`, ACL resets, ownership takeover or blanket attribute clearing. Request elevation only if the specific repair needs it, retaining the normal user's identity. Resume `git pull --ff-only origin main` and the environment collector after resolving the failure. Game build/run remains blocked by the incomplete environment/source inventory.

## Windows file lock retry

This retry has already been attempted: the server failed before the client was reached. Proceed to the capture below rather than repeating the restart or unobserved pulls.

The returned report shows Modify access and a sharing violation while renaming a newly written temporary file. The locking program is not yet identified. Additional ACL grants or administrator-mode Git are not justified by this result.

Save open work and restart Windows once. Temporarily connect to GitHub, open a normal PowerShell window and retry before reopening editors or Git GUI applications. This is an attempt to release existing handles, not a confirmed fix; a background application may recreate the lock.

```powershell
& {
    $git = 'C:\Program Files\Git\cmd\git.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = Join-Path 'D:\Test\wesnoth-setup' $name
        Write-Host "Updating $name"
        & $git -C $repo pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop here and send the error output." }
    }
    Write-Host 'Both pulls completed successfully.'
}
```

After both pulls succeed, start LDPlayer and run the inventory in normal PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
```

Expected: both pulls exit successfully, followed by collector version `2026-10-11.2` and `Collection COMPLETE: 10/10 sections finished`. Return the latest report from `wesnoth_server\diagnostics`, including missing-tool or incomplete-section results. This does not establish a game build or successful play.

If a pull fails again, send the error and run `resmon.exe`. Open **CPU > Associated Handles**, search for `wesnoth-setup`, and report the **Image**, **PID**, and **Handle Name** columns. This is Microsoft's [built-in method for finding processes with open files](https://techcommunity.microsoft.com/blog/itopstalkblog/identify-which-process-is-blocking-a-file-in-windows/4432635). A matching open handle is a lead, not proof that the process blocked rename. Do not force-close handles or terminate an unidentified process. If the search is empty, report that too: the observed lock may be brief. A repeat failure with no visible handle calls for a [Process Monitor](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon) capture filtered to the repository paths during reproduction, preserving events from all processes. Do not replace tracing with repeated reboots, permission resets or antivirus exclusions.

## Capture the recurring Git failure

Resource Monitor found no matching handles. Use [Microsoft Process Monitor](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon) to record file operations while the error occurs; a snapshot of current handles can miss brief interference. This diagnostic requires no repository update first.

1. Download the [official Process Monitor ZIP](https://download.sysinternals.com/files/ProcessMonitor.zip), extract it, and run `Procmon64.exe` as administrator. Elevation is for the tracing tool only; keep Git in the normal user's PowerShell window.
2. Stop capture with **Ctrl+E**, then clear existing events with **Ctrl+X**. Use **Ctrl+L** to open filters, reset previous filters, and add **Path / begins with / `D:\Test\wesnoth-setup\wesnoth_server\.git\objects` / Include**. Click **Add**, then **OK**. Keep filesystem events enabled. Do not restrict Process Name or Result; successful opens by another process can explain Git's later failure.
3. Start capture with **Ctrl+E**, then run the following command once in normal PowerShell:

```powershell
& 'C:\Program Files\Git\cmd\git.exe' `
  -C 'D:\Test\wesnoth-setup\wesnoth_server' pull --ff-only origin main
```

4. Immediately stop capture with **Ctrl+E** after Git finishes or fails. Save with **File > Save > Events displayed using current filter**, choose **CSV**, and use `D:\Test\git-objects.csv`.
5. Return that filtered CSV and Git's terminal output. Keep the event columns **Time of Day, Process Name, PID, Operation, Path, Result, Detail**. Do not send an unfiltered capture or PML file, which can include unrelated process metadata. If Git unexpectedly succeeds, send that result and the capture too.

Expected: filesystem events under the server's `.git\objects` directory during this one retry. They may show `SHARING VIOLATION` or `ACCESS DENIED`; neither a specific result nor the responsible program is guaranteed in advance. An empty CSV means the capture/filter needs checking. Review preceding opens and their sharing modes before assigning blame to a process; the process reporting an error can be the victim. Resume the collector only after the needed update succeeds. This trace has not yet been run on Windows.

## First play acceptance

The first milestone is complete only when all relevant checks have actual evidence:

- Source files are recovered, tracked and matched to compatible game data. Versions and offline dependency caches are recorded.
- A nonempty Android APK builds on Windows; a nonempty server executable starts with its DLLs. Preserve build logs and exact commit IDs.
- The Android app launches in LDPlayer and reads local game data with internet unavailable. Offline asset import and any OBB support must be implemented and tested before claiming support.
- A local single-player scenario loads and completes at least one turn.
- The server listens on the agreed LAN interface/port. The client reaches the server, enters the lobby, creates/joins a game and completes a turn. Confirm the emulator's route to the Windows host instead of assuming that Android `localhost` is the Windows computer. A phone uses the Windows LAN IP on a reachable local network.
- MongoDB runs locally on Windows and the chosen persistence behavior is exercised after integration. Guest LAN play may be a useful earlier checkpoint, but does not establish MongoDB integration.
- Close/reopen behavior, save/load when supported, and relevant logs are checked. Repeat the offline launch and gameplay checks on the physical Android device.
- At least one complete fix → commit → push → transfer/pull → build → run → report cycle succeeds.

## Test report format

Include the client and server commit IDs; Windows report filename; exact command and shell; selected emulator/device and ABI; expected result; actual result; full relevant build error or server log; and Android logcat around the failure. Record the last successful step. Remove secrets before sharing logs.

Future handoffs should update `BASELINE.md` with confirmed versions, commands that actually ran, results, remaining blockers and the next action.
