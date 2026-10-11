# Windows server running; query the confirmed LDPlayer instance

Windows build and all guest protocol checks passed. The normal launcher also stayed running for at least30 minutes on TCP15000; zero users/games is normal before a client connects. Keep the working server open. The latest focused probe confirms LDPlayer instance **0**, named LDPlayer, with Android started=1. SDK ADB lists no devices despite exit0, so Android API/ABI and the cause of the missing ADB connection remain unknown.

This handoff updates project records only. Use the installed tools below; no new pull, rebuild, installation or full inventory rerun is needed. Keep the server-local core.filemode=false setting and saved stash. Preserve all local client engine-script changes until their diffs are inspected.

## 1. Keep instance 0 running

Keep the LDPlayer window at Android's home screen. The intended setting remains Settings (gear) > Other settings > ADB debugging > **Open local connection**. If you already selected it, leave it unchanged. Root permission does not need to change. The returned output confirms Android started, but does not independently confirm this setting.

The vendor documents [local ADB access](https://www.ldplayer.net/blog/introduction-to-version-4.0.37-and-3.102-features.html) and [settings/save/restart](https://www.ldplayer.net/support/how-to-solve-locked-screen.html). The latter article's root/unlock procedure is unrelated; only the ADB setting applies here. An empty device list by itself does not prove which setting is currently selected.

## 2. Query instance 0 through LDPlayer's command interface

In a second normal Windows PowerShell window, paste the whole block. No internet connection is needed. The index comes from the actual returned list2 row. LDPlayer handles selection of this instance; no port is derived from an index formula.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $ld = 'C:\LDPlayer\LDPlayer9\ldconsole.exe'
    foreach ($command in @(
        'get-serialno'
        'shell getprop sys.boot_completed'
        'shell getprop ro.product.model'
        'shell getprop ro.build.version.release'
        'shell getprop ro.build.version.sdk'
        'shell getprop ro.product.cpu.abi'
        'shell getprop ro.product.cpu.abilist'
        'shell getprop ro.dalvik.vm.native.bridge'
    )) {
        "COMMAND: $command"
        & $ld adb --index 0 --command $command
        $queryExit = $LASTEXITCODE
        "LDCONSOLE_EXIT: $queryExit"
        if ($queryExit -ne 0) {
            'Command failed. Send all output above.'
            break
        }
    }
}
```

Expected: a serial from get-serialno, sys.boot_completed=1, and actual Android model/release/API/ABI properties. A blank native-bridge property can be valid. The script stops if ldconsole reports a nonzero exit; exit0 alone is not sufficient evidence if its output is empty or contains an ADB error. Return every COMMAND/LDCONSOLE_EXIT line and any daemon, connection or version-mismatch messages. A serial is not necessarily a TCP endpoint; do not automatically pass an emulator serial to adb connect.

This uses the vendor's [instance-targeted ADB command](https://www.ldplayer.net/support/introduction-to-ldplayer-command-line-interface.html) and ADB's [serial query](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/user/adb.1.md). It requests device information only, but LDPlayer may invoke its bundled ADB, which can start or replace an incompatible host ADB daemon. Do not alternate SDK/bundled clients during this probe. SDK ADB registration is not considered fixed merely because the LDPlayer command succeeds.

Send the complete output. This step does not need another server build, protocol test or full collector report. Android build preparation follows the actual API/ABI results; we will address SDK connectivity from the observed serial and output. The Windows game-data folder is missing at its expected path; asset delivery, OBB support and MongoDB remain pending. The exact block parses in the VPS PowerShell7.4.6 verifier and uses PowerShell5.1 syntax; Windows/LDPlayer execution is still pending.

## Reference: restart the verified server if it has stopped

The server is already running in the latest report; no restart is needed for the device probe. If you stop it later, start it again in a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Keep that window open; Ctrl+C stops the server. The printed transcript path is diagnostics/server-run-*.txt.

## Reference: update and rebuild after future implementation changes

These commands are retained for later code changes, not required for the current startup/inventory step. Temporarily connect to GitHub and pull using the established MSYS2 route:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Cannot read the $name commit." }
    }
    'Both updates completed successfully.'
}
```

Preserve local README edits and other work. Stop on a pull error without resetting, cleaning, force-pulling or applying the saved stash. After successful pulls for an implementation change, disconnect and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Build-WindowsServer.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Server build failed. Send the build log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Test-WindowsServer.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Protocol test failed. Send the test log.' }
    'Server build and protocol test completed successfully.'
}
```

Expected: BUILD COMPLETE for build/windows-mingw64/bin/wesnothd.exe version1.19.26, followed by PASS protocol smoke test. Logs go to diagnostics/server-build-*.txt and server-protocol-*.txt. The test starts/stops a temporary server and deliberately sends malformed WML as a rejection check; it does not play a game turn. The build uses the confirmed MINGW64 compiler/dependencies, native CMake/Ninja and Windows Python3.14 for testing. Do not delete the build directory between incremental fixes unless a concrete failure requires it.

## VPS verification

The Linux Release build and native protocol checks have passed. The Linux image in `tools/Dockerfile.verify` pins GCC 16.2, Boost 1.91.0, CMake 4.3.0 and Ninja 1.13.2. It is prepared online; builds/tests then run with Docker networking disabled. Linux system OpenSSL/ICU/compression libraries and OS remain separate from Windows. Matching these four major tools does not prove Windows ABI, linker or DLL compatibility. No Docker installation is needed on Windows.

From the server repository on the VPS:

```sh
docker build -t wesnoth-server-verify:1.19.26 -f tools/Dockerfile.verify tools
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work wesnoth-server-verify:1.19.26 \
  sh -c 'cmake -S . -B build/linux-verification -G Ninja && cmake --build build/linux-verification --parallel 2 && python3 tests/test_server_protocol.py --server build/linux-verification/bin/wesnothd --log-path diagnostics/server-protocol-linux.txt'
```

For changes to the Windows build helper, run `python3 tests/test_windows_build_bootstrap.py` on the VPS with the existing verification image. This executes the unchanged helper with restricted PATH and mocked native tools in a network-disabled container; it also verifies that missing/empty source files and configuration failures stop the build. It does not compile a Windows executable.

Do not translate a passing Linux result into a claimed Windows, Android, database or gameplay result. Record the user's returned evidence in `BASELINE.md` before selecting the following test.
