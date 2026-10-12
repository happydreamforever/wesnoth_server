# Windows server verified; check ADB after the LDPlayer restart

The user found the host ADB setting, saved and restarted LDPlayer after the Open local connection instructions. That UI step is complete; do not ask them to find the setting again. The earlier missing-device errors occurred before this change. The next step verifies the connection and reads actual Android API/ABI; no successful post-restart ADB output has been returned yet.

Windows server build, guest protocol and normal launcher remain verified. No server rebuild, Git pull, new installation or full inventory is needed for this inline diagnostic. Preserve all local changes and the server Git setting/stash.

## 1. Wait for the restarted instance's Android home screen

Keep LDPlayer open and run the block below in a normal Windows PowerShell window. It uses the already-installed SDK ADB. Local connection was requested in the prior instructions and the user reports completing the save/restart; that does not independently prove a working ADB transport. No further settings, root or emulator restart is requested now.

## 2. Test the default local endpoint and read actual ready-device properties

The observed emulator-5554 name makes 127.0.0.1:5555 a documented default candidate: [Android's port-pair explanation](https://developer.android.com/tools/adb#howadbworks) distinguishes console5554 from ADB5555, and section X of [LDPlayer's ADB guide](https://www.ldplayer.net/support/ldplayer-ldconsole-command-line-developer-usage-guide.html) describes the matching instance0 default. It is a connection attempt, not proof that this installation currently exposes that endpoint. A missing/failed connection does not prove a firewall or settings cause.

Paste this in a normal PowerShell window. The listener check reads only ports5037/5554/5555, is diagnostic rather than a prerequisite, and does not prove process ownership. All ADB operations use the confirmed SDK executable and local daemon. No ldconsole/bundled ADB calls are mixed into this block. ADB may start or replace its own incompatible host daemon normally.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $adb = 'C:\Users\Uni\AppData\Local\Android\Sdk\platform-tools\adb.exe'
    $endpoint = '127.0.0.1:5555'

    'LOCAL ADB LISTENERS'
    try {
        Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -in @(5037, 5554, 5555) } |
            Format-Table LocalAddress,LocalPort,OwningProcess -AutoSize
    } catch { 'Listener check: ' + $_.Exception.Message }

    "CONNECTING: $endpoint"
    & $adb -H localhost -P 5037 connect $endpoint
    "CONNECT_EXIT: $LASTEXITCODE"

    $lines = @(& $adb -H localhost -P 5037 devices -l)
    $listExit = $LASTEXITCODE
    $lines
    "DEVICES_EXIT: $listExit"
    if ($listExit -ne 0) { throw 'Device listing failed. Send all output.' }

    $serials = @($lines | ForEach-Object {
        if ($_ -match '^(127\.0\.0\.1:5555|emulator-5554)\s+device(?:\s|$)') {
            $Matches[1]
        }
    })
    if ($serials.Count -eq 0) {
        'LDPlayer is not ready in ADB. Send all output.'
        return
    }
    $serial = $serials[0]
    if ($serials -contains $endpoint) { $serial = $endpoint }

    foreach ($property in @(
        'sys.boot_completed', 'ro.product.model', 'ro.build.version.release',
        'ro.build.version.sdk', 'ro.product.cpu.abi', 'ro.product.cpu.abilist',
        'ro.dalvik.vm.native.bridge'
    )) {
        "PROPERTY: $serial $property"
        & $adb -H localhost -P 5037 -s $serial shell getprop $property
        $propertyExit = $LASTEXITCODE
        "PROPERTY_EXIT: $propertyExit"
        if ($propertyExit -ne 0) { break }
    }
}
```

Expected: connected/already connected to127.0.0.1:5555, a ready device row, boot completion1, and Android model/release/API/ABI values. A blank native bridge can be valid. Return all output including listener rows (or no rows), CONNECT_EXIT, DEVICES_EXIT, PROPERTY/PROPERTY_EXIT and any daemon/error messages. Do not interpret CONNECT_EXIT0 alone as success: some ADB connection failures are printed with zero exit. Only a successful devices command and a ready row for the specific candidate serial or the observed emulator-5554 alias permit property queries; unrelated devices are ignored. The TCP serial is preferred if both aliases appear. A failed property query stops further properties.

This diagnostic block parses with the available Linux PowerShell7.4.6 verifier and uses Windows PowerShell5.1 syntax. Windows listener/connection execution remains pending. If it still finds no target after the reported settings change/restart, inspect the returned listener and connection evidence before requesting further changes or trying more ports. API/ABI selection, offline Android dependencies, local game data/OBB, LAN play and MongoDB remain pending.

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
