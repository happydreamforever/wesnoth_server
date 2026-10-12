# ADB verified; prepare the Windows Android build inputs

The user verified LDPlayer after enabling local ADB: Android9/API28, boot_completed=1, model2203121C, primary ABI x86_64, ABI list x86_64,x86,arm64-v8a,armeabi-v7a,armeabi, native bridge libnb.so. SDK ADB connected successfully to127.0.0.1:5555; both that TCP serial and emulator-5554 appear ready. Use the explicit TCP serial for future device commands. Device discovery is complete; no more ADB/settings inventory is requested.

Windows server1.19.26 build, guest protocol and normal runtime are also verified. The next checkpoint prepares a separate client source tree and checks the exact Windows Android inputs. **It does not build an APK yet.** The native build scripts need a Windows port. See ANDROID_BUILD.md for selected versions and remaining work.

## 1. Pull the new preparation tools

Temporarily connect to GitHub. Run in a normal PowerShell window using the verified MSYS2 Git route:

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
}
```

Preserve README/engine edits, server-local core.filemode=false and the saved stash. This delivery adds tools/profile and updates docs; it does not replace engine/. Stop on a pull conflict without reset, clean or stash application.

## 2. Prepare source and check prerequisites offline

Disconnect from the internet if desired; these commands do not download anything. Run:

```powershell
& {
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    & 'C:\Users\Uni\AppData\Local\Programs\Python\Python314\python.exe' '.\tools\prepare_android_source.py'
    "SOURCE_PREPARATION_EXIT: $LASTEXITCODE"

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAndroidPrerequisites.ps1' `
        -MsysRoot 'D:\Test\msys64'
    "PREREQUISITE_CHECK_EXIT: $LASTEXITCODE"
}
```

The prerequisite check is useful even if source preparation is blocked. It reads the originals and reports differences without changing them. Send complete console output plus the new client diagnostics/android-prerequisites-*.txt file. Do not send .env or credentials.

Expected source result:1591 preserved files match SHA256, then PREPARED (or ALREADY PREPARED) for build/android-source. It deliberately states APK build remains blocked because native integration is unfinished. A content mismatch or unmanaged/edited destination stops staging without overwriting. Executable-bit-only changes do not prevent matching. An interrupted stage is preserved; use the returned output to choose a recovery, not deletion/reset.

Expected prerequisite result: a completed report with specific PASS/BLOCKED checks for source integrity, selected Java/SDK/NDK, MSYS build tools/SCons, actual Gradle/AndroidX cache files and the23 native archive hashes. Existing Windows evidence suggests NDK26.3.11579264 and SCons4.11.0 may be missing, so exit2/BLOCKED is an expected actionable result. Exit0 establishes these prerequisite checks only, not full offline dependency resolution or APK readiness. A Gradle cache file's presence is not a build test. No blanket tool upgrades or downloads are requested in this step; missing packages/cache will be prepared from the report.

No server rebuild or repeated protocol test is needed. Android app build/install/run commands will follow when the Windows native pipeline and offline dependency set are prepared. Existing server run instructions below remain valid.

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
