# Build and test font selection and Cairo rendering

Your GLib2.82.1 Windows build and every LDPlayer probe check passed. Preserve that completed stage and all earlier successful prefixes.

The next independent stage builds cached Expat2.5.0, Fontconfig2.17.1 and Cairo1.16.0 using the existing tools. It consumes the completed fonts/text-base prefixes read-only. No source download or package installation is needed.

## Pull the prepared update

Temporarily connect Windows to GitHub. Paste this block into normal PowerShell:

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

Only the pulls need internet. Keep repository-local Git settings and saved stashes. If a pull reports a conflict, stop and return its output; preserve local files.

## Build, then run the native LDPlayer test

Return to offline use and keep LDPlayer open with Android booted. Paste this entire block into normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidTextRender.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Text rendering build failed. Send the complete output.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidTextRender.ps1' -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) { throw 'Text rendering device test failed. Send the complete output.' }
}
```

The build uses D:\Test\msys64, existing MSYS Python/Meson/Make/Ninja and NDK26.3.11579264 with two jobs. Its separate output is D:\Test\wesnoth-setup\wesnoth_client\build\android-text-render. Let configuration and compilation finish. No repeated backup or rebuilding of earlier stages is required.

The device helper first uses native Windows Python3.14.3 to verify the completed fonts/text-base and new text-rendering prefixes and receipts. It then verifies exactly these existing files under D:\Test\wesnoth-setup\gamedata-1.19.26 against their pinned sizes and hashes: fonts/Lato-Regular.ttf, fonts/DejaVuSans.ttf and fonts/COPYING. Before ADB starts, it stops if any required input differs.

The test sends one native executable and those three small font/license files to a unique directory on the selected LDPlayer instance. It checks incremental XML parsing and error handling, private font registration and selection, fallback from Lato to DejaVu Sans for an Arabic character, image compositing and glyph rendering into memory. No new APK screen or running server is needed. This is font selection and rendering; full paragraph shaping/bidirectional layout remains a later Pango checkpoint.

Expected completion lines:

```text
ANDROID TEXT RENDER BUILD PASS
ANDROID TEXT RENDER BUILD COMPLETE: ...\build\android-text-render\receipt.json
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

The probe also reports Expat2.5.0, Fontconfig21701 (2.17.1), Cairo1.16.0 and FreeType2.13.0. Send the complete console output on success or failure. These helpers stream output without creating a transcript; package configure logs and Meson's log remain under build/android-text-render/build. The device helper prints the retained test directory. Actual Windows compilation and LDPlayer execution of this new batch remain pending until your result. The game APK, asset import/OBB, gameplay and MongoDB remain later required work.
