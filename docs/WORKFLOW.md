# Offline Wesnoth development workflow

**Offline logout/relogin accepted; app restart next (2026-10-20):** The user supplies the repeat Logged in profile and explicitly confirms the exact server-revoked logout message, matching separate personal-leader request and WAN disconnected throughout with Ethernet retained. Accept server logout acknowledgement and repeat account access at user-observed scope; no old-token replay or independent network trace is claimed. Current NEXT_TEST.md keeps the session logged in, closes the profile, chooses Back to game then the actual main-menu Quit, and reopens Wesnoth Offline in LDPlayer. Verify the trusted server remains saved, Start game/Alliance requires login, and fresh UniPlayer login plus leader view returns the same on-screen ID/Spearman/level1/zero XP. Do not log out before this restart test. Keep all three backend windows and local Ethernet running with WAN disconnected. No command, pull, rebuild, reinstall, profile reimport, new account or database restart is needed. App restart, unavailable-service and player persistence across backend restart remain untested; campaign/team gameplay is later work.

**Windows account bridge build accepted (2026-10-20):** The returned console reports both native compile/link steps, ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED and ALLIANCE ACCOUNT BRIDGE BUILD PASSED, saved as diagnostics/alliance-bridge-build-20261020-101034-914-4f9607a9e56445d4a9e8df9db469ca65.txt. Actual CMake4.3.0/Ninja1.13.2/GCC16.2.0/MINGW64/OpenSSL3.6.3/zlib1.3.2 are shown. This establishes Windows build/artifact verification; listener startup, Android account connection and WAN-disconnected account acceptance remain pending. WAN status and pulled commit IDs were not supplied for this build. Next run the existing Run-WindowsAllianceBridge.ps1 with the LOCALAPPDATA/WesnothAlliance/runtime database configuration and D:\Test\wesnoth-setup\msys64. Keep healthy database/admin windows open; start their existing helpers only if closed. No pull, rebuild, dependency preparation, database initialization, OBB transfer or old transport rerun is needed for this documentation checkpoint. Preserve the existing game, all native stages, public/private identity, profile database and areas. Account registration/login/leader/logout code and VPS real MongoDB integration are complete; actual account APK build/install follows bridge startup acceptance, one step at a time. Team gameplay and custom campaign rewards remain later milestones.

The project is a custom Android game client with a Windows 11 server on a local network, using Wesnoth as its starting point and MongoDB as the intended database. Development takes place on the Linux VPS. The user builds and runs the Windows server and Android app on Windows, with LDPlayer only. Gameplay must work without internet access.

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
3. Run meaningful available checks on the VPS. Identify separately what needs Windows, LDPlayer, or MongoDB. A Linux build does not establish Windows or Android runtime success.
4. Review and stage explicit files. Never stage credentials, `.env`, private keys, signing stores, reports, generated binaries, dependency caches, or incomplete placeholder source accidentally.
5. Commit and push the changed repositories to their configured GitHub remotes. The user has authorized this cycle. Report the actual branch and commit IDs, and say explicitly if a push fails. Do not force-push or overwrite user work.
6. Give the user exact transfer/pull, build, run and test commands with the working directory, shell, selected device/ABI and required paths. Include expected visible results and log filenames. If the current delivery is diagnostic-only, say that game build/run is blocked rather than supplying an unverified success command.
7. The user tests on Windows and returns results/logs. Compare observed and expected behavior, update the baseline and continue with the next fix. Ask focused questions whenever missing information matters.

For long results, accept attached logs or a named workspace file such as log.txt and read it directly. Do not require the user to copy lengthy terminal output. Current Windows handoffs should save output under the existing checkout's ignored diagnostics directory and print that file path so it can be returned. Keep console output visible and retain native command exit checks.

## Version matching and offline operation

Inventory Windows before selecting or upgrading tool versions. Record the active MSYS2 environment, compiler/dependencies, Python/SCons, JDK, Gradle/AGP, Android SDK/NDK/build-tools, LDPlayer Android API/ABI, MongoDB server/shell and Git versions. Pin supported versions after reviewing the report. Maintain separate Linux and Windows host tools where required; matching project/toolchain inputs is possible, identical operating systems and executable binaries are not.

