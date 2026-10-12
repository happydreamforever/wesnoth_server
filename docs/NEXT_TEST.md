# Verify the copied game data

The Windows media build and LDPlayer codec test passed, including PNG, JPEG, WebP, Ogg Vorbis and in-memory SDL_mixer rendering. The user copied the game data to `D:\Test\wesnoth-setup\gamedata-1.19.26`. This step checks that every filename and byte matches the recorded VPS copy. The data stays in that folder; no OBB or Android installation is created yet.

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

Preserve local work, server-local core.filemode=false and stash f0c22d3. Stop on a pull conflict without reset, clean or stash application. The data folder remains outside both repositories.

## 2. Verify the folder offline

After pulling, internet access is unnecessary. This check uses the installed native Python 3.14.3. No server, LDPlayer, compiler, SDK setup or rebuild is needed.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Test-WindowsGameData.ps1' `
        -DataRoot 'D:\Test\wesnoth-setup\gamedata-1.19.26'
    if ($LASTEXITCODE -ne 0) {
        throw 'Game-data verification failed or was interrupted. Send the complete console output.'
    }
}
```

Let it finish reading approximately 726 MB; it prints progress. Expected final output:

```text
PASS: 26,748 files; 726,207,542 bytes; 13 expected empty files
Tree SHA256: d805fd055b263a5b09cd19576dc9df83c64e47bbcf7821cbb6550b686a74e53c
Core 1.19.26; music 1.19.18; manual_install=true (metadata matches).
GAME DATA VERIFICATION PASSED
```

Send the complete console output, including the pulled commit IDs and final result. No diagnostics log file is created. A mismatch is reported by parent directory; preserve the copied files and send the error before changing them. The 13 empty files, two hidden .gitignore files and original line endings are part of the reference. Timestamps, permission bits and empty-directory structure are ignored.

This verifies copy integrity only. The current SDL check app does not consume these assets. Remaining work includes the text/network libraries, actual game engine, Android asset import/OBB, audible playback, single-player, a LAN turn and MongoDB. The existing server, SDL app and media tests remain completed checkpoints.
