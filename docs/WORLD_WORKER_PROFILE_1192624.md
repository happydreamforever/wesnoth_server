**Current Windows step:** The version diagnostic returned `not_run` and incomplete collection. [Read and return the existing JSON report](WORLD_WORKER_VERSION_1192624.md) before any retry. No pull or build is currently requested. Earlier instructions below are historical.

**Current Windows step:** Worker compilation and linking passed; final version capture stopped. Follow [the existing-executable version diagnostic](WORLD_WORKER_VERSION_1192624.md). Keep services stopped and return both reports before another build. Earlier instructions below are historical.

# Continue the Windows worker after the profile-reader compile failure

The supplied console confirms that the Ninja history recovery, guarded CMake configuration and Windows resource compilation passed. The build resumed with 14 remaining steps, then `alliance_native/account_client.cpp:634` failed because `lstat` is unavailable in the selected Windows compiler. The `NOMINMAX` redefinition is a nonfatal warning, not this failure.

Returned attachment: 10,504 bytes, SHA256 `b77ec156fce918f716f557577637930ff45a84499bc31a7b9ac78787e91ad472`. Saved Windows log: `diagnostics/world-worker-build-20261028-151913-045-8776effadd044d23aaf6bd2c2d8dfa99.txt`. Only the attached console has been opened on the VPS, not that saved log or its compiler/resource reports.

## Correction and preservation

The client source now uses a Windows file handle for the public-profile read. It rejects final reparse points, directories, devices and invalid sizes, bounds the read, and checks the same handle before and after reading. It preserves Windows narrow-path/active-code-page semantics. JSON, certificate, numeric IP and fingerprint validation remain unchanged. The POSIX/Android reader is unchanged.

The server helper recognizes only the reviewed old builder and this exact source correction. It validates the earlier completed recovery and all 575 original recorded outputs, then inventories the current stage, including newly compiled files and current Ninja history. A separate resumable journal preserves the old ownership and inventory before changing only the source binding. Old journals, temporary logs, compiled objects and the isolated dependency prefix remain in place. The existing configure guard remains active.

Both repositories need the update because the worker compiles the shared reader directly from the client repository. No dependency, Python, database, protocol or gameplay-rule change is part of this correction.

Implementation: client **fe91a45** and server **7bfa1f1**, or descendants containing both.

## 1. Pull both corrections

Keep all five services stopped. Temporarily connect to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    foreach ($worldRepo in @('wesnoth_server', 'wesnoth_client')) {
        & $worldBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/' + $worldRepo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) {
            throw "$worldRepo pull failed. Preserve local changes and send the output."
        }

        & $worldBash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/' + $worldRepo + ' rev-parse HEAD')
        if ($LASTEXITCODE -ne 0) {
            throw "$worldRepo commit check failed. Stop and send the output."
        }
    }
}
```

## 2. Retry only the World worker

Disconnect WAN again while retaining local Ethernet. The previous Ninja recovery completed, so this command intentionally omits `-NinjaReportPath`:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild

    if ($LASTEXITCODE -ne 0) {
        throw 'Worker retry stopped. Preserve all files and send the complete console and saved build log.'
    }
}
```

Expected sequence:

1. Compiler and resource checks pass.
2. `WORLD WORKER ACCOUNT SOURCE RETRY PREPARED; existing compilation retained`
3. `WORLD WORKER NINJA CONFIGURE GUARDED; original history restored`
4. Remaining compilation/linking and executable/DLL/version/receipt checks.
5. `FULL NATIVE WORLD WORKER BUILD PASSED`

Return the complete console and the new `diagnostics/world-worker-build-*.txt`. Stop at the first unexpected result. Keep all recovery/lock/journal files and metadata variants; do not rename or delete files, change permissions, or run Ninja/CMake separately.

Full worker acceptance remains pending until the last marker and log review. Android has not started on Windows; wait for the worker result review before rebuilding Android or starting services. Do not repeat the accepted Python installation, package preparation, migration, backup, bridge or Room builds. Keep Python 3.14 installed until the later five-service acceptance gate.

## Verification scope

`WORLD_WORKER_PROFILE_VERIFICATION_1192624.json` records the actual pinned Windows compilation and profile-read checks under Wine, POSIX regression coverage, Android NDK compilation and effective-source comparison, preserving source-transition tests and exact PowerShell syntax checks. Wine and compiler fixtures are not the completed full-worker build on the user's Windows machine. The previously accepted results and once-per-batch WAN confirmation remain recorded.