Do not infer an installed version from a directory or archive filename alone. Test the actual selected tools. Keep MINGW64 and UCRT64 runtimes/dependencies consistent. Record exact source/data revisions and APK package ID, versionCode, versionName and ABI once recovered.

Offline builds need the pinned dependencies and Gradle artifacts already cached locally. Prepare missing installers, archives, checksums, Gradle dependencies and package metadata on a connected computer before moving them to Windows. Never run package upgrades or download-dependent commands as part of offline testing. Use Gradle `--offline` when the build is ready and verify that native dependency scripts also avoid downloads.

The user confirmed on 2026-10-11 that Windows temporarily connects to GitHub to pull updates, then returns to offline use. GitHub is the normal delivery route; do not ask the user to choose a transfer method again. Use `git pull --ff-only origin main` in the appropriate clean checkout. Never erase uncommitted Windows source to make a pull succeed. Git bundles remain an optional fallback if connectivity changes.

## First environment check

**Current status (2026-10-14):** The first Windows-server/LDPlayer offline gameplay milestone is complete at the tested scope. Actual Windows pulls reached server 275f0ea/client bfa53b8; wesnothd 1.19.26 starts and listens on IPv4/IPv6 port 15000. The address helper reports Ethernet 100.99.99.14, Public profile. The user confirms the actual Android game joins the server lobby, plays against the computer, returns control after the AI turn and keeps the connection active. The user explicitly confirms internet/WAN was disconnected while local Ethernet stayed connected. Record gameplay and offline status as user-observed results, not an independently captured network trace. Earlier actual APK build, game-data OBB/import and local-turn results remain valid. Preserve all completed binaries/data/stages/receipts and current MSYS2 D:\Test\wesnoth-setup\msys64. No pull, rebuild, reinstall or repeated LAN test is needed for this documentation update. Follow the requested one-step-at-a-time pace. Implementation of Alliance Battle is authorized (2026-10-19). Read docs/ALLIANCE_IMPLEMENTATION.md for the rules and commit-sized checklist. Tests use LDPlayer only; do not request a physical phone. Preserve the working guest game, OBB, native build stages and current MSYS2 root. Database, admin and custom gameplay are new milestones; completed baseline gameplay is not proof of their implementation.

The user now confirms that both repositories are already cloned at the following paths. Use these existing checkouts; an additional diagnostics checkout is unnecessary.

| Windows path | Purpose |
| --- | --- |
| `D:\Test\wesnoth-setup` | Workspace parent |
| `D:\Test\wesnoth-setup\wesnoth_client` | Existing client clone |
| `D:\Test\wesnoth-setup\wesnoth_server` | Existing server clone |
| `D:\Test\wesnoth-setup\gamedata-1.19.26` | Verified offline asset source; Windows full hash check passed |
| `D:\Test\msys64` | Historical MSYS2 root; sampled tools now missing |
| `D:\Test\wesnoth-setup\msys64` | Current verified MSYS2 root; runtime and Android compile boundary passed |

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

This capture is complete and analyzed: the conflicting handle owner is `svchost.exe` PID 15800. Continue with service identification below; another general capture is unnecessary while the same process remains available.

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

Expected: filesystem events under the server's `.git\objects` directory during this one retry. An empty CSV means the capture/filter needs checking. The actual Windows capture returned 604 events, including nine Git SHARING VIOLATION events while svchost PID 15800 held conflicting handles. See `BASELINE.md` for the event sequence. Resume the collector only after the needed update succeeds.

## Identify the captured service

The CSV identifies `svchost.exe` PID 15800 as the direct conflicting handle owner; it does not name the hosted service. In the same Windows session as the capture, run in normal PowerShell:

```powershell
tasklist.exe /svc /fi "PID eq 15800"
```

Actual result: `svchost.exe 15800 N/A`. Microsoft's [`tasklist /svc` documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tasklist) describes this read-only mapping, but this result did not identify a service. In the same normal PowerShell window, collect the targeted process and service details:

```powershell
Get-CimInstance Win32_Process -Filter 'ProcessId = 15800' |
  Format-List ProcessId,Name,ExecutablePath,CommandLine,ParentProcessId,CreationDate

Get-CimInstance Win32_Service -Filter 'ProcessId = 15800' |
  Format-List Name,DisplayName,State,StartMode
```

