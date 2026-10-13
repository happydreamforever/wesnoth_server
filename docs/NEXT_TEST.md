# Build and test Android paragraph layout

The new MSYS2 location passed the Windows runtime and NDK compile check. Use D:\Test\wesnoth-setup\msys64 for current commands. All earlier native stages and the FriBidi source cache are already prepared; preserve them.

Connect Windows temporarily to GitHub. In normal PowerShell, update both existing checkouts:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }
    'Both updates completed successfully.'
}
```

If Git reports local changes, preserve them and return the error. Keep existing filemode settings, stashes and backups.

Disconnect from the internet and keep LDPlayer open with Android booted and its local ADB enabled. Run this entire block in normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\text-layout-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Build-WindowsAndroidTextLayout.ps1' `
                -MsysRoot 'D:\Test\wesnoth-setup\msys64'
            if ($LASTEXITCODE -ne 0) { throw 'Layout build failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Test-AndroidTextLayout.ps1' `
                -Serial '127.0.0.1:5555'
            if ($LASTEXITCODE -ne 0) { throw 'Layout device test failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Expected build result: ANDROID TEXT LAYOUT BUILD COMPLETE and a new build/android-text-layout/receipt.json. The builder uses only cached sources and verified prior prefixes, builds four static libraries for x86_64/API23, and retains development headers/metadata/notices. FriBidi's seven table generators use the host compiler; the libraries and probe use the selected Android NDK. No dependency upgrade or source download is performed.

Expected device output includes:

```text
PASS FriBidi mixed-direction ordering
PASS Pango private fonts and Arabic shaping
PASS Pango paragraph wrapping
PASS PangoCairo layout rendering
PASS wesnoth-android-text-layout
ANDROID TEXT LAYOUT TEST PASSED
```

The test verifies all receipts and the two fonts/license from D:\Test\wesnoth-setup\gamedata-1.19.26 before device access. It pushes the native probe, its verified C++ runtime and those three asset files to an owned temporary device directory. Drawing happens in memory and is checked through pixel values, so no new app window or APK installation is expected. The server does not need to run for this checkpoint. The Android ABI remains x86_64 and the selected LDPlayer is Android9/API28.

Return the saved client diagnostics/text-layout-*.txt file on success or failure. VPS evidence covers actual offline Android compilation, static archives/ELF metadata, host semantic tests and simulated PowerShell/ADB behavior. Windows compilation and Android execution of this new stage require your returned result. Full game APK/assets/OBB, single-player/LAN gameplay and MongoDB integration remain later work.
