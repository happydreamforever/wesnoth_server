# Windows server running; connect LDPlayer for the Android build

Windows build and all guest protocol checks passed. The normal launcher also stayed running for at least30 minutes on TCP15000; zero users/games is normal before a client connects. Keep the working server open. Collector2026-10-11.3 completed10/10 with exit0, but ADB listed no devices, so Android API/ABI is still unknown.

This handoff updates project records only. Use the installed tools below; no new pull, rebuild, installation or full inventory rerun is needed. Keep the server-local core.filemode=false setting and saved stash. Preserve all local client engine-script changes until their diffs are inspected.

## 1. Check LDPlayer local ADB access

In the running LDPlayer window, open Settings (gear) > Other settings > ADB debugging. If needed, select **Open local connection**, save settings and restart only LDPlayer when requested. Wait until Android's home screen appears. Root permission does not need to change. If Open local connection is already selected, keep it and continue.

The vendor documents [local ADB access](https://www.ldplayer.net/blog/introduction-to-version-4.0.37-and-3.102-features.html) and [settings/save/restart](https://www.ldplayer.net/support/how-to-solve-locked-screen.html). The latter article's root/unlock procedure is unrelated; only the ADB setting applies here. An empty device list by itself does not prove which setting is currently selected.

## 2. Query instances and ready devices

In a second normal Windows PowerShell window, paste the whole block. No internet connection is needed.

```powershell
& {
    $adb = 'C:\Users\Uni\AppData\Local\Android\Sdk\platform-tools\adb.exe'

    'LDPLAYER INSTANCES'
    & 'C:\LDPlayer\LDPlayer9\ldconsole.exe' list2
    "LDCONSOLE_EXIT: $LASTEXITCODE"

    'LOCAL ADB DEVICES'
    $lines = @(& $adb -H localhost -P 5037 devices -l)
    $listExit = $LASTEXITCODE
    $lines
    "ADB_DEVICES_EXIT: $listExit"
    if ($listExit -ne 0) { throw 'ADB device list failed. Send the output.' }

    $serials = @($lines | ForEach-Object {
        if ($_ -match '^([^\s]+)\s+device(?:\s|$)') { $Matches[1] }
    })
    if ($serials.Count -eq 0) {
        'No ready device. Send this complete output.'
        return
    }

    foreach ($serial in $serials) {
        foreach ($property in @(
            'sys.boot_completed', 'ro.product.model', 'ro.build.version.release',
            'ro.build.version.sdk', 'ro.product.cpu.abi', 'ro.product.cpu.abilist', 'ro.dalvik.vm.native.bridge'
        )) {
            "PROPERTY: $serial $property"
            & $adb -H localhost -P 5037 -s $serial shell getprop $property
            "EXIT: $LASTEXITCODE"
        }
    }
}
```

Expected: LDPlayer instance rows, at least one ADB row with state device, sys.boot_completed=1 and Android release/API/ABI properties. API and ABI values must come from the device, not assumptions. The script queries only ready serials returned by SDK ADB on localhost:5037; it does not guess an instance index or device port. A blank native-bridge property can be valid. If listing fails or there is no ready device, it stops property queries and preserves the diagnostic output.

Send the complete output including LDCONSOLE_EXIT, ADB_DEVICES_EXIT and every PROPERTY/EXIT line, even if the device list remains empty. This step does not need another server build, protocol test or full collector report. It will determine the Android build target and next dependency/cache preparation. The Windows game-data folder is missing at its expected path; asset delivery, OBB support and MongoDB remain pending.

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
