# Rerun the corrected MSYS Python/Meson check

The Windows FreeType/HarfBuzz build and real LDPlayer font test passed, including Latin ligatures, Arabic shaping and glyph rasterization. Their pixel counts match the Linux check. Keep the completed builds and verified `D:\Test\wesnoth-setup\gamedata-1.19.26` folder.

Your latest Windows report reached client75b1d25/server4dbea32. All listed tools ran and reported their versions, but the old helper rejected the Python/Meson binding by comparing executable path names. The compiler/archive test was therefore skipped. The correction recognizes same-file aliases and byte-identical copies in the same installation directory, then checks that the actual interpreter has matching Python/Meson runtime locations and versions. It also prints both paths. Pull the correction and rerun this diagnostic; keep all installed versions and completed builds.

The remaining text libraries use MSYS Make and Meson. This focused diagnostic checks the selected tools and compiles/archives a small Android object through Make and isolated pkg-config, using temporary paths containing spaces. It installs nothing, does not build the game and does not need LDPlayer or the server running. Actual Autotools/Meson package builds remain the following checkpoint.

## Pull and check

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

    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsAndroidTextToolchain.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Text toolchain check failed. Send the complete console output.'
    }
}
```

Only the pulls need internet. Preserve local work, server-local core.filemode=false and stash f0c22d3. Stop on a conflict without resetting, cleaning or applying the saved stash.

The helper uses MSYS2 at `D:\Test\msys64` and NDK26.3.11579264 under the existing `%LOCALAPPDATA%\Android\Sdk`. Its environment is scoped to the child process. Unlike the CMake stages, this build family selects MSYS Python/Meson/Ninja together; existing native CMake/Ninja outputs are unchanged. Autoconf/Automake regeneration tools are reported separately because release archives already contain generated configure scripts.

Expected final marker:

```text
ANDROID TEXT TOOLCHAIN CHECK PASSED
```

The helper removes its own temporary directory after success and preserves it with a printed path after failure. No diagnostics transcript or app window is created. Send the complete console output, including pulled commit IDs and any missing tool/error; no package installation or version upgrade is requested before reviewing that result.
