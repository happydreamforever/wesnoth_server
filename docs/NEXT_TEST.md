# Next Windows test: Alliance transport inside LDPlayer

The user-observed database/admin checkpoint passed: the saved area name and audit identifier survived the offline restart, and signing out required login again. No database or browser acceptance test needs repeating.

Next we verify the native transport needed by future Alliance player accounts on the actual Android runtime. This is a small standalone console check in LDPlayer, using the existing Boost 1.88, OpenSSL 3.4.1 and NDK shared C++ runtime. It creates temporary certificates and local peers in memory, binds only emulator loopback, and checks the production Alliance transport component. It does not contact MongoDB, the admin website or the Windows game server. It does not install an APK, import the OBB or add account/team screens yet.

## 1. Pull while temporarily connected

Use the existing MSYS2 Git route. Healthy database/admin windows may remain running; this delivery changes no backend code or private runtime.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
}
```

After both pulls succeed, disconnect internet/WAN while keeping local Ethernet connected. Keep the existing LDPlayer instance open and fully booted. Use the verified MSYS2 root `D:\Test\wesnoth-setup\msys64`, native Python 3.14.3 and SDK/NDK already installed. No downloads, upgrades or earlier dependency rebuilds are required.

## 2. Build and test the small Android check

Run in normal Windows PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Build-WindowsAndroidAlliance.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android Alliance build failed. Send the saved build log.' }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Test-AndroidAlliance.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android Alliance test failed. Send the saved test log.' }
}
```

The builder verifies completed prerequisites, then compiles only the transport and its new standalone check into owned `build\android-alliance`. A completed matching stage is verified and reused. Changed/incomplete metadata stops with existing files preserved. Never delete earlier prefixes, caches or receipts to make this stage pass.

Expected build result: **ANDROID ALLIANCE BUILD PASS** followed by **ANDROID ALLIANCE BUILD COMPLETE**. The first build compiles two C++ files and links a small static library and executable. The Windows build has not been accepted until you return its actual output.

The device helper selects `127.0.0.1:5555`, requires the confirmed LDPlayer Android API28/primary x86_64, and verifies the artifact receipt before any transfer. Only the new executable and C++ runtime are copied into a unique `/data/local/tmp/wesnoth-alliance-check/<GUID>` directory; local and remote SHA256 must match before execution.

Expected device result: the version header shows `abi=x86_64 min_api=23 boost=1_88 openssl=0x30400010`, each case prints PASS, then **ALLIANCE ANDROID TRANSPORT CHECK PASSED** and **ANDROID ALLIANCE TEST PASSED**. Cases include TLS1.2/TLS1.3 message exchange, server push, invalid identity/pin/expiry, untrusted/plaintext/downgrade rejection, bounded malformed frames, stalled peers and cancellation. A rejected test connection counts as PASS only when the expected rejection is verified.

This test has no new game screen. Results appear in PowerShell. It establishes Android transport behavior inside the emulator; actual LAN account login, game UI and team battle remain subsequent milestones.

## 3. Return the saved output

Both helpers save logs automatically under the client checkout's diagnostics directory:

- `diagnostics\android-alliance-build-*.txt`
- `diagnostics\android-alliance-device-*.txt`

Send both new logs and say whether WAN stayed disconnected during the build and test. If either command fails, the block stops; send the saved output without changing versions, deleting stages or rerunning initialization. Keep the emulator test directory for diagnosis. Preserve the profile database, administrator, areas, permanent operation.guard, old logs/backups and completed game/OBB/native stages. No private profile, `.env`, keys or passwords are needed.
