# Open the actual offline game on LDPlayer

Your Windows engine build and LDPlayer version test passed. This step packages that completed engine into **Wesnoth Offline**, prepares an OBB from the already copied `D:\Test\wesnoth-setup\gamedata-1.19.26`, and opens the game. Keep LDPlayer running. The first data import can take several minutes. Allow roughly 2 GB free on the emulator for the OBB, extracted data, APK and game cache.

Temporarily connect and update both existing checkouts with MSYS2 Git. Run this in PowerShell:

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

The following build and device test use existing tools and caches without downloads. You can disconnect internet after pulling. Run this entire block in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\game-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')

    try {
        & {
            & $python -I -B -u '.\tools\prepare_android_game_data.py' `
                --data-root 'D:\Test\wesnoth-setup\gamedata-1.19.26'
            if ($LASTEXITCODE -ne 0) { throw 'Game-data OBB preparation failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Build-WindowsAndroidGame.ps1'
            if ($LASTEXITCODE -ne 0) { throw 'Game APK packaging failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Test-AndroidGame.ps1' -Serial '127.0.0.1:5555'
            if ($LASTEXITCODE -ne 0) { throw 'Game launch check failed. Send the saved log and game-logcat file.' }
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

- `ANDROID GAME DATA PREPARED`: all 26,748 source files match the trusted data hash. The 731,274,164-byte stored-ZIP OBB is `build/android-game-data/main.1192600.org.wesnoth.offline.obb`. The original folder stays unchanged.
- `ANDROID GAME BUILD PASS`: Gradle packages a signed debug x86_64 APK at `build/android-game/app/build/outputs/apk/debug/app-debug.apk`. It reuses the engine and dependencies; it removes debug information only from new copies. No native recompilation is requested.
- `ANDROID GAME ARTIFACTS VERIFIED`, successful APK installation and OBB transfer/hash verification. This creates the separate `org.wesnoth.offline` app, versionName1.19.26/versionCode1192600; the earlier SDL Check app is a different package.
- A **Wesnoth Offline** data-import screen opens. It verifies every extracted file locally against the full trusted manifest inside the APK. Progress remains visible; no online asset download is used. After import, the actual game activity starts.
- The helper waits up to ten minutes for this run's data and activity readiness markers, then prints `ANDROID GAME LAUNCH CHECK PASSED`. **This is an import/activity check, not proof that the title screen or gameplay works.** Native initialization may still need time after the activity opens.

When the title screen appears, check that text and images are readable and buttons respond. Open the tutorial or a local game, move a unit and finish one turn if possible. Report exactly how far it reaches, whether sound plays, and any visible error or crash. Keep internet disconnected during this check. Do not select an online multiplayer server or download add-ons for this milestone.

Attach the saved `diagnostics/game-*.txt` even on success. The helper also prints paths for `game-logcat-*.txt` and any copied `game-userdata-*` native log directory; include those on failure. If the importer or build fails, preserve its files and send the logs before deleting or rebuilding anything. This does not require new tools, another engine/dependency/server rebuild, a new data download or a new inventory. Existing user data, native stages, caches and receipts are preserved.

The next confirmed milestone needs your visual/runtime result. LAN gameplay with the Windows server, a physical Android phone, release packaging and local MongoDB integration remain subsequent required work.
