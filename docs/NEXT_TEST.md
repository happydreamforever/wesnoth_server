# Windows source prepared; complete the Android prerequisite report

Windows source preparation passed with all 1,591 preserved file hashes matching, created `build/android-source`, and exited 0. The server build/protocol/runtime and LDPlayer connection are already verified. Use `127.0.0.1:5555` for future ADB commands; the emulator is Android 9/API 28 with primary ABI x86_64.

Prerequisite helper 2026-10-12.1 stopped because writing its report hit a file-sharing error. The JDK/MSYS2 section failures named the report file, not those tools. NDK 26.3.11579264 is genuinely missing; Gradle and native archive checks were not reached. Version 2026-10-12.2 keeps console results in memory and saves the complete report separately, with bounded retries and a temporary-directory fallback. The current step reruns this check. **It does not build an APK.** The Windows native build port is still pending; see ANDROID_BUILD.md.

## 1. Pull the logging fix and updated project records

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

Preserve README/engine edits, server-local core.filemode=false and the saved stash. This delivery changes the prerequisite helper and project records. Stop on a pull conflict without reset, clean or stash application.

## 2. Rerun only the prerequisite check

This command can run offline and does not install or download anything. Source preparation already passed and is unchanged, so keep the existing stage.

```powershell
& {
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAndroidPrerequisites.ps1' `
        -MsysRoot 'D:\Test\msys64'
    "PREREQUISITE_CHECK_EXIT: $LASTEXITCODE"
}
```

Expected: header version `2026-10-12.2`, followed by all checks including Gradle cache and native archive integrity, then `Check complete=True`. NDK-related BLOCKED entries and exit 2 are expected while that selected package is missing. Other missing inputs will be listed. Exit 0 means these prerequisite checks passed; it does not establish complete offline resolution, native compilation or an APK.

The helper prints `Report saved to:` only after a successful save. The normal destination is client `diagnostics/android-prerequisites-*.txt`. If that destination remains unavailable, it tries a unique report under `%TEMP%\wesnoth-diagnostics`; use the actual printed path. If both destinations fail, the full results remain on screen and exit 3 identifies a report-save failure independently of dependency results. Send the complete console output and the report at the printed path if saved. Do not send `.env` or credentials.

Let the check finish; no server rebuild, repeated ADB setup, Windows service change or tool installation is requested for this rerun. The complete report will guide targeted preparation of NDK/SCons/caches and the native Windows port. Android build/install/run commands follow when that pipeline is ready.

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
