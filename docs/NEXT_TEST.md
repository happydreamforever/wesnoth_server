# Build the reusable Android image and audio libraries

The Windows SDL APK build and automated LDPlayer graphics/input test passed. The latest log confirms a presented 1920x1080 OpenGL ES2 frame and the matching tap response. The user also confirmed that manual clicks change the counter/color and the animation moves. Keep the successful SDL app and build outputs.

This step builds the image/audio libraries required by the real game into a reusable Android x86_64/API23 prefix. A native test checks PNG, JPEG and WebP image handling, Ogg Vorbis decoding and SDL_mixer rendering into memory. It does not open a new app window or play sound through the speakers. The actual game engine and remaining text/network dependencies still need integration.

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

## 2. Build offline and test the codecs in LDPlayer

Keep LDPlayer open and wait for its Android home screen. After pulling, internet access is unnecessary. No SDK setup, package installation, server rebuild or unchanged SDL APK rebuild is required.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidMedia.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android media build failed. Send the complete console output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidMedia.ps1' `
        -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) {
        throw 'Android media test failed. Send the complete console output.'
    }
}
```

This first build compiles seven source packages, including SDL with installed development headers and metadata for the future game build. It uses native Windows Python3.14, CMake4.3.0, Ninja1.13.2 and NDK26.3.11579264. Its separate output is build/android-media; it does not replace the existing SDL APK stage. Configuration may take several minutes per package on this computer. Let it finish; subsequent unchanged runs reuse compiled files. Return any exact missing-cache or build error before changing packages.

Expected libraries: libpng1.6.39, libwebp1.4.0, libogg1.3.5, libvorbis1.3.7, SDL3.4.2, SDL3_image3.4.0 and SDL3_mixer3.2.0. The builder verifies the already cached source archives and records input/output hashes in build/android-media/receipt.json. Headers and libraries are installed under:

```text
D:\Test\wesnoth-setup\wesnoth_client\build\android-media\prefix
```

The device helper checks current source and artifact hashes before ADB. It transfers only the native codec test and its runtime libraries into a unique project directory under /data/local/tmp on the explicit device127.0.0.1:5555. It requires a successful process exit and all codec PASS lines. Existing applications, game data and device logs are preserved. These helpers print their report to the console; no diagnostics transcript is created.

Expected build marker: `ANDROID MEDIA BUILD COMPLETE`. The device output must include:

```text
PASS PNG roundtrip
PASS JPEG roundtrip
PASS WebP roundtrip
PASS Ogg Vorbis decode
PASS SDL mixer offline render
PASS wesnoth-android-media
ANDROID MEDIA TEST PASSED
```

Send the full build/test output, including the commit IDs and final PASS or error lines. A successful result verifies codec execution and in-memory mixing on Android; audible playback, the full Wesnoth engine, game data/OBB, local gameplay, LAN play and MongoDB remain pending.

## Reference: the verified server

The server does not need to run for this codec test. If you later need to restart it, use a separate normal PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsServer.ps1'
```

Keep that window open; Ctrl+C stops the server. Its transcript path is diagnostics/server-run-*.txt. No server code is changed by this delivery.
