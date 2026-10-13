# Recover Network build history, then resume the existing build

The returned Windows state JSON confirms that .ninja_log is missing. Its surviving .ninja_log.restat has the exact 942 crypto objects, 90 SSL objects and both archives; the144 installed OpenSSL files and saved generation pass. This recovery preserves the completed work and earlier backups.

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

After pulling, disconnect and open LDPlayer. Run this block in normal PowerShell. It uses the state report already saved in the client diagnostics directory. Keep that JSON at its existing path. The Windows server is not needed for the native loopback HTTPS check.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    $report = Join-Path (Get-Location).Path 'diagnostics\network-state-20261013-092657-266-0a25997b14e74caa908736082192203c.json'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\network-recovery-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')

    try {
        & {
            if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
                throw "The saved state report is missing: $report"
            }
            & $python -I -B -u '.\tools\build_android_network.py' --recover-ninja-state $report
            if ($LASTEXITCODE -ne 0) { throw 'Metadata recovery stopped. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Build-WindowsAndroidNetwork.ps1'
            if ($LASTEXITCODE -ne 0) { throw 'Network build failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Test-AndroidNetwork.ps1' -Serial '127.0.0.1:5555'
            if ($LASTEXITCODE -ne 0) { throw 'Android Network test failed. Send the saved log.' }
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

- `ANDROID NETWORK NINJA STATE RECOVERED`, with a preserved metadata-backup path. Recovery checks the report/current metadata hashes, owned source/generation/prefix records and exact expected output files before creating the missing log. It keeps the surviving .restat.
- Verified OpenSSL generation reuse, protected configure operations, and resumed native compilation. Completed OpenSSL objects should be reused; curl and the probe still need building. A build failure stops before the device test.
- `ANDROID NETWORK BUILD PASS`, then `ANDROID NETWORK ARTIFACTS VERIFIED` and `ANDROID NETWORK TEST PASSED`. The test exercises cryptography and verified HTTPS entirely inside LDPlayer. It opens no visible app window.

Attach the complete saved diagnostics/network-recovery-*.txt, including successful output. If recovery or a configure transaction stops, keep its metadata backup and send the log; do not delete metadata, run Ninja directly or repeat an old stage-rename command. The current repair block is for this reviewed report. Subsequent ordinary builds use Build-WindowsAndroidNetwork.ps1, which explicitly configures both phases while preserving Ninja history; automatic Ninja-driven CMake regeneration is disabled for this owned stage.

No source download, package upgrade, full inventory or rerun of earlier native/server tests is needed. The full game APK/assets/OBB, playable turns and MongoDB remain later required steps.
