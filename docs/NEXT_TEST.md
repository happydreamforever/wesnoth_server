# Retry the Alliance identity test with the existing identity

The returned Windows console output confirms that identity preparation succeeded for **100.99.99.14**, using Python3.14.3 and OpenSSL3.6.3. The later fixture failed with `ConnectionResetError`; the original output did not identify which case. The JSON/text files were saved on Windows but have not been supplied. Do not delete or regenerate `runtime\alliance-transport`.

This update corrects the fixture's handling of peer closure during deliberately rejected connections, adds orderly TLS shutdown for successful cases, and prints/saves each case as it runs. Negative cases still require the expected client-side TLS rejection; a client reset or positive-case reset still fails. This is a tested correction to the fixture, not a proven diagnosis of the exact Windows case. No database/game rebuild, identity rotation, malware investigation or tool upgrade is requested.

## 1. Pull the tested update

Temporarily connect Windows to GitHub. Run in ordinary Windows PowerShell:

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

Keep local Ethernet connected and disconnect internet/WAN again for the test. Preserve the existing installation, game, data and runtime. No dependency download or native/Android rebuild is needed for this increment.

## 2. Retest the preserved identity

Keep local Ethernet connected and disconnect internet/WAN again. The address below is the identity address just confirmed by the user's successful preparation; the probe itself only connects to loopback.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAllianceTransport.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -ServerAddress '100.99.99.14'
    if ($LASTEXITCODE -ne 0) {
        throw 'Alliance identity retest failed. Send the new saved log and JSON report.'
    }
}
```

Expected identity message is **reused**. The unchanged preparer validates ownership, file hashes, the key/certificate pair and profile before testing. If existing files are incomplete/changed, stop and return that error; do not delete or rename the identity to force a fresh one. The wrapper still uses pinned native Windows Python3.14.3 and MINGW64 OpenSSL3.6.3. The existing MongoDB runtime and game stages remain untouched.

## Expected result and report

Expected output includes:

```text
PASS reused server identity; private key stays on this computer.
PASS TLS1.2 trusted numeric-IP identity and encrypted payload
PASS TLS1.3 trusted numeric-IP identity and encrypted payload
PASS wrong-ip rejected before application data
PASS untrusted rejected before application data
PASS plaintext rejected before application data
ALLIANCE TRANSPORT IDENTITY CHECK PASSED
ALLIANCE TRANSPORT FIXTURE COMPLETE
```

A `RUN` line now precedes each case, and each completed `PASS` prints immediately. On failure, JSON retains completed `checks` and `case_results` with the failed case, client/peer stage and safe error codes. A peer reset is allowed only for the explicitly rejected handshake before application data (or its plaintext reply); the client must still independently reject the connection. The public profile is `runtime\alliance-transport\public-profile.json`; the private key stays in that restricted directory. The profile requires trusted delivery before a client may use it; accepting a profile from an arbitrary server is not authentication. Certificates last 365 days; expiry, changed identities and later address changes need deliberate renewal/provisioning, not silent replacement. Profile port 15001 is the planned account endpoint; this test does not start that endpoint.

Return the matching **`diagnostics\alliance-transport-*.txt` and `.json`** files, even when the check fails, and state whether WAN was disconnected. The JSON contains only public identity metadata, versions and results. Do not send the private identity directory or key.

All test sockets use `127.0.0.1` and a temporary OS-assigned port while verifying the configured Ethernet IP as the certificate identity. Success proves the Python TLS fixture on Windows, not LAN reachability, native-client downgrade refusal, account login, MongoDB persistence or Android gameplay. The installed game menu stays as it is. Next implementation is the strict native account connection mode, then the account bridge and leader/team UI; Windows database acceptance remains pending separately.
