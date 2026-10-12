# Retry the gettext archive check with the pipe correction

The Windows build stopped during gettext configuration with repeated `LLVM ERROR: IO failure on output stream: Invalid argument`. The log ends with the helper terminating its owned build processes. Wait for the PowerShell prompt before updating or moving the stage.

The next configure operation feeds llvm-ar output into an ELF reader that originally closed after five bytes. This matches the [LLVM Windows closed-pipe bug report](https://www.mail-archive.com/llvm-bugs@lists.llvm.org/msg49040.html). The corrected reader drains the remaining stream while keeping the ELF-class check. The exact Windows behavior still needs your rerun.

Keep all installed versions, cached archives and completed build/android-text-base output. The correction changes the privately extracted gettext configure source, so preserve the failed GLib dependency stage under a unique name and create a fresh one. The commands below perform that preservation without deleting its logs or files.

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

## Preserve the failed stage once

After both pulls succeed and the previous build has stopped, run this block once. It renames only build/android-glib-deps to a sibling backup with a UTC timestamp and GUID. The verified text-base prefix and earlier stages remain available.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $stage = 'D:\Test\wesnoth-setup\wesnoth_client\build\android-glib-deps'
    if (Test-Path -LiteralPath $stage) {
        $item = Get-Item -LiteralPath $stage -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The GLib dependency stage is not a normal directory. Stop and send the output.'
        }
        $backupName = 'android-glib-deps-before-pipe-fix-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N')
        $backup = Join-Path $item.Parent.FullName $backupName
        if (Test-Path -LiteralPath $backup) { throw "Backup already exists; nothing was moved: $backup" }
        Rename-Item -LiteralPath $stage -NewName $backupName -ErrorAction Stop
        Write-Host "BUILD BACKUP SAVED: $backup"
    } else {
        Write-Host 'No active GLib dependency stage to preserve. Existing backups are unchanged.'
    }
}
```

Expected: `BUILD BACKUP SAVED: ...android-glib-deps-before-pipe-fix-...`, or a message that no active stage exists. Keep this backup until the retry succeeds. If a later retry is needed, follow the next diagnosis rather than repeating this preservation step automatically.

## Build, then run the native LDPlayer test

After the backup succeeds, return to offline use and keep LDPlayer open with Android booted. Paste this entire block into normal PowerShell:

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

Send the complete console output on success or failure. These helpers stream to the console and do not create a transcript. Package logs remain in the owned build directory; the device helper prints the retained executable/catalog directory. The Windows correction, completed package compilation and LDPlayer execution of this batch remain unverified until your result. The library-suffix check should now continue through iconv checks instead of repeating LLVM errors. GLib itself, full text layout, the game APK/OBB and gameplay are later steps.
