# Run the completed font-rendering probe in LDPlayer

Your log.txt confirms the Windows Expat/Fontconfig/Cairo build succeeded, including the final probe and receipt. Cairo recovered on its third configure attempt. Keep the completed build/android-text-render directory and all earlier stages; no rebuild is needed.

The device helper stopped before verification or ADB because its default game-data path was evaluated before PSScriptRoot was available. This update resolves that default after script initialization. The existing data directory remains D:\Test\wesnoth-setup\gamedata-1.19.26.

## Pull the helper fix

Temporarily connect Windows to GitHub and paste this into normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
}
```

Keep repository-local Git settings and saved stashes. If a pull reports a conflict, preserve local files and return the error. Only the pulls need internet.

## Run only the device test and save its output

Return to offline use. Keep LDPlayer open with Android booted and paste this block into normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\text-render-device-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    $deviceExit = 2
    try {
        powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File '.\tools\Test-AndroidTextRender.ps1' -Serial '127.0.0.1:5555' `
            2>&1 | Tee-Object -FilePath $log
        $deviceExit = $LASTEXITCODE
    } finally {
        Write-Host "Saved log: $log"
    }
    if ($deviceExit -ne 0) { throw 'Device test failed. Send the saved log file.' }
}
```

The output remains visible and is saved in D:\Test\wesnoth-setup\wesnoth_client\diagnostics\text-render-device-<timestamp>.txt. Send that file or place it in the VPS workspace and tell me its filename; there is no need to copy the entire console. If the helper fails, send the saved file as well.

The helper verifies the existing font/text-base/TextRender prefixes and receipts with native Windows Python, then verifies the two TTFs and their COPYING notice against their pinned hashes. It sends the probe and those three files to the selected booted x86_64/API28 LDPlayer at127.0.0.1:5555. No APK screen or running server is needed.

Expected completion lines:

```text
ANDROID TEXT BASE ARTIFACTS VERIFIED
ANDROID FONTS ARTIFACTS VERIFIED
ANDROID TEXT RENDER ARTIFACTS VERIFIED
WESNOTH_ANDROID_TEXT_RENDER version=1.19.26 abi=x86_64 min_api=23
PASS Expat XML and errors
PASS Fontconfig private font selection
PASS Fontconfig character fallback
PASS Cairo image compositing
PASS Cairo FreeType glyph rendering
PASS wesnoth-android-text-render
ANDROID TEXT RENDER TEST PASSED
```

This checks font selection, character fallback and rendering into memory. Actual TextRender execution remains pending until your device result. Full paragraph shaping/bidirectional layout, the game APK/assets/OBB, gameplay and MongoDB remain later required work.