Return the output including blank fields or errors; no output from the second command means that query returned no service mapping. Windows documents [executable path, command line and creation time](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process) as process properties. Some executable details require additional privileges; empty fields alone are not suspicious. If they are unavailable, an elevated read-only query or the original Process Monitor process properties may be needed. Keep Git operations in the normal user's PowerShell window.

If the process has exited or Windows restarted, the PID may be absent or reused. Report that rather than stopping another process with the same number. If the saved Process Monitor session is still available, its process properties can help identify the original hosted service. Do not kill the whole svchost process, disable an unidentified service or change antivirus exclusions. Choose a scoped repair only after identifying what was holding the files.

## Temporary packed update

**Windows result: failed.** Objects downloaded, but Git could not rename the temporary `.rev` pack index. The client was not attempted. The command below records the tested attempt; do not repeat it or change more Git options before identifying the process. Proceed to the elevated read-only lookup below.

This command-only workaround can be tried while process identification continues. It asks Git to retain received objects in a pack instead of writing individual loose objects, using [`fetch.unpackLimit`](https://github.com/git-for-windows/git/blob/v2.53.0.windows.2/Documentation/config/fetch.adoc#L29-L38). It has passed isolated Linux verification described in `BASELINE.md`; Windows interference may still affect other writes. The underlying process problem remains open even if the update succeeds.

Temporarily connect to GitHub. In normal PowerShell, paste this entire block and press Enter:

```powershell
& {
    $git = 'C:\Program Files\Git\cmd\git.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = Join-Path 'D:\Test\wesnoth-setup' $name
        Write-Host "Updating $name using packed objects"
        & $git -c fetch.unpackLimit=1 -C $repo pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Update failed for $name. Stop here and send the complete output."
        }
    }
    Write-Host 'Both updates completed successfully.'
}
```

Expected: `Both updates completed successfully.` The setting is not saved in Git configuration. If either update fails, return the full output; a failure at a different path is useful evidence. Do not reset or delete local files to bypass a conflict. Stop after this one attempt if it fails.

After both updates succeed, start LDPlayer, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
```

Let it finish. Expected: collector version `2026-10-11.2`, then `Collection COMPLETE: 10/10 sections finished`. Return the report from `wesnoth_server\diagnostics`, including BLOCKED/UNKNOWN or incomplete results. Game build/run is still pending source recovery and this environment inventory.

## Elevated process identification

The normal-user lookup returned blank executable path and command line for PID 15800, parent PID 4152, and no service mapping. Microsoft marks the [ExecutablePath property](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process) as requiring additional privileges. An elevated read may provide the missing details; it is not guaranteed for every process.

Open Start, type **Windows PowerShell**, right-click that result and choose **Run as administrator**, then accept the Windows prompt. Paste this entire block into the new window and press Enter. It validates elevation and only reads process, service and file-signature information. It does not run Git or stop/change anything.

```powershell
& {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $admin = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        'STOP: Open Windows PowerShell using Run as administrator.'; return
    }
    'ADMIN: True'
    $target = Get-CimInstance Win32_Process -Filter 'ProcessId = 15800' -ErrorAction Stop
    if (-not $target) { 'PID 15800 is no longer running.'; return }
    $parent = $null
    if ($target.ParentProcessId -gt 0) {
        $parent = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $target.ParentProcessId) -ErrorAction Stop
    }
    foreach ($entry in @(@{Role='TARGET';Data=$target},@{Role='CURRENT PARENT';Data=$parent})) {
        'Inspecting: ' + $entry.Role
        $process = $entry.Data
        if (-not $process) { 'Process no longer running.'; continue }
        $process | Format-List ProcessId,Name,ExecutablePath,ParentProcessId,CreationDate
        if ($entry.Role -eq 'TARGET') { 'CommandLine: ' + $process.CommandLine }
        if ($process.ExecutablePath) {
            try {
                $file = Get-Item -LiteralPath $process.ExecutablePath -ErrorAction Stop
                $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName -ErrorAction Stop
                $file.VersionInfo | Format-List CompanyName,FileDescription,FileVersion
                $signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { '(none)' }
                'SIGNATURE: {0}; SIGNER: {1}' -f $signature.Status,$signer
            } catch { 'FILE INSPECTION: ' + $_.Exception.Message }
        } else { 'Executable path remains unavailable in this elevated session.' }
        $services = @(Get-CimInstance Win32_Service -Filter ('ProcessId = ' + $process.ProcessId) -ErrorAction Stop)
        if ($services.Count) { $services | Format-Table ProcessId,Name,DisplayName,State -AutoSize }
        else { 'No matching service.' }
    }
}
```

Return the complete output. Expected first line: `ADMIN: True`, followed by target/parent details, signature information where the path is available, and service mappings or explicit absence messages. The parent PID is queried at the time of inspection and may have been reused; compare its creation time with the target before treating it as the original parent. File version strings and signature status are evidence to review, not standalone proof of process behavior. [Get-AuthenticodeSignature](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-authenticodesignature?view=powershell-5.1) reads signature information; it does not execute the inspected file. No definitive process repair or new pull should be prescribed from blank fields alone.

## NetActvity service configuration

The elevated result associates current parent PID 4152 with the running service named exactly `NetActvity`. The direct Git-blocking process remains PID 15800, which has no service mapping. Both paths are `C:\Windows\SysWOW64\svchost.exe`, with valid Microsoft signatures; this identifies the host files, not the service's code or publisher. The parent's reported creation time precedes the child's. The trace establishes the child's conflicting file opens, but does not yet establish that stopping the parent service would stop that child or restore Git.

In the existing **Administrator: Windows PowerShell** window, paste this entire block and press Enter. If that window is closed, use Start, type Windows PowerShell, right-click it, choose Run as administrator, and accept the Windows prompt. No Git pull or downloaded helper is needed for this check.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $name = 'NetActvity'
    $service = Get-CimInstance Win32_Service -Filter "Name='$name'"
    if (-not $service) { 'Service no longer found.'; return }

    'SERVICE CONFIGURATION'
    $service | Format-List Name,DisplayName,Description,State,StartMode,StartName,PathName,ProcessId,AcceptStop

    'SERVICE PROCESS'
    if ($service.ProcessId -gt 0) {
        Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $service.ProcessId) |
            Format-List ProcessId,ExecutablePath,CommandLine,CreationDate
    } else { 'Service has no running process.' }

    $key = 'HKLM:\SYSTEM\CurrentControlSet\Services\NetActvity'
    foreach ($path in @($key, "$key\Parameters")) {
        'REGISTRY: ' + $path
        if (Test-Path -LiteralPath $path) {
            Get-ItemProperty -LiteralPath $path |
                Format-List ImagePath,Description,ServiceDll,ServiceMain,DependOnService
        } else { 'Key not present.' }
    }

    'SERVICE DEPENDENCIES'
    Get-Service -Name $name |
        Format-List Name,Status,CanStop,ServicesDependedOn,DependentServices
}
```

