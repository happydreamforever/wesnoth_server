# Next Windows test: run the completed Android transport check with WAN disconnected

The Windows build and all22 LDPlayer transport cases passed. You confirmed internet/WAN remained available during that run. The only remaining check for this stage is execution while WAN is disconnected. The build, libraries, installed game and OBB are already present. No pull, build, reinstall, dependency change or database restart is needed.

## Run the existing check once offline

Disconnect internet/WAN while keeping local Ethernet connected. Leave the existing LDPlayer instance fully booted. Healthy database/admin windows may remain open; this check does not use them.

In normal Windows PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidAlliance.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Offline Android Alliance test failed. Send the new saved device log.'
    }
}
```

Expected: the existing artifact receipt verifies, LDPlayer reports API28/x86_64, both transferred SHA256 values match, all22 cases pass, then **ALLIANCE ANDROID TRANSPORT CHECK PASSED** and **ANDROID ALLIANCE TEST PASSED**. Results appear in PowerShell; no new game screen is expected. The helper creates a fresh unique emulator test directory and leaves the prior successful files intact.

Send the new `wesnoth_client\diagnostics\android-alliance-device-*.txt` log and explicitly confirm that WAN stayed disconnected during this run. If it fails, send the saved log without changing versions, rebuilding libraries or deleting any stage. Do not repeat database initialization or the completed browser test.

This verifies the native transport inside emulator loopback under disconnected conditions. Actual Windows-LAN account traffic, public-profile import, native bridge, account screens and team gameplay remain subsequent implementation work. The earlier successful build happened with WAN available; this device-only check does not retroactively establish a physically disconnected Windows compilation.
