# First native server checkpoint

This delivery restores Wesnoth 1.19.26 source into new `engine/` directories. The server builds a native guest multiplayer server; the client snapshot still needs its Windows Android build port and offline dependencies. Existing empty custom files are preserved. No Android APK, OBB loading, MongoDB persistence or playable turn is claimed by this checkpoint.

Use normal Windows PowerShell. No new installation or administrator shell is required. Open LDPlayer and wait until Android is ready before collecting the environment report.

## 1. Correct the Windows server Git setting and pull both repositories

The latest diagnostic confirms the cause: `core.filemode=true`, helper index mode `100644`, working-tree mode `100755`, zero added/deleted lines, LF in both copies, and no staged helper change. The comparison with `core.filemode=false` is clean. Stash `f0c22d3` also records only a mode change for this helper; its content hash matches HEAD. Do not repeat the diagnostic or create/apply another stash.

Temporarily connect to GitHub and run this block in normal Windows PowerShell. It saves `core.filemode=false` only in the existing Windows server repository, verifies the effective value and the helper comparison, then updates both repositories using MSYS2 Git.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    $serverGit = 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server '

    & $bash --noprofile --norc -c ($serverGit + 'config --local core.filemode false')
    if ($LASTEXITCODE -ne 0) { throw 'Could not save the server Git setting. Send the output.' }

    $mode = & $bash --noprofile --norc -c ($serverGit + 'config --get core.filemode')
    if ($LASTEXITCODE -ne 0 -or $mode -ne 'false') { throw 'Server core.filemode is not false. Stop here.' }
    Write-Host "Server core.filemode=$mode"

    & $bash --noprofile --norc -c ($serverGit + 'diff --no-ext-diff --no-textconv --quiet HEAD -- tools/build-windows-server.sh')
    if ($LASTEXITCODE -ne 0) { throw 'The helper still differs. Stop and send all output.' }

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Cannot read the $name commit." }
    }
    'Both updates completed successfully. Keep the existing stash saved.'
}
```

Expected: `Server core.filemode=false`, both fast-forward pulls (or already up-to-date), both commit IDs, and `Both updates completed successfully`. Keep the stash saved. If a step fails, stop and send its output; do not reset/restore/clean or force the update.

[Git's core.fileMode setting](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefileMode) controls whether working-tree executable bits count as changes. This repository-local setting persists for future server pulls. It does not alter the helper's contents, tracked mode, Windows access permissions, global Git configuration or the client/VPS Git configuration. Real content changes remain protected by Git. The server wrapper explicitly invokes the helper through Bash, so it does not require Git to track local execute-bit changes. Keep the existing README edits and other local work; no new stash or source rewrite is needed for the reported mode-only difference. The corrected helper and this setting have not yet been validated by a successful Windows build.

## 2. Build and test the server offline

The first Windows attempt failed with `dirname: command not found` and `Source: /`. Pull the corrected helper before retrying. It initializes its own MSYS2 PATH and validates the source location. Expected: `Source: /d/Test/wesnoth-setup/wesnoth_server` and `Build: /d/Test/wesnoth-setup/wesnoth_server/build/windows-mingw64`. No tool upgrade or global PATH edit is needed.

Disconnect the internet after the pulls. In PowerShell:

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

Expected executable: `build\windows-mingw64\bin\wesnothd.exe`, with version 1.19.26. The test starts and stops a temporary server, checks malformed-WML and version rejection, two guest logins, lobby listing, message relay and lobby refresh. It should end with `PASS protocol smoke test`. The log intentionally includes a rejected malformed message from the negative test. It does not test a game turn. Logs are `diagnostics\server-build-*.txt` and `diagnostics\server-protocol-*.txt`.

Build selection matches the confirmed Windows inventory: MINGW64 GCC 16.2.0 and Boost 1.91.0, Windows CMake 4.3.0, native UCRT64 Ninja 1.13.2. Ninja is used only as a build tool; compiler, headers, libraries and runtime DLLs all come from MINGW64. The wrapper also reports OpenSSL, ICU, zlib and bzip2 package versions. It does not invoke package installs, downloads, SCons, MongoDB or the empty original `src/` files. The test uses the confirmed Windows Python 3.14 installation and its standard library. Optional helper parameters support alternate existing tool locations.

## 3. Run the server

After build and protocol test pass, run this in a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Expected: version 1.19.26, configuration loaded and the process stays running on TCP port 15000. Keep that window open; Ctrl+C stops it. Logs are `diagnostics\server-run-*.txt`. Runtime state goes under `build\windows-mingw64\run`. The upstream server listens on available IPv4/IPv6 interfaces and allows guest clients with version 1.19.26. This helper supplies the installed MINGW64 DLL directory through its process PATH; the EXE is not a self-contained portable distribution. LAN routing/firewall and Android connection tests come after the APK is ready.

## 4. Identify LDPlayer for the Android build

With LDPlayer booted, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Collect-WindowsEnvironment.ps1' `
  -WorkspaceRoot 'D:\Test\wesnoth-setup' `
  -MsysRoot 'D:\Test\msys64'
"COLLECTOR_EXIT: $LASTEXITCODE"
```

Expected: collector `2026-10-11.3`, `Collection COMPLETE: 10/10 sections finished`, exit 0, plus Android API/ABI lines if ADB can see a ready LDPlayer device. The ADB probe now allows its local daemon to start. Send the report even if no device appears. Legacy empty artifacts and missing MongoDB may still be reported; inventory completion does not mean all components are ready.

Return both commit IDs, the server build/protocol/run logs, and the newest `windows-environment-*.txt` from `D:\Test\wesnoth-setup\wesnoth_server\diagnostics`. Stop a failed build/test sequence and send its complete log. Do not send `.env` or credentials. The next client task is to select the observed Android ABI, pin the Android toolchain/dependencies, build a real APK and load local game data.

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