Expected: SERVICE CONFIGURATION, SERVICE PROCESS, the two REGISTRY sections, and SERVICE DEPENDENCIES. Return all output, including empty fields, `Key not present.` messages or errors. The block reads only the named service's configuration and current process metadata. It also reads any configured `ServiceDll` and `ServiceMain` values; those values are not guaranteed to exist or identify all loaded code. It does not read `.env` or the full registry/environment. Review command-line/path output for private information before sharing.

Use the [service configuration properties](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-service) and [dependency information](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/get-service?view=powershell-5.1) to identify the component and choose the next repair. A signature check on a host executable alone does not establish the identity of hosted code. No service is stopped, disabled or deleted by this block. Do not terminate generic svchost processes, add antivirus exclusions, reset permissions or repeat the failed packed-update flags. A temporary service stop/test/start may be considered once the component and its impact are understood; explicitly verify the blocking child afterward because stopping a parent does not establish that the child exited. Git should continue to run in the normal-user session.

Verification: the pasted block parses using the VPS PowerShell 7.4.6 verifier and uses Windows PowerShell 5.1 syntax. The user has now run it on Windows and returned the blank configuration/missing-key results recorded below. Git repair, game builds and runtime tests remain blocked.

## Native service state and installation history

The latest Windows check completed. NetActvity is Running with PID 4152 and AcceptStop/CanStop True, but Description, StartName and PathName are blank, StartMode is Unknown, and both the service key and Parameters key are reported absent. Its current host command line is `C:\Windows\SysWOW64\svchost.exe -k netsvcs -p`. No dependency entries were returned. This is insufficient to identify the component or guarantee it can restart.

