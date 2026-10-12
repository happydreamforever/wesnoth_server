# Resume the Windows text-library build

The build configured libiconv/libcharset and compiled both libcharset objects, then failed while linking the archive: `../libtool: line 3280: 0: Bad file descriptor`. Libtool needs valid standard input even when it has no interactive prompts. The corrected runner supplies an empty readable input stream for every tool.

Keep the current build/android-text-base directory and all installed versions. The generated sources/toolchain and compile options are unchanged, so the same build command can resume the owned stage after pulling. Pixman and the Android probe have not run on Windows yet.

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

Only the pulls need internet. Preserve repository-local Git settings and the old saved helper stash. If Git reports a local conflict, stop and return the output; do not reset or overwrite files. The successful diagnostic does not require another Git recovery experiment.

## Build, then run the native LDPlayer test

After both pulls succeed, return to offline use and keep LDPlayer open with Android booted. Paste this entire block into normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Build-WindowsAndroidTextBase.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Text library build failed. Send the complete output.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-AndroidTextBase.ps1' -Serial '127.0.0.1:5555'
    if ($LASTEXITCODE -ne 0) { throw 'Text library device test failed. Send the complete output.' }
}
```

The build uses D:\Test\msys64, the existing SDK/NDK26.3.11579264, MSYS Python3.12.13/Meson1.12.0/Ninja1.13.2 and two jobs. It compiles the release Autoconf/Make and Meson libraries without network access. Configure checks and compilation can take several minutes; let the helper finish. Warnings or unsupported-feature probes alone do not indicate a failure; the exit status and final markers determine success. The new managed stage is D:\Test\wesnoth-setup\wesnoth_client\build\android-text-base. Other completed stages are not rebuilt.

The test verifies current source/artifact receipts with the existing native Windows Python3.14.3, then uses SDK ADB to connect to 127.0.0.1:5555 and executes only the new C probe. The server need not be running. No game-data copy, font transfer, APK install or new app screen is expected.

Expected completion lines:

```text
ANDROID TEXT BASE BUILD PASS
ANDROID TEXT BASE BUILD COMPLETE: ...\build\android-text-base\receipt.json
ANDROID TEXT BASE ARTIFACTS VERIFIED
WESNOTH_ANDROID_TEXT_BASE version=1.19.26 abi=x86_64 min_api=23
PASS libiconv conversion
PASS libiconv error handling
PASS Pixman compositing
PASS wesnoth-android-text-base
ANDROID TEXT BASE TEST PASSED
```

Send the complete console output, including library versions or the first error. These helpers stream to the console; they do not create a transcript. Build/configure logs stay in the owned stage and the device helper prints its retained executable directory. Windows package compilation and actual LDPlayer execution remain unverified until your result. This tests reusable character conversion and pixel compositing, not full text layout, the game APK/OBB or gameplay.
