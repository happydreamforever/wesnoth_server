# Retry Cairo configuration, then test font rendering

Your new log confirms Expat and Fontconfig built, then Cairo configuration stopped on a Bash temporary-file error. The Android test was not reached. Keep the current build/android-text-render directory and all earlier successful stages.

The updated helper gives Cairo configuration a fresh private temporary directory and records each attempt. It retries at most twice after the exact reported busy-file failure; other failures stop immediately. The existing sources, compiler and dependencies are reused. No source download, package installation or manual file edit is needed.

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

The build uses D:\Test\msys64, existing MSYS Python/Meson/Make/Ninja and NDK26.3.11579264 with two jobs. Its separate output is D:\Test\wesnoth-setup\wesnoth_client\build\android-text-render. Let configuration and compilation finish. No backup or deletion is required. Keep all files in the existing stage. The helper reruns configuration and reuses available object files; earlier prerequisite stages are not rebuilt.

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

The probe also reports Expat2.5.0, Fontconfig21701 (2.17.1), Cairo1.16.0 and FreeType2.13.0. Send the complete console output on success or failure. Cairo attempt logs and failed config.log/config.status snapshots are retained under the attempt paths printed by the builder. Other package configure logs and Meson's log remain under build/android-text-render/build. The device helper prints the retained test directory. Actual Windows compilation and LDPlayer execution of this new batch remain pending until your result. The game APK, asset import/OBB, gameplay and MongoDB remain later required work.
