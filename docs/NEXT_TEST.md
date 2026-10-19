# Next Windows test: native Alliance account transport

The returned Windows result completes the Python identity fixture: the existing identity was reused and all five TLS cases passed. Keep `runtime\alliance-transport` and all completed game/OBB/native stages. Do not repeat that check or initialize MongoDB now. WAN status for that returned run was not supplied; this is actual Windows loopback evidence, not a new physically disconnected acceptance claim.

Next test compiles the new C++ Alliance connection component with the already installed Windows compiler and runs temporary loopback peers. This is the code intended for the later Alliance account screens; the installed APK and guest server still use their existing code. Native game integration, profile import UI, account login, MongoDB startup and team gameplay remain pending. No game rebuild, reinstall or service change is required.

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

## 2. Disconnect WAN, then build and check the small component

Keep local Ethernet connected. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAllianceNative.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Native Alliance check failed. Send the saved log and JSON report if present.'
    }
}
```

The helper uses the existing Python3.14.3, CMake4.3.0, Ninja1.13.2, MINGW64 GCC16.2.0, Boost1.91 and OpenSSL3.6.3 from the current MSYS root. It builds only two C++ source files into a new `build\alliance-native-<runid>` directory. It never downloads dependencies or touches the completed server/Android builds.

It reads only the existing public profile, checks it with native C++, and leaves the original certificate/private key/receipt unchanged. Socket tests use newly generated disposable loopback identities inside the new restricted fixture directory. All sockets bind/connect to `127.0.0.1` on temporary ports. No connection to100.99.99.14 or port15001 occurs. No production account credentials are entered or sent.

## Expected result and report

The build should finish four steps. Then24 checks pass: existing public identity, disconnected-send guards, wrong IP/pin, hostname/broadcast refusal, expired certificate, TLS1.2/TLS1.3 encrypted frames, server-push receive, untrusted peer, downgrade/unexpected/closed/reset/stalled negotiation, plaintext, stalled TLS, cancellation, oversized/empty/truncated frames and stalled receive. The result ends with:

```text
ALLIANCE NATIVE TRANSPORT CHECK PASSED
ALLIANCE NATIVE FIXTURE COMPLETE
```

Return the matching **`diagnostics\alliance-native-*.txt` and `.json`** reports, even on failure, plus whether WAN was disconnected. If compilation fails before JSON creation, send the text log. Do not send the disposable fixture directory or any private key. Keep any failed build directory for diagnosis; the helper uses a new one for a later explicit rerun.

The game menu does not change during this test. A pass establishes Windows C++ component behavior, not Android execution, LAN reachability or authenticated team gameplay. Next integration work will add trusted public-profile import and explicitly route Alliance account screens through this component, with the local backend bridge. Local MongoDB startup remains a separate unresolved acceptance item; its investigation is deferred at the user's request.
