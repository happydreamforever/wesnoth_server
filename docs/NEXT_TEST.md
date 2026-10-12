# Build and test the next GLib prerequisites

The Windows libiconv/libcharset and Pixman build and actual LDPlayer probe passed. Keep the completed build/android-text-base directory. The next separate stage builds gettext-runtime/libintl 0.21.1, PCRE2-8 10.42 and libffi 3.4.4 from the existing cache. It uses the verified libiconv library without rebuilding or changing that prefix.

## Pull the prepared update

Temporarily connect Windows to GitHub. Run in normal PowerShell:

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

Only the pulls need internet. Preserve repository-local Git settings and the old saved helper stash. If Git reports a local conflict, stop and return the output; do not reset or overwrite files.

## Build, then run the native LDPlayer test

After both pulls succeed, return to offline use and keep LDPlayer open with Android booted. Paste this entire block into normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidGlibDeps.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'GLib prerequisite build failed. Send the complete output.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidGlibDeps.ps1' -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) { throw 'GLib prerequisite device test failed. Send the complete output.' }
}
```

The build uses D:\Test\msys64, existing MSYS Python 3.12.13/Make 4.4.1 and NDK 26.3.11579264 with two jobs. Release configure checks and compilation can take several minutes; let the helper finish. The owned output directory is D:\Test\wesnoth-setup\wesnoth_client\build\android-glib-deps. No package installation or completed-stage rebuild is required. Configure warnings and unsupported-feature checks alone are not failures; use the final markers and exit status.

The test verifies both prefixes and their receipts with native Windows Python 3.14.3, then uses SDK ADB at 127.0.0.1:5555 to send one executable and one small synthetic translation catalog. It checks catalog conversion and plurals, Unicode regular expressions, mixed integer/double and structure calls, and a native callback. No APK install, new app screen, game-data transfer or running server is needed.

Expected completion lines:

```text
ANDROID GLIB DEPS BUILD PASS
ANDROID GLIB DEPS BUILD COMPLETE: ...\build\android-glib-deps\receipt.json
ANDROID TEXT BASE ARTIFACTS VERIFIED
ANDROID GLIB DEPS ARTIFACTS VERIFIED
WESNOTH_ANDROID_GLIB_DEPS version=1.19.26 abi=x86_64 min_api=23
PASS gettext catalog
PASS PCRE2 Unicode
PASS libffi calls
PASS libffi closure
PASS wesnoth-android-glib-deps
ANDROID GLIB DEPS TEST PASSED
```

Send the complete console output on success or failure. These helpers stream to the console and do not create a transcript. Package logs remain in the owned build directory; the device helper prints the retained executable/catalog directory. Windows compilation and LDPlayer execution of this new batch remain unverified until your result. GLib itself, full text layout, the game APK/OBB and gameplay are later steps.
