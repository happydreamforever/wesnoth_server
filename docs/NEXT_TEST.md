# Connect the Android game to the Windows server

The user reports that the requested local turn test is okay. Local gameplay is recorded as a user-reported pass; no new gameplay log was supplied. The next checkpoint is the installed Android game joining the existing Windows server and reaching turn 2 in a multiplayer game against the AI. No server rebuild, APK rebuild, reinstall or game-data copy is needed.

Use normal Windows PowerShell. Temporarily connect to GitHub for this update:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }
}
```

This delivers the new read-only server address helper and updated project records. Keep the installed org.wesnoth.offline app, its imported OBB data, all native/build receipts, existing stashes/backups and unrelated README edits.

After updating, disconnect the internet/WAN connection while keeping Windows connected to the local Wi-Fi router or Ethernet network. Turning off Wi-Fi or unplugging Ethernet would remove the LAN connection this test needs. If no local network is available, return the address helper's report before choosing another connection method. Start LDPlayer and keep the game at its main menu.

## Start the existing server

If the server is already running, keep its window open and proceed to the address report. Otherwise run this in the first PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1' `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expected: Wesnoth server 1.19.26 starts on TCP port 15000 and prints its server-run log path. Leave this window open. The explicit MSYS2 path uses the verified current installation; the launcher's historical default remains unchanged.

If Windows asks about firewall access, allow wesnothd on your trusted Private network. Do not disable the firewall. If the current network is Public or the client times out, keep its settings and return the reports for a specific connection fix.

## Read the Windows server address

In a second PowerShell window run:

```powershell
& {
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Show-WindowsLanAddress.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Server address check failed. Send the saved report and server log.' }
}
```

Expected: the report lists a wesnothd listener and one or more **Server** addresses, for example `192.168.1.25:15000`, followed by `LAN ADDRESS REPORT COMPLETE`. Use the actual printed address. If there are multiple rows, start with the adapter connected to your local router. Do not enter the example address, the ADB address or Android's 127.0.0.1.

The helper reads physical adapter IPv4 addresses, network profiles and local TCP listeners. It saves server diagnostics/lan-address-*.txt and changes no network/firewall settings. A report pass establishes local metadata only; the Android connection below is the real test. See Microsoft's [Get-NetAdapter](https://learn.microsoft.com/en-us/powershell/module/netadapter/get-netadapter), [Get-NetIPAddress](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-netipaddress) and [Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection) references.

## Join and play in LDPlayer

1. In the game choose **Multiplayer**. Set **Login** to `UniLAN`, select **Connect to Server**, then **OK**.
2. Enter the printed **Server** address under **Address**, then **Connect**.
3. Confirm the lobby shows `Welcome to the offline Wesnoth LAN server.` and your player name.
4. Choose **Create Game**, select **Scenarios**, then **2p — The Freelands** and era **Default**. Name it `Offline-LAN-Test`, leave the password empty, then **Create Game**.
5. In **Game Lobby**, leave side 1 assigned to `UniLAN`. Change side 2's controller to **Computer Player**. Keep the opposing North/South teams and random factions.
6. Press **I'm Ready**. Move your leader to a highlighted adjacent hex, then **End Turn**. Confirm the AI acts and your **turn 2** begins. Leave the game and server running.

No second human is needed for this check. If I'm Ready stays disabled, check that side 2 is Computer Player and no unoccupied Network Player side remains. These labels and the scenario were checked against the supplied 1.19.26 source/data.

Return whether the lobby appeared, the game started, turn 2 began and internet/WAN was disconnected while the local connection remained active. Also return the saved server diagnostics/lan-address-*.txt and server-run-*.txt files. On failure include the exact visible error and last successful step; do not reinstall or rebuild first.

Expected server events include `UniLAN has logged on`, `created game:` and `started game:`. The normal info log does not record every turn, so your visible turn-2 observation is still needed. Periodic game/user counts alone do not prove a playable turn.

This validates the actual Android client/server session using the Windows LAN address and one human plus AI. LDPlayer on the same Windows computer does not establish separate-phone connectivity or synchronization between two human devices. Physical-phone support, those additional tests, MongoDB persistence and custom game features remain subsequent work.
