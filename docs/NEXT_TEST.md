# Build and run the first native Android dependency test

Windows dependency preparation passed: NDK 26.3.11579264/clang 17.0.2, private SCons 4.11.0, Gradle 8.9/AGP 8.7.3 and selected Java/Windows AAPT2 caches. Online and offline resolution produced the same 24 artifact hashes. Prerequisite .3 completed with zero blockers and exit 0. The earlier connection reset did not recur; no additional online setup or inventory is needed now.

Next, compile the real bzip2 1.0.8 library and a small C++ test program for Android x86_64/API23, then run the program on the verified LDPlayer Android 9/API28 device. It tests bzip2/zlib compression, C++ runtime support and exceptions. This creates the first target library and verifies native compile/link/device execution before porting the remaining dependencies. **It is a command-line native test, not a game APK or playable client.** No game window is expected.

## 1. Pull the native bootstrap tools

Temporarily connect to GitHub and run in normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
    }
}
```

Preserve local work, server-local core.filemode=false and stash f0c22d3. Stop on a pull conflict without reset, clean or stash application.

## 2. Build offline and run in LDPlayer

Internet access is no longer needed for these commands. Keep LDPlayer running and wait for its Android home screen. The test uses its already verified local ADB endpoint; no settings change or server restart is needed.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidBootstrap.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android native build failed. Send the complete console output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidBootstrap.ps1' `
        -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android native runtime test failed. Send the complete console output.'
    }
}
```

The build uses existing Windows Python 3.14, native CMake 4.3.0, native Ninja 1.13.2 and NDK 26.3.11579264. It verifies the cached bzip2 source archive before using it and downloads nothing. It builds in a separate ignored `build/android-native-bootstrap` directory, preserving engine/ and build/android-source. The executable links the newly built bzip2 library, Android system zlib and the matching NDK C++ runtime. This checkpoint uses the native Windows CMake toolchain; it does not establish that the eventual SCons/MSYS2 game build is ported.

Expected files are `out/lib/libbz2.a`, `out/bin/wesnoth-native-check`, `out/bin/libc++_shared.so`, and a build receipt under `build/android-native-bootstrap`. The receipt records inputs and artifact hashes. The device helper verifies them before ADB, checks the selected device's boot/API/ABI, then pushes only the executable and C++ runtime into a uniquely named directory under `/data/local/tmp/wesnoth-native-bootstrap`. It does not install an APK, request root or change game/server data.

Expected runtime output includes identifying Android x86_64/API23 information, successful compression/C++ checks, and final `ANDROID NATIVE BOOTSTRAP TEST PASSED`. A nonzero device command or missing success marker is a failure. Send the complete build and test console output, including errors. The receipt is useful build evidence; these wrappers print to the console rather than creating a new diagnostics transcript.

After this passes on Windows and LDPlayer, continue with remaining native dependencies and the actual client build. Keep the prepared SDK, private SCons, Gradle caches and the 23 native source archives for offline work. Do not rerun the connected setup merely to build this checkpoint.

## Reference: restart the verified server if it has stopped

The server is already running in the latest report; no restart is needed for the native bootstrap test. If you stop it later, start it again in a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Keep that window open; Ctrl+C stops the server. The printed transcript path is diagnostics/server-run-*.txt.

## Reference: update and rebuild after future implementation changes

These commands are retained for later code changes, not required for the current native bootstrap step. Temporarily connect to GitHub and pull using the established MSYS2 route:

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