Use the same **Administrator: Windows PowerShell** window. Paste the entire block and press Enter; no Git pull is needed. If that window is closed, open Start, type Windows PowerShell, right-click it, select Run as administrator, and accept the Windows prompt.

```powershell
& {
    'NATIVE SERVICE CONFIGURATION'
    sc.exe qc NetActvity
    "SC_QC_EXIT: $LASTEXITCODE"

    'NATIVE SERVICE STATUS'
    sc.exe queryex NetActvity
    "SC_QUERYEX_EXIT: $LASTEXITCODE"

    'SERVICE INSTALLATION RECORD'
    $query = "*[System[Provider[@Name='Service Control Manager'] and EventID=7045] and EventData[Data[@Name='ServiceName']='NetActvity']]"
    try {
        Get-WinEvent -LogName System -FilterXPath $query -MaxEvents 5 -ErrorAction Stop |
            Format-List TimeCreated,Id,Message
    } catch {
        if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') {
            'No matching installation event found in the retained System log.'
        } else { 'EVENT LOOKUP ERROR: ' + $_.Exception.Message }
    }

    'LAST WINDOWS BOOT'
    Get-CimInstance Win32_OperatingSystem |
        Format-List LastBootUpTime
}
```

Expected: native service configuration/status output or explicit SC errors, up to five matching service-installation events, and the last Windows boot time. Return all output, including exit codes and errors. `sc.exe` is intentional; `sc` alone is a different PowerShell alias. The [SC commands](https://learn.microsoft.com/en-us/windows/win32/services/configuring-a-service-using-sc) query the Service Control Manager directly. The [event query](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.diagnostics/get-winevent?view=powershell-5.1) filters the System log to installation event 7045 for exactly NetActvity; it does not dump unrelated events. The record may preserve an original binary path/account even when current configuration is unavailable. Missing retained events do not establish that installation never occurred. Review service command lines for private data before sharing.

The observed mismatch does not prove malware, legitimacy or a specific deletion mechanism. Microsoft's [DeleteService lifecycle](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-deleteservice) distinguishes a running service marked for deletion from final removal after it stops and all service handles close; absent registry keys alone do not establish that lifecycle. Do not promise Stop-Service followed by Start-Service is reversible when configuration cannot be read. Do not recreate a guessed service key, stop/delete this unidentified service, terminate generic svchost processes, suspend the captured process while it may hold a handle, or add speculative Git flags. Preserve the current process state for these focused reads. Query boot time because the service process still reports an October 1 creation date and an actual full restart has not been established.

Verification: the block's syntax parses with Linux PowerShell 7.4.6. The user ran it on Windows: qc failed with error 2 querying delayed autostart, queryex returned Running PID 4152, no installation record was found, and boot time was October 1. Successful updates and the complete environment inventory remain pending; no game build/run is verified.

## Full Windows restart and guarded update

The native check now establishes LastBootUpTime `10/1/2026 9:09:03 PM`. No full Windows restart has occurred since that boot; the earlier suggested restart was not verified and is not a failed recovery test. `sc.exe qc NetActvity` failed specifically while querying the delayed-autostart flag with error 2, while queryex still reported Running PID 4152. No matching installation event was found in the retained System log.

Save open work and close the emulator/development applications, then use **Start → Power → Restart** on Windows. Restart performs a full boot cycle; ordinary shutdown may retain system state through Fast Startup. See Microsoft's [power-state documentation](https://learn.microsoft.com/en-us/windows/win32/power/system-power-states). Do not force power off or change Fast Startup settings. This restarts the Windows session and tests Git afterward; it does not guarantee restoration of the unidentified service. Its registration may remain absent or be recreated by other software, and its role is still unknown.

After signing back in, temporarily connect to GitHub and open a **normal Windows PowerShell** window. Run the following before reopening LDPlayer or the development applications:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    'WINDOWS BOOT TIME'
    Get-CimInstance Win32_OperatingSystem | Format-List LastBootUpTime

    'NETACTVITY AFTER RESTART'
    sc.exe queryex NetActvity
    "SC_QUERYEX_EXIT: $LASTEXITCODE"

    $git = 'C:\Program Files\Git\cmd\git.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = Join-Path 'D:\Test\wesnoth-setup' $name
        Write-Host "Updating $name"
        & $git -C $repo pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Pull failed for $name. Stop here and send all output."
        }
        & $git -C $repo rev-parse --short HEAD
    }
    'Both updates completed successfully.'
}
```

Expected: boot time reflects the restart just performed, followed by service status or a native error, then both successful pulls and their commit IDs. Error 1060 (service does not exist) is one possible service-query result and does not prevent attempting Git; it is not required for a successful update. The service query's exit code is informational. If the boot time still shows the old boot, a new full boot has not been demonstrated. Do not reuse old PIDs 4152/15800 to control processes after restarting; PIDs may be assigned to unrelated processes.

If either pull fails, the block stops. Return its full output, including boot/service information and the Git failure. Preserve local files; do not reset, reclone, alter permissions, delete objects, or repeat the packed-fetch workaround. A fresh failure after a confirmed restart is new evidence, and the earlier trace does not establish which new process caused it.

Only after **Both updates completed successfully.**, start LDPlayer, wait for Android to finish booting, and run in normal PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
"COLLECTOR_EXIT: $LASTEXITCODE"
```

