# Build and run the first SDL graphics/input APK

The Windows native bootstrap build and actual LDPlayer execution passed. All five compression/C++ checks succeeded. The NDK CMake deprecation warnings were nonfatal. Dependency setup, the first native compiler/runtime test and local ADB connection are complete; keep their existing tools, caches and successful artifacts.

The next checkpoint creates a separate **Wesnoth SDL Check** Android app. It builds the same SDL 3.4.2 native library and matching Java code used by the restored game source, opens an OpenGL ES landscape screen, and exercises tap input. It does not load the game engine or game data yet. The expected visible result is a colored target with tap/frame counters and an animated bar.

## 1. Pull the APK build/test tools

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

## 2. Build offline, install and test in LDPlayer

Keep LDPlayer open at its Android home screen. Internet access is unnecessary for the build and device test. The helper selects the existing native CMake/Ninja/NDK, Windows Python and Android Studio Java, and uses Gradle --offline with SDK auto-downloads disabled.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsSdlCheck.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'SDL APK build failed. Send the complete console output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidSdlCheck.ps1' `
        -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) {
        throw 'SDL APK test failed. Send the complete console output.'
    }
}
```

The first build compiles SDL and Java and packages a debug APK. Let it finish; later unchanged builds reuse the outputs. Native CMake feature probes can report "not found" for unavailable optional features; the final result and process exit determine success. If an offline cache input is missing, send its exact error before installing packages or rerunning connected setup.

Expected build marker: `SDL CHECK APK BUILD COMPLETE`. The APK is at:

```text
D:\Test\wesnoth-setup\wesnoth_client\build\android-sdl-apk\app\build\outputs\apk\debug\app-debug.apk
```

The builder verifies the SDL source archive, exact matching Java files, Android x86_64/API23 libraries, APK native payload, package/SDK metadata and APK signature. The receipt is build/android-sdl-apk/receipt.json. The package is org.wesnoth.offlinecheck, version 1.0/code 1, with minimum API23 and target35. It is separate from the eventual game app. Original engine/, build/android-source and build/android-native-bootstrap remain preserved.

The device helper checks current source and artifact hashes before ADB, verifies the selected API/ABI, installs this APK, and launches a fresh test run. It reads only that app's process logs without clearing device logs. A READY marker must confirm a presented OpenGL ES frame; then an automated center tap must produce a presented INPUT response from the same run. The final expected marker is `ANDROID SDL CHECK AUTOMATED TEST PASSED`.

After the automated test finishes, leave the app open and click its colored target a few times. Confirm that the tap counter increases, the color changes and the animation continues. Send the full build/test console output and describe the visible result. If the display is blank or incorrect, include a screenshot of the app. These helpers print to the console; they do not create a new diagnostics transcript.

This validates SDL graphics/input, JNI library loading and a first APK build/install. The actual Wesnoth client, remaining dependency libraries, game data/OBB, audio, LAN gameplay and MongoDB still need implementation/testing. The working server does not need a rebuild or restart for this step.

## Reference: restart the verified server if it has stopped

The server is already running in the latest report; no restart is needed for the SDL APK test. If you stop it later, start it again in a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Keep that window open; Ctrl+C stops the server. The printed transcript path is diagnostics/server-run-*.txt.

## Reference: update and rebuild after future implementation changes

These commands are retained for later code changes, not required for the current SDL APK step. Temporarily connect to GitHub and pull using the established MSYS2 route:

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
