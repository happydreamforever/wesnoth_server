# Next Windows test: Alliance server identity

The delivery cycle is **implement -> VPS verification -> commit/push -> Windows pull -> offline run/test -> return results**. This increment prepares the server identity and public connection profile that custom account login will use. It does not require the unresolved MongoDB startup to succeed. Malware troubleshooting remains deferred at the user's request.

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

## 2. Prepare the identity and test it

This block reads the current IPv4 of the user's previously verified **Ethernet** adapter, so it does not silently reuse an old address. If there is no single preferred address, it stops before generating any identity. Send that output rather than guessing another adapter.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop
    $addresses = @(Get-NetIPAddress -InterfaceAlias 'Ethernet' -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource -and $_.IPAddress -notlike '169.254.*' })
    if ($addresses.Count -ne 1) {
        throw 'Expected one preferred Ethernet IPv4 address. Stop and send this output.'
    }
    $serverAddress = [string]$addresses[0].IPAddress
    Write-Host "Preparing identity for Ethernet address: $serverAddress"
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAllianceTransport.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -ServerAddress $serverAddress
    if ($LASTEXITCODE -ne 0) {
        throw 'Alliance identity test failed. Send the saved log and JSON report if present.'
    }
}
```

The helper uses existing native Windows Python **3.14.3** and MINGW64 OpenSSL **3.6.3**. It creates a restricted, separate `runtime\alliance-transport` directory. It never opens `.env`, starts MongoDB/wesnothd, changes Windows services/trust stores, or modifies the existing `runtime\alliance` database. Repeat runs verify and reuse the same identity. Changed/incomplete identity files or a changed address/port stop without replacing keys; return that error before choosing recovery or rotation.

## Expected result and report

Expected output includes:

```text
PASS created server identity; private key stays on this computer.
PASS TLS1.2 trusted numeric-IP identity and encrypted payload
PASS TLS1.3 trusted numeric-IP identity and encrypted payload
PASS wrong-ip rejected before application data
PASS untrusted rejected before application data
PASS plaintext rejected before application data
ALLIANCE TRANSPORT IDENTITY CHECK PASSED
ALLIANCE TRANSPORT FIXTURE COMPLETE
```

A later successful run says `reused` instead of `created`. The public profile is `runtime\alliance-transport\public-profile.json`; the private key stays in that restricted directory. The profile requires trusted delivery before a client may use it; accepting a profile from an arbitrary server is not authentication. Certificates last 365 days; expiry, changed identities and later address changes need deliberate renewal/provisioning, not silent replacement. Profile port 15001 is the planned account endpoint; this test does not start that endpoint.

Return the matching **`diagnostics\alliance-transport-*.txt` and `.json`** files, even when the check fails, and state whether WAN was disconnected. The JSON contains only public identity metadata, versions and results. Do not send the private identity directory or key.

All test sockets use `127.0.0.1` and a temporary OS-assigned port while verifying the configured Ethernet IP as the certificate identity. Success proves the Python TLS fixture on Windows, not LAN reachability, native-client downgrade refusal, account login, MongoDB persistence or Android gameplay. The installed game menu stays as it is. Next implementation is the strict native account connection mode, then the account bridge and leader/team UI; Windows database acceptance remains pending separately.
