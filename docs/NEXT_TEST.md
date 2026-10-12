# Build and test the Android font libraries

The Windows game-data verification passed: 26,748 files / 726,207,542 bytes and the complete tree hash match the VPS reference. Keep the verified folder at `D:\Test\wesnoth-setup\gamedata-1.19.26`. No recopy, full data recheck, SDK setup, server rebuild or unchanged media/SDL retest is needed.

The next step builds reusable FreeType 2.13.0 and HarfBuzz 7.1.0 libraries from the existing source cache. A native Android test loads the actual Lato and DejaVu Sans fonts from the verified data, checks Latin ligatures and Arabic shaping, and rasterizes glyphs into memory. This prepares text rendering for the game. It does not open a new app window or implement the complete text-layout/game engine.

## 1. Pull the new tools

Temporarily connect to GitHub and run in normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read the $name commit." }
    }
}
```

Preserve local work, server-local core.filemode=false and stash f0c22d3. Stop on a pull conflict without reset, clean or stash application.

## 2. Build offline and run the real-font test

Keep LDPlayer open at its Android home screen. After pulling, internet access is unnecessary. The build uses the existing native Windows Python 3.14.3, CMake 4.3.0, Ninja 1.13.2 and NDK 26.3.11579264, targeting x86_64/API23.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidFonts.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android font build failed. Send the complete console output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidFonts.ps1' `
        -DataRoot 'D:\Test\wesnoth-setup\gamedata-1.19.26' `
        -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android font test failed. Send the complete console output.'
    }
}
```

Let the first compilation finish; configuration and compilation can take several minutes. Subsequent unchanged builds reuse the output. If a source archive is missing or any build step fails, send its exact error before changing tool versions or packages. This build never downloads dependencies.

The independent output is `wesnoth_client\build\android-fonts\prefix`, containing static FreeType/HarfBuzz libraries, headers, package metadata, license notices and the native test/runtime. A successful build writes its input/output hashes to `build/android-fonts/receipt.json`. The original engine, prepared source, bootstrap, SDL APK, media prefix and verified data folder remain separate.

Before ADB, the device helper verifies the current source hashes, complete installed prefix, runtime artifacts and three selected asset hashes. It pushes only the native test, libc++ runtime, Lato-Regular.ttf, DejaVuSans.ttf and fonts/COPYING into a unique project directory under `/data/local/tmp` on the explicit device. The test uses fixed original font names. Existing apps and data are preserved. No diagnostics transcript is created; send the console output.

Expected build marker: `ANDROID FONTS BUILD COMPLETE`. The device output must include:

```text
WESNOTH_ANDROID_FONTS version=1.19.26 abi=x86_64 min_api=23
PASS FreeType font loading
PASS HarfBuzz Latin ligatures
PASS HarfBuzz Arabic shaping
PASS FreeType glyph rasterization
PASS wesnoth-android-fonts
ANDROID FONTS TEST PASSED
```

Send the full build/test output, including pulled commit IDs and any error. Success verifies the selected font decoding, shaping and in-memory rasterization on Android. It does not establish full paragraph layout, visible game UI, general Android asset import/OBB, gameplay or MongoDB. Those remain subsequent milestones alongside the remaining native dependencies and game engine.