Expected: collector version `2026-10-11.2`, a script SHA256, all ten inventory sections, footer `Collection COMPLETE: 10/10 sections finished`, and exit 0. Let the scan finish; MSYS2 probes may take several minutes. Return the latest report under `D:\Test\wesnoth-setup\wesnoth_server\diagnostics`, including any BLOCKED/UNKNOWN entries. If the report is INCOMPLETE or the collector exits nonzero, return that report/output too. Inventory completion does not establish a working build, server, APK or gameplay.

Verification: both pasted blocks parse with the Linux PowerShell 7.4.6 verifier. The user confirmed the restart and new boot time, but the server pull failed again; client update and collector were not reached. The next test uses the existing MSYS2 Git below. Game build/run remains blocked on source recovery and environment confirmation.

## Use the already installed MSYS2 Git

**This MSYS2 update route has now succeeded on Windows.** Server reached ebfb18d and client f35d0af, followed by a complete collector run. Keep the commands below as the project's Windows update route. Historically, the full restart did not restore native Git: NetActvity returned Running under PID 4172 and the server pull failed at object `55/eb0340cb3a6018aee02ed2e87cecf41a08bc0b`. The earlier direct locker PID 15800 must not be reused for process actions.

This route uses the user's existing `D:\Test\wesnoth-setup\msys64\usr\bin\git.exe` (confirmed version 2.55.0) through its MSYS2 Bash and runtime `3.6.10-8fbd9808.x86_64`. [MSYS2 distinguishes its runtime-based Git from native Windows Git](https://www.msys2.org/docs/git/). In the installed Git for Windows version, [opening the rename source with DELETE access returns immediately on failure](https://github.com/git-for-windows/git/blob/v2.53.0.windows.2/compat/mingw.c#L2970-L2978). The [MSYS2 runtime implementation](https://github.com/msys2/msys2-runtime/blob/cf8cb2aaf2102d0e8ca382790970b2b2ded0680b/winsup/cygwin/syscalls.cc#L2632-L2650) waits and retries source opens on sharing violations. The successful MSYS2 pulls are consistent with avoiding the earlier brief conflict through retry handling; there was no trace of the successful run to prove each internal retry. This establishes a working update route, not the unidentified service's purpose or a repair to native Git.

