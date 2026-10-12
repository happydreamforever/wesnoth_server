# Prepare the missing Android tools and Java dependency cache

The Windows prerequisite report completed and saved normally. All 1,591 source hashes, all 23 native source archive hashes, Java/javac 21.0.9 and the 15 named MSYS host tools passed. MSYS Python is 3.12.13. The twelve BLOCKED entries represent missing NDK 26.3 inputs (eight entries), SCons, the selected Gradle 8.9 distribution, and two AndroidX artifact files. They are dependency results, not another logging failure.

The next step temporarily needs internet access to prepare these tools. Existing NDK 30beta and server tools remain installed. Native Android compilation is still being ported; **this setup does not build an APK**.

## 1. Pull the preparation helper

Run in normal PowerShell while temporarily connected:

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

Preserve README/source work, server-local core.filemode=false and stash f0c22d3. Stop on a pull conflict without reset, clean or stash application.

## 2. Prepare tools while connected, then check the results

Keep internet access available for SDK, Python package and Gradle/Maven downloads. NDK installation can take several minutes. If the Android SDK manager displays license terms, review them and answer its prompt yourself. The helper requests only NDK 26.3.11579264; it does not update all SDK/MSYS packages or auto-accept licenses. This uses the already-installed [SDK manager's specific-package installation](https://developer.android.com/tools/sdkmanager#install_packages).

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Prepare-WindowsAndroidTools.ps1' -Download
    if ($LASTEXITCODE -ne 0) {
        throw 'Android tools setup stopped. Send the complete console output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAndroidPrerequisites.ps1' `
        -MsysRoot 'D:\Test\msys64'
    "PREREQUISITE_CHECK_EXIT: $LASTEXITCODE"
}
```

The setup verifies and reuses the existing `build/android-source`; it does not replace it. It prepares the published SCons 4.11.0 wheel with a pinned SHA256 in `build/downloads`, installs its pure Python files privately under `build/tools/scons-4.11.0`, and checks integrity before use. No global pip or MSYS package installation is required. The prerequisite helper uses MSYS `/usr/bin/python3 -I` to run this exact private SCons package.

The staged upstream source has no gradlew.bat, so setup launches its preserved wrapper JAR through the selected Java executable. The wrapper downloads pinned Gradle 8.9 with its recorded distribution checksum. A dedicated Gradle task resolves actual debug compile/runtime JAR/AAR files and the AGP-matching Windows AAPT2 artifact. It repeats the same task with `--offline`; it cannot invoke native, compile or package tasks. Gradle's project cache is outside the preserved source stage, and selected Java/SDK environment variables apply only inside setup.

Expected output:

- NDK 26.3 installation succeeds, or SDK manager reports it is already installed.
- Private SCons preparation succeeds; the subsequent check reports `Project-private SCons 4.11.0 verified and runnable with MSYS2 Python`.
- Gradle reports `CACHE RESOLUTION PASSED: offline=false`, then `offline=true`, followed by `SETUP COMPLETE`.
- Prerequisite header is `2026-10-12.3`, its final line reports `Check complete=True; BLOCKED entries=0`, and `PREREQUISITE_CHECK_EXIT: 0`.

A successful offline resolution only proves the selected Java/plugin/AAPT2 files can resolve from that cache. Native dependencies, Android compilation and a complete offline APK build remain unverified. No server rebuild or ADB setup is needed. Send full console output and the prerequisite file named by `Report saved to:`. If setup fails, send that output without deleting caches or rerunning broad installers. If report saving fails, the prerequisite helper tries `%TEMP%\wesnoth-diagnostics`; exit 3 means no complete report was saved.

## Reuse the private SCons package offline

Windows setup uses native Python to extract the universal wheel and MSYS Python to run it. Once cached, `prepare_scons.py prepare` uses no network; `version` and `run -- <SCons arguments>` always verify the retained wheel and installed files first. Future native build helpers must use this runner with the selected interpreter, not assume a global scons command exists. Both the wheel and private tool directory live under ignored build/ and must be retained for offline use.

## Reference: restart the verified server if it has stopped

The server is already running in the latest report; no restart is needed for the prerequisite check. If you stop it later, start it again in a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Keep that window open; Ctrl+C stops the server. The printed transcript path is diagnostics/server-run-*.txt.

## Reference: update and rebuild after future implementation changes

These commands are retained for later code changes, not required for the current prerequisite-check step. Temporarily connect to GitHub and pull using the established MSYS2 route:

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
