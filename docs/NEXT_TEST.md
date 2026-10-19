# Next test: resume Alliance dependency preparation

The existing Windows-server/LDPlayer offline game milestone remains passed. The user now authorizes implementation of Alliance Battle, with LDPlayer-only testing. No phone inspection, Android rebuild, server rebuild or repeated guest LAN turn is needed here.

The first backend delivery implements MongoDB persistence, leader/team rules, transactional rewards and a local administrator website. It is not yet connected to the Android game. Read [ALLIANCE_IMPLEMENTATION.md](ALLIANCE_IMPLEMENTATION.md) for the checked and remaining features, and [ALLIANCE_RUNTIME.md](ALLIANCE_RUNTIME.md) for the full build/run/test sequence.

## Returned Windows result

Both pulls succeeded (server 48ba3b0/client 0f45892), and native Python 3.14.3 passed. Preparation stopped on WinError 10060 while downloading `markupsafe-3.0.4-cp314-cp314-win_amd64.whl`. This is a connection timeout; the log does not establish its network cause. The preceding eleven downloads completed verification under the sequential helper. No installation or database initialization ran.

The update below preserves and reverifies that cache. Temporary network failures now get at most three attempts per missing file, separated by 2s and 4s. Certificate, integrity and local file errors still stop preparation. Versions, URLs and hashes are unchanged.

## Do this one step now

Temporarily connect Windows to GitHub and the official dependency download hosts. Run this in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server'
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\Prepare-WindowsAlliance.ps1' -Download
    if ($LASTEXITCODE -ne 0) { throw 'Alliance preparation failed. Send the saved log.' }
}
```

Expected: `Using verified cached ...` for completed files, then `ALLIANCE DEPENDENCIES VERIFIED: 17 wheels; MongoDB 8.0.32.` The full cache is approximately 810 MB, mostly the MongoDB archive which had not been reached. Keep internet connected until preparation finishes. Failed transfers restart only the current file; completed matching files are reused. The helper does not initialize a database, modify `.env`, install a Windows service or rebuild the game.

Return `D:\Test\wesnoth-setup\wesnoth_server\diagnostics\alliance-prepare-*.txt`, including any error. Stop after this step. Offline installation, initial admin setup, the two run windows and browser/persistence checks follow after this preparation result; their complete commands are already documented in ALLIANCE_RUNTIME.md.

## Verified here and still pending

The initial delivery passed 84 checks: 28 domain/rules/source-data tests, 7 authentication tests, 26 HTTP/admin tests, 5 configuration/deployment tests and 18 offline-artifact/PowerShell tests. Real MongoDB 8.0.32/Python 3.14.3 tests ran with networking disabled, including actual authenticated database initialization/restart and production Waitress HTTP startup. PowerShell helpers use Linux PowerShell 7.4.6 with simulated Windows/native tools. Actual Windows offline installation, portable Mongo execution, website browser testing and the eventual Android account/game integration remain unverified.

The retry change passes 28 artifact/PowerShell checks, including a real loopback HTTP 503/read-timeout/recovery test. All 22 artifact cases also pass under matching Python 3.14.3 with external networking disabled. These are VPS results; Windows retry success still requires the new log. Unchanged database/admin tests were not repeated for this download-only fix.

Keep the existing APK/OBB, game-data source, completed native stages and current MSYS2 location. Prior Network recovery and dependency-build instructions are historical.
