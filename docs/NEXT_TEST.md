# Inspect the surviving Network build state

Windows network-20261013-065142-325.txt confirms that the depfile fix worked: OpenSSL compiled and installed, and curl configuration finished. The failure is CMake's final Ninja -t restat operation replacing .ninja_log. Ninja can delete the original log before a rename fails, so another build could discard incremental history. The current file state is not shown by the error.

Keep build/android-network and all previous backups in place. First, temporarily connect and pull the diagnostic and updated instructions:

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

After pulling, disconnect and run the following in normal PowerShell. It uses the already installed native Python. It reads only the selected build metadata and saved Network generation/prefix state, then writes a new JSON report under diagnostics. It does not run CMake/Ninja, compile, repair metadata, move/delete build files or access the device. The server and LDPlayer are not needed for this check.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    $report = Join-Path (Get-Location).Path ('diagnostics\network-state-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.json')

    & $python -I -B '.\tools\inspect_android_network_state.py' --report $report
    if ($LASTEXITCODE -ne 0) {
        throw 'State collection was incomplete. Send the saved report and error output.'
    }
}
```

Expected: `ANDROID NETWORK STATE COLLECTED` and `Report saved: ...network-state-....json`. This means the diagnostic finished, not that the build passed. Missing/malformed Ninja logs or failed saved-state checks are findings to return. If collection reports an error, send its saved report and displayed error too.

Attach the complete new diagnostics/network-state-*.json file. It includes exact contents of the three possible Ninja build-log files, their sizes/hashes/record counts, metadata for .ninja_deps/build.ninja, and read-only validation of saved generation and the partial installed prefix. It does not collect .env, full environment variables, source-cache contents or command text from the Ninja manifest.

Build/run/device commands are deferred until this report establishes what survived the failed log replacement. Do not rerun the older backup or build blocks in the meantime. All earlier completed native stages remain verified.
