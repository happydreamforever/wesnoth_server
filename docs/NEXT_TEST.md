# Build and load the actual Android game engine

The Network stage passed on Windows and LDPlayer. Keep its completed files and metadata backups; its old report-based recovery command is finished. This step builds the actual Wesnoth 1.19.26 engine using the ten completed dependency prefixes, then runs the engine's version command on LDPlayer. APK/activity and game-data integration follow after this result.

Temporarily connect and pull both existing checkouts through MSYS2 Git:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }
}
```

After pulling, disconnect and open LDPlayer. Run this block in normal PowerShell. The Windows server is not needed for this engine-loading check. The existing verified `gamedata-1.19.26` directory stays in place for the later APK/asset step.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\engine-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')

    try {
        & {
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Build-WindowsAndroidEngine.ps1'
            if ($LASTEXITCODE -ne 0) { throw 'Engine build failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Test-AndroidEngine.ps1' -Serial '127.0.0.1:5555'
            if ($LASTEXITCODE -ne 0) { throw 'Android engine test failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } catch {
        ('ERROR: ' + $_.Exception.Message) | Tee-Object -FilePath $log -Append
        throw
    } finally {
        Write-Host "Saved log: $log"
    }
}
```

Expected sequence:

- Verification of existing Media, text/layout, ICU, Boost and Network prerequisites, without rebuilding them. Hash checks may take a few minutes.
- Native compilation of 537 actual game C++ files, 31 bundled Lua files and the small CLI runner, then linking `libmain.so` and the runner. The engine is substantially larger than the earlier probes; leave the build running until it finishes or reports an error. Default parallelism is two compiler jobs.
- `ANDROID ENGINE BUILD PASS` and a receipt in `build/android-engine/receipt.json`.
- `ANDROID ENGINE ARTIFACTS VERIFIED`, six file transfers to a unique LDPlayer temporary directory, then the actual `Battle for Wesnoth 1.19.26` report with `Library versions:` and `Optional features:`.
- `ANDROID ENGINE TEST PASSED`. No visible app opens: the real engine exits after its version report, before graphics/game-data initialization.

Attach the complete saved `diagnostics/engine-*.txt`, including successful output. If the new stage fails, preserve its files and send the log. Do not delete Ninja metadata, rerun Network recovery, rename old dependency stages, or rebuild earlier libraries. The helper reuses a successfully recorded engine configuration when inputs are unchanged; an interrupted or changed configuration stops for inspection. No source downloads, package upgrades, full inventory or previous server/Android retests are needed.

The actual game APK/activity, offline asset/OBB import, title screen, playable local and LAN turns, physical phone testing and MongoDB remain required future steps. No game-engine execution on Windows/LDPlayer is claimed until this log is returned.
