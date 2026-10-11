# Windows server passed; prepare the Android client checkpoint

The user has now built the native 1.19.26 server on Windows and passed all guest protocol checks. Keep server-build-20261011-143549-682.txt and server-protocol-20261011-143830-505.txt. The latest handoff updates project records only: the commands below use helpers already installed, so no immediate pull, rebuild or repeated protocol test is required.

Use normal Windows PowerShell. These next checks need no internet connection or new installation. Guest protocol success does not establish an Android client, assets/OBB, MongoDB, LAN connectivity or a playable turn. Preserve the existing build directory, server-local core.filemode=false setting and stash f0c22d3.

## 1. Start the normal server launcher

The build and protocol test have passed. Run this in a normal PowerShell window; the test server has already stopped:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Expected: version 1.19.26, configuration loaded and the process stays running on TCP port 15000. Keep that window open; Ctrl+C stops it. Logs are `diagnostics\server-run-*.txt`. Runtime state goes under `build\windows-mingw64\run`. The upstream server listens on available IPv4/IPv6 interfaces and allows guest clients with version 1.19.26. This helper supplies the installed MINGW64 DLL directory through its process PATH; the EXE is not a self-contained portable distribution. LAN routing/firewall and Android connection tests come after the APK is ready.

## 2. Identify LDPlayer for the Android build

Open LDPlayer and wait until the Android home screen appears. Keep the server window open. In a second normal PowerShell window, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
"COLLECTOR_EXIT: $LASTEXITCODE"
```

Expected: collector `2026-10-11.3`, `Collection COMPLETE: 10/10 sections finished`, exit 0, plus Android API/ABI lines if ADB can see a ready LDPlayer device. The ADB probe now allows its local daemon to start. Send the report even if no device appears. Legacy empty artifacts and missing MongoDB may still be reported; inventory completion does not mean all components are ready.

Return the server startup output (or `server-run-*.txt`) and the newest `windows-environment-*.txt` from `D:\Test\wesnoth-setup\wesnoth_server\diagnostics`. The collector records current Git HEADs. Keep the successful build/protocol logs; no need to repeat those tests for this documentation update. Let collection finish without Ctrl+C. If no Android device appears, send that report too. Do not send `.env` or credentials. These results determine the next Android toolchain/ABI and offline dependency work.

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