Connect to GitHub and open **Windows PowerShell normally**: click the Start-menu result without choosing Run as administrator. Close any other Git commands. Paste the entire block and press Enter:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $bash --noprofile --norc -c '/usr/bin/git --version && /usr/bin/uname -r'
    if ($LASTEXITCODE -ne 0) { throw 'MSYS2 check failed. Send all output.' }

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name with MSYS2 Git"
        $command = 'PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main'
        & $bash --noprofile --norc -c $command
        if ($LASTEXITCODE -ne 0) {
            throw "MSYS2 pull failed for $name. Stop here and send all output."
        }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send all output." }
    }
    'Both updates completed successfully using MSYS2 Git.'
}
```

This selects /usr/bin/git explicitly so a MINGW/native Git elsewhere on PATH is not chosen. The /usr/bin PATH prefix exists only for each child command; it does not change saved Windows variables, Git configuration, installed versions or service settings. The existing /d/Test/wesnoth-setup/... paths are the same Windows checkouts. Bash startup profiles are skipped. No package install/update, clone, reset or packed-fetch option is involved.

Expected: MSYS2 Git version (previously 2.55.0), active runtime version, both successful pulls and commit IDs, then `Both updates completed successfully using MSYS2 Git.` The guard stops on the first error. If authentication, credential-helper, certificate, ownership, conflict or file-write errors occur, return that output rather than falling back to native Git or changing security/configuration. Never paste a token or credential-bearing remote URL into the conversation.

After both pulls succeed, follow the current build/test commands in NEXT_TEST.md. The complete environment inventory is already recorded; do not repeat it for ordinary delivery. The current verified MSYS2 location is D:\Test\wesnoth-setup\msys64 as confirmed by the 2026-10-13 runtime check.

Verification: the pasted PowerShell block and its generated Bash commands passed syntax checks on the VPS, and the user has now completed both fast-forward pulls on Windows. The following inventory finished 10/10 sections with exit 0; its BLOCKED/UNKNOWN entries still require interpretation. No new service configuration, global Git setting or installation was required by the successful commands. If a future MSYS2 update fails, assess that exact error and current locking-process evidence rather than reusing old PIDs or blindly changing services. That explanation did not need another pull; the current source/build delivery does require the new pulls in NEXT_TEST.md.

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


## Preparing newly required offline sources

For the paragraph-layout stage, the original source cache lacks FriBidi. The explicit connected helper Prepare-WindowsAndroidLayoutSources.ps1 -Download prepares its separate pinned release archive. Run the default helper after disconnecting to verify the cache offline. NEXT_TEST.md contains the current saved-log commands. Keep the existing 23-archive manifest and completed native receipts unchanged; later build commands must consume verified local sources with downloads disabled. A successful source-preparation marker is not evidence of a library build, Android runtime or gameplay.


## Validate a changed MSYS2 copy before resuming updates

FriBidi preparation and default cache verification passed. The later failure occurs before Git: the old Bash path is unavailable. The user reports the new MSYS2 root D:\Test\wesnoth-setup\msys64, but the corresponding uploaded tree has empty EXEs/DLLs. Current NEXT_TEST.md therefore starts with standalone PowerShell file-size checks at both Windows locations and saves a log. It needs no pull, MSYS process, network or package installation. Verify the actual copy before adopting the new root; preserve intact installations and completed builds. Existing helpers accept -MsysRoot, so avoid changing old receipt inputs to select a new location. The historical MSYS2 pull block above resumes only after the selected Bash/Git/runtime are usable.


## Runtime check after the Windows location report

The returned Windows report confirms nonempty tools at D:\Test\wesnoth-setup\msys64 and missing sampled tools at the old root. This differs from the uploaded empty VPS copy. NEXT_TEST.md now runs offline version/runtime checks and the existing MSYS/NDK checker with explicit -MsysRoot, saving one report. No pull is needed for this handoff. Use the new Bash path for subsequent Git updates after it runs successfully; preserve repository-local Git settings and successful builds. Never treat nonzero file size as a confirmed version or require a reinstall based on the different uploaded copy.


## Current delivery after the MSYS2 runtime passed (2026-10-13)

The historical location/runtime diagnostics above are complete. Use the guarded MSYS2 pull block in NEXT_TEST.md with D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe. The new TextLayout builder defaults to this verified root; old build helpers keep their receipt-bound inputs and accept -MsysRoot overrides. No reinstall or package upgrade is requested.

After pulling, disconnect and build only the new FriBidi/Pango prefix, then run its native probe on the selected LDPlayer. The saved-log block stops after a build failure and prints the client diagnostics/text-layout-*.txt path in either case. Preserve prior stages, source caches, game data, stashes and backups. Review each returned result before advancing to full client integration; the completed host checks do not establish Android layout success.


## Current source handoff after Android layout passed

The new Windows/LDPlayer result completes TextLayout. Keep all earlier outputs and receipt-bound helpers unchanged. NEXT_TEST.md now combines ordinary MSYS2 pulls with explicit connected ICU78.3 source preparation, then a separate default-mode verification after disconnecting. Both source-helper runs save logs and stop on failure; Git pulls retain their already verified direct invocation and stop before preparation on an error. Return those reports before requesting a Windows ICU library build. This does not repeat source inventory, the runtime relocation check or successful layout tests. All actual offline builds/gameplay must remain independent of internet access.


## Remaining ICU cache verification after the successful download

Actual Windows pulls and ICU78.3 download/hash verification passed. The current NEXT_TEST.md now requests only disconnecting and invoking the already present source helper in its default mode, with output saved under client diagnostics. No new pull or repeated -Download step is required to read a documentation-only checkpoint update. Preserve the successful source cache and native stages; no actual ICU library build or Android ICU runtime is implied by a source-helper success marker.


Latest Network checkpoint (2026-10-13): The returned network-state-20261013-092657-266-0a25997b14e74caa908736082192203c.json confirms that .ninja_log is missing and .ninja_log.restat contains exactly all 942 crypto objects, 90 SSL objects and both archives. Saved generation and the 144-file OpenSSL prefix pass. NEXT_TEST.md now verifies that report against current Windows files, preserves a metadata backup, restores the exact reviewed log, then resumes only the Network build and LDPlayer probe. Each configure protects both Ninja logs; completed source generation, objects and earlier stages stay in place. Actual curl build completion, Android Network execution, full game/APK/assets/OBB, playable turns and MongoDB remain pending. The Network builder now uses report-checked recovery and protected explicit configure operations for both .ninja_log and .ninja_deps. It disables automatic CMake regeneration only for this stage; use the normal helper for later builds. Preserve the surviving .restat and metadata transaction backups. Read the final BASELINE.md section for exact evidence and validation.


## Network complete; actual-engine handoff

The 2026-10-13 returned `network-recovery-20261013-115646-392-0df8d5ce80634e0dbd7dc9c60169af15.txt` completes Windows Network compilation and LDPlayer crypto/HTTPS execution. Its old metadata-state JSON is historical; do not reuse it for a new recovery after the completed build. Retain original metadata backups and all completed stages. Current NEXT_TEST.md moves to the actual engine shared library and version entry point, with a saved `diagnostics/engine-*.txt` log. Only the new owned engine stage is built. Android gameplay evidence still requires the later APK/activity/asset integration and a real playable turn.


Current game runtime checkpoint: actual Windows APK build, signing, installation and complete Android OBB import pass. The main menu is now user-confirmed; a completed turn is not. org.wesnoth.offline/versionCode1192600 uses the exact copied gamedata-1.19.26 through main.1192600.org.wesnoth.offline.obb. Preserve the installed app, verified data, source/cache/native/APK stages and receipts. NEXT_TEST.md is now a manual offline first-turn test, using Campaigns -> Heir to the Throne, Classic and its optional Battle Training. This data version has no separate Tutorial button. Documentation-only updates do not require pulling or rebuilding before this test.


## First-step acceptance and communication

The first step is complete when the existing Windows server and actual Android game run with the supplied data, a local turn and an offline LAN turn both work, and the fix/commit/push/pull/run/report cycle is verified. State which visible milestone each technical task advances. Current result now includes the user-confirmed Windows-server/LDPlayer full turn against AI with internet/WAN disconnected and local Ethernet active. The first emulator-based offline playable baseline is complete. Preserve gamedata-1.19.26, MSYS2 D:\Test\wesnoth-setup\msys64 and all completed stages. The user requests one test step per response. Establish physical-phone availability and then inspect its API/ABI before selecting a phone build. Separate-phone and two-human tests, MongoDB and custom features remain subsequent work. User-reported gameplay/offline status and actual startup/address logs are distinct evidence; no new gameplay event log has been inspected. Documentation-only records need no immediate Windows pull or rebuild.
