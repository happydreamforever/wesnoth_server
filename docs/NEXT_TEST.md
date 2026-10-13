# Prepare the missing paragraph-layout source

TextRender passed on Windows and LDPlayer. The next stage is Pango paragraph layout; it needs the missing FriBidi source. This delivery prepares that source only. The existing Pango 1.50.14 archive and completed native builds remain usable.

Temporarily connect Windows to the internet. In normal PowerShell, paste this block to update both existing checkouts with MSYS2 Git and prepare the pinned FriBidi 1.0.17 archive:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }

    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\layout-sources-prepare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    $setupExit = 2
    try {
        powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File '.\tools\Prepare-WindowsAndroidLayoutSources.ps1' -Download `
            2>&1 | Tee-Object -FilePath $log
        $setupExit = $LASTEXITCODE
    } finally { Write-Host "Saved log: $log" }
    if ($setupExit -ne 0) { throw 'Source preparation failed. Send the saved log file.' }
}
```

The helper downloads 1,203,284 bytes from the exact official release URL recorded in tools/native-text-layout/sources.json, checks SHA256, and caches the archive at D:\Test\wesnoth-setup\wesnoth_client\build\android-layout-sources\fribidi-1.0.17.tar.xz. An already valid archive is reused. If an existing file differs from the pin, it is preserved and the helper stops; send the log without deleting or replacing the file.

After the preparation succeeds, disconnect internet access and run the offline verification:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\layout-sources-offline-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    $setupExit = 2
    try {
        powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File '.\tools\Prepare-WindowsAndroidLayoutSources.ps1' `
            2>&1 | Tee-Object -FilePath $log
        $setupExit = $LASTEXITCODE
    } finally { Write-Host "Saved log: $log" }
    if ($setupExit -ne 0) { throw 'Offline source verification failed. Send the saved log file.' }
}
```

Both commands should exit successfully and print:

```text
PASS: FriBidi 1.0.17; bytes=1203284; SHA256=6949dcde27d41cebad1fd741fcafc36d55a1020d2d872d4a6eb3914caabbada2
ANDROID LAYOUT SOURCES VERIFIED
```

The second command should also say Existing FriBidi source matches its pin; no download needed. Return both saved logs from the client diagnostics folder. Files can be attached or copied to workspace log files; no lengthy console copy is needed.

This step needs only the existing PowerShell/Git and temporary connectivity for preparation. No build, LDPlayer test or server launch is requested yet. After this cache check, the next implementation builds/tests FriBidi and Pango for mixed-direction paragraphs, wrapping and PangoCairo rendering with the verified fonts. The full game APK/assets/OBB, a playable local/LAN turn and MongoDB remain later milestones.
