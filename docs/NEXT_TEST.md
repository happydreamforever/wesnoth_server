# Recover the client update and rerun the diagnostic

The Windows FreeType/HarfBuzz build and real LDPlayer font test passed, including Latin ligatures, Arabic shaping and glyph rasterization. Their pixel counts match the Linux check. Keep the completed builds and verified `D:\Test\wesnoth-setup\gamedata-1.19.26` folder.

The latest pull updated the server to c2da5e0, but the client remains at75b1d25: Git fetched e75b0bf and then refused to overwrite a local change to tools/check_android_text_toolchain.sh. The corrected Python/Meson diagnostic has therefore not run on Windows. A working-tree executable-bit difference is possible, as previously confirmed in the server, but the client difference is not yet identified.

The guarded command below prints helper metadata and checks both its index and content against HEAD. It stops on any staged/content difference or Git error, preserving the file. Only if both checks pass does it set client-local core.filemode=false, verify that setting, pull both repositories and run the corrected diagnostic. Keep all installed versions, existing server-local configuration, saved stash and completed builds.

The remaining text libraries use MSYS Make and Meson. This focused diagnostic checks the selected tools and compiles/archives a small Android object through Make and isolated pkg-config, using temporary paths containing spaces. It installs nothing, does not build the game and does not need LDPlayer or the server running. Actual Autotools/Meson package builds remain the following checkpoint.

## Pull and check

Temporarily connect to GitHub and run in normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\msys64\usr\bin\bash.exe'
    $prefix = 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client '
    $file = ' -- tools/check_android_text_toolchain.sh'

    & $bash --noprofile --norc -c ($prefix + 'diff --no-ext-diff --no-textconv --raw --numstat HEAD' + $file)
    if ($LASTEXITCODE -ne 0) { throw 'Inspection failed. Send the output.' }

    foreach ($check in @(
        'diff --no-ext-diff --no-textconv --cached --quiet HEAD'
        '-c core.filemode=false diff --no-ext-diff --no-textconv --quiet HEAD'
    )) {
        Write-Host "CHECK: $check"
        & $bash --noprofile --norc -c ($prefix + $check + $file)
        if ($LASTEXITCODE -ne 0) {
            throw 'Helper has staged/content changes, or Git could not check it. Stop and send all output; files are preserved.'
        }
    }

    & $bash --noprofile --norc -c ($prefix + 'config --local core.filemode false')
    if ($LASTEXITCODE -ne 0) { throw 'Client Git setting failed. Send the output.' }
    $mode = & $bash --noprofile --norc -c ($prefix + 'config --get core.filemode')
    if ($LASTEXITCODE -ne 0 -or ([string]$mode).Trim() -ne 'false') {
        throw 'Client Git setting was not confirmed. Send the output.'
    }
    Write-Host "Client core.filemode=$mode"

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }

    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAndroidTextToolchain.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Text toolchain check failed. Send the complete output.'
    }
}
```

Only the pulls need internet. The guarded setting applies to the Windows client repository only; it makes Git ignore working-tree executable-bit differences, while content and staged changes remain guarded. No source is reset, restored, stashed or cleaned. Preserve the existing server-local core.filemode=false and stash f0c22d3. A different local conflict still stops the ordinary fast-forward pull.

The helper uses MSYS2 at `D:\Test\msys64` and NDK26.3.11579264 under the existing `%LOCALAPPDATA%\Android\Sdk`. Its environment is scoped to the child process. Unlike the CMake stages, this build family selects MSYS Python/Meson/Ninja together; existing native CMake/Ninja outputs are unchanged. Autoconf/Automake regeneration tools are reported separately because release archives already contain generated configure scripts.

If the client difference is only its executable bit, the initial metadata should show 100644 -> 100755 with zero added/deleted lines. After the guards pass, expect Client core.filemode=false and successful pulls. If a guard stops, return that output; do not bypass it.

Expected final diagnostic marker:

```text
ANDROID TEXT TOOLCHAIN CHECK PASSED
```

The helper removes its own temporary directory after success and preserves it with a printed path after failure. No diagnostics transcript or app window is created. Send the complete console output, including pulled commit IDs and any missing tool/error; no package installation or version upgrade is requested before reviewing that result.
