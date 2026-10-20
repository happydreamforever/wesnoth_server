# Next Windows test: retry the native Alliance fixture

Your native C++ build and first six checks passed. The next step failed while OpenSSL `ca` prepared the disposable expired certificate, before `RUN expired` or any socket cases. The console does not include OpenSSL stderr; the original cause is unknown. The unused `Boost_ROOT` warning did not prevent compilation.

The correction creates the expired leaf directly with `openssl x509`, preserving the same key, IP and server-purpose constraints in the disposable identity. It needs no CA database/index/serial rotation. The original server identity is unchanged. The installed game, MongoDB and all completed build/data stages remain as they are.

## 1. Pull while temporarily connected

In a normal Windows PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Stop and send the output." }
    }
}
```

## 2. Disconnect WAN, then retry using your compiled probe

Keep local Ethernet connected. This selects the exact successful build from your report:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAllianceNative.ps1' `
        -ProbePath '.\build\alliance-native-20261019-212254-918-022ffd1f78ce4b3eaae6f60c30abc11e\alliance-native-probe.exe'
    if ($LASTEXITCODE -ne 0) {
        throw 'Native Alliance retry failed. Send the new saved log and JSON report if present.'
    }
}
```

`-ProbePath` uses that executable without CMake, Ninja or compiler invocation. It verifies Python3.14.3/OpenSSL3.6.3 and the compiled native versions, sets the selected MINGW64 DLL path, and runs the fixture in a fresh uniquely named directory. If the selected executable is missing/empty it stops; it does not rebuild. Keep the old build, old fixture directory and old diagnostics.

The fixture reads the existing public profile and uses newly generated disposable loopback identities for its socket cases. The original private identity and MongoDB runtime are not accessed. All test sockets use127.0.0.1 and temporary ports; no production account credentials are sent. This checks the C++ transport component, not installed-game login or team gameplay.

## Expected result and report

First expect `Reusing existing native Alliance probe without rebuilding:`. There should be no build steps. All24 checks should pass, including `PASS expired`, `PASS TLS1.2` and `PASS TLS1.3`. The final lines include:

```text
ALLIANCE NATIVE TRANSPORT CHECK PASSED
ALLIANCE NATIVE FIXTURE COMPLETE
```

Return the **new matching `diagnostics\alliance-native-*.txt` and `.json`** reports, even on failure, and tell us whether WAN was disconnected. Do not send the fixture directory or private key files. The previous Windows console proves compilation/early validation only; native socket completion and Android account integration are still pending.
