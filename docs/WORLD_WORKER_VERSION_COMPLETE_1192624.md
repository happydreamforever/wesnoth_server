**Current Windows step:** All F builds, including Android **1192624**, passed. Continue with [G: five-service startup](WORLD_ACCEPTANCE_1192624.md#g-start-five-services-and-verify-worker-availability). Return workflow output and the shared-battle window’s worker-ready message before installing. No pull or rebuild is needed. Earlier instructions below are historical.

**Current Windows step:** Full native worker completion passed. Run only the **Android rebuild** in [the current F section](WORLD_ACCEPTANCE_1192624.md#current-f-android-only). Keep five services stopped and return its rebuild/build logs before G startup or H installation. No new pull or worker retry is needed. Earlier instructions below are historical.

# Complete the verified Windows worker without recompiling

Both supplied reports for run `20261028-211023-410-c59efbb7f4224168892e9220898dc14d` have been opened and reviewed on the VPS.

- JSON: 21,180 bytes; SHA256 `5127d2a83fd5ada52cd3200414f741846f4e4b532f3d3407319fa0e240f9a729`.
- Text: 1,542 bytes; SHA256 `d10267c7f91d53f0fcafa91e4d093482a1b1e3e6a6818259d31d931331bc3e9f`.
- Actual Windows executable reports exactly **1.19.26**, exits 0, and produces no stderr. Capture completes in 0.265 seconds.
- The linked and copied executable both contain 49,760,583 bytes with SHA256 `3ef934c178639d53fef336b32addc676399bfb5a960dfe3ff4204fa2cd5a7e83`.
- All seven preservation checks pass. The bin inventory contains the executable and 53 private DLLs; 1,707 source-binding inputs remain unchanged.

This accepts the actual Windows version diagnostic and preservation checks. It does not yet publish the final build receipt or establish native worker gameplay readiness.

## Correction

Fresh builds now capture the exact version with `--simple-version --no-log-to-file --wnoconsole`, separate retained userdata/cache directories and bounded output/time.

For this already linked build, `-VersionReportPath` selects a separate completion path before any configure, compilation, DLL copy or historical recovery. It matches the exact accepted report, original ownership, linked/bin artifacts, source binding and prior recovery history. It rechecks the source overlay, isolated prefix, game data, tool versions, compiler configuration and DLL closure without replacing binaries. A fresh isolated version invocation must match **1.19.26**.

A new external journal retains the report, original ownership bytes, full stage inventory, historical journals and intended receipt. Only the builder/new-helper binding and final receipt are published. Interrupted publication is resumable from the same command. Changes to retained files stop completion; no permission reset, deletion or stage rebuild is prescribed.

The update also adds `--wnoconsole` to Windows worker and companion launches so their inherited admission pipe and logs remain connected. POSIX arguments and game rules remain unchanged. Full runtime admission, AI and gameplay still require later acceptance.

## 1. Pull only the server update

Keep all five services stopped. Temporarily connect to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) {
        throw 'Server pull failed. Preserve local changes and send the output.'
    }

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) {
        throw 'Commit check failed. Stop and send the output.'
    }
}
```

## 2. Complete the existing worker

Disconnect WAN again, keeping local Ethernet connected. Use the exact accepted JSON; omit the old `-NinjaReportPath`:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldVersionReport = 'D:\Test\wesnoth-setup\wesnoth_server\diagnostics\world-worker-version-20261028-211023-410-c59efbb7f4224168892e9220898dc14d.json'

    if (-not (Test-Path -LiteralPath $worldVersionReport -PathType Leaf)) {
        throw 'The accepted version report is missing. Preserve all files and send this output.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild `
        -VersionReportPath $worldVersionReport

    if ($LASTEXITCODE -ne 0) {
        throw 'Worker completion stopped. Preserve all files and send the complete console and new saved build log.'
    }
}
```

Expect named completion checks followed by:

```text
WORLD WORKER VERSION COMPLETION VERIFIED; existing compilation retained
FULL NATIVE WORLD WORKER BUILD PASSED
```

Validation may take several minutes because it reads the existing source, dependency and game-data inventories. No CMake configure or compile steps should run on this completion path.

Return the complete console and the new `diagnostics/world-worker-build-*.txt`. Stop at any unexpected result and preserve everything, including the accepted version report, all older journals and the new `build/windows-world-worker.version-completion*` records. Retain any `.windows-world-worker.version-receipt-pending-*` staging files if interrupted.

Review full worker completion before the remaining Android rebuild and G/H service startup/installation. No client pull, repeated version diagnostic, dependency/Python preparation, migration, new backup, bridge or Room rebuild is required. Keep Python 3.14 installed until G passes. The previous WAN batch confirmation remains recorded; these reports do not independently measure physical network state.

## Verification scope

`WORLD_WORKER_VERSION_COMPLETE_VERIFICATION_1192624.json` records the supplied Windows report review, focused transaction/dispatch/PowerShell regressions, actual Windows filesystem and PE execution under Wine, and the Windows admission-pipe fixture. Synthetic source/report provenance boundaries are named explicitly. Those fixtures do not replace the user's final completion run or later native AI, account admission, Android and gameplay acceptance. Existing native sources, old recovery helpers, signer/profile/OBB, database and campaign saves remain preserved.
