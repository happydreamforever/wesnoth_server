# Build and test GLib on Android

Your Windows gettext/PCRE2/libffi build and all LDPlayer probe checks passed. The repeated LLVM output-stream error is resolved. Keep the successful `build/android-text-base` and `build/android-glib-deps` directories and the backup already saved.

The next stage builds GLib 2.82.1, GObject, GIO, GModule and the GThread compatibility archive from the existing cached source. It consumes both verified prerequisite prefixes read-only and uses the selected NDK's system zlib interface for GIO compression. No tool installation or cache download is needed.

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
        -File '.\tools\Build-WindowsAndroidGlib.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'GLib build failed. Send the complete output.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidGlib.ps1' -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) { throw 'GLib device test failed. Send the complete output.' }
}
```

The build uses D:\Test\msys64, existing MSYS Python/Meson/Ninja and NDK 26.3.11579264 with two jobs. Its separate output is D:\Test\wesnoth-setup\wesnoth_client\build\android-glib. Configuration and compilation can take several minutes; let the helper finish. No repeated backup or rebuilding of successful prerequisite stages is required. Feature checks reporting unsupported facilities are not by themselves build failures; use the exit status and final markers.

The test uses native Windows Python 3.14.3 to verify all three prefixes and receipts before SDK ADB transfers one executable to 127.0.0.1:5555. It checks Unicode conversion and errors, regular expressions, serialized values, object signals/lifetime, gzip memory streams, threads/main-loop delivery and process-symbol lookup. No APK installation, new app screen, game-data transfer or running server is needed.

Expected completion lines:

```text
ANDROID GLIB BUILD PASS
ANDROID GLIB BUILD COMPLETE: ...\build\android-glib\receipt.json
ANDROID TEXT BASE ARTIFACTS VERIFIED
ANDROID GLIB DEPS ARTIFACTS VERIFIED
ANDROID GLIB ARTIFACTS VERIFIED
WESNOTH_ANDROID_GLIB version=1.19.26 abi=x86_64 min_api=23
PASS GLib Unicode and regex
PASS GLib variants
PASS GObject signals and lifetime
PASS GIO streams and compression
PASS GLib threads and main context
PASS GModule process symbols
PASS wesnoth-android-glib
ANDROID GLIB TEST PASSED
```

The probe also prints GLib and zlib versions. GLib must be 2.82.1; the NDK zlib header version and Android system zlib runtime version can differ. The compression round trip tests the selected interface on the actual device.

Send the complete console output on success or failure. The helpers stream to the console without creating a transcript; Meson configuration details remain in build/android-glib/build/glib/meson-logs/meson-log.txt. The device helper prints its retained executable directory. The VPS build and host checks cannot establish Windows compilation or Android execution of this new stage; those results await this test. Full text layout, the game APK/OBB and gameplay remain later steps.
