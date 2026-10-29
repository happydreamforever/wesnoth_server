# Inspect the linked Windows worker's version

## Current result: collection stopped before a version was recorded

The returned console reports `outcome=not_run; exit_code=None` and incomplete collection. The saved JSON/text files were not supplied to the VPS. Its failure phase and error fields are needed before choosing a correction. Keep five services stopped and preserve every file. Do not repeat the diagnostic or build yet; no new pull is needed for this report-review step.

Read the existing sanitized report and paste its full output:

```powershell
Get-Content -LiteralPath 'D:\Test\wesnoth-setup\wesnoth_server\diagnostics\world-worker-version-20261028-204353-453-06512b95db92479e86cff4c5655fa991.json' -Raw -Encoding UTF8 -ErrorAction Stop
```

If attaching files instead, send that JSON and its matching `.txt` file. No passwords or private runtime files are needed. The following diagnostic installation/run instructions are retained history until report review.

The latest Windows console confirms compiler/resource checks, the account-source continuation, guarded CMake generation, both remaining C++ compilations and successful linking of `world-worker.exe`. It then stops at `Full native engine version differs.` Full worker verification and readiness are still pending.

Saved build log: `diagnostics/world-worker-build-20261028-164511-292-3662c29aa7ee473ca6c674e3864b300b.txt`. Compiler report: `build/world-worker-toolchain-check-ccaca723867245d5a776536d098902b9/report.json`. Resource report: `build/world-worker-resource-check-5178ca251334488e95ea224756a1a05e/report.json`. Only the pasted console was supplied; these saved Windows files and the executable have not been opened on the VPS.

## Finding

The current build checker captures `--version` from stdout. In the pinned engine, Windows enables file logging before handling that option and can redirect stdout to its log. Explicitly disabling file logging can also allocate a console unless `--wnoconsole` is supplied. The error therefore does not by itself prove the binary is a different version.

The diagnostic uses `--simple-version --no-log-to-file --wnoconsole` to inspect the existing executable, with separate retained user-data and cache directories. The required version remains exactly **1.19.26**. It does not rebuild, recover metadata, create a build receipt or access the game runtime. Existing builder/recovery/client sources and source bindings remain unchanged.

Diagnostic implementation: server **931625e**, or a descendant containing it.

## 1. Update only the server diagnostic

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

## 2. Inspect the existing executable once

Disconnect WAN again while keeping local Ethernet connected, then run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsWorldWorkerVersion.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Version inspection was incomplete. Preserve all files and send the saved text and JSON reports if produced.'
    }
}
```

Source and binary preservation checks can take several minutes. The actual version process is bounded to 30 seconds and runs once, without retry. Its output is bounded and sanitized; unexpected text is not copied verbatim into the report.

If the expected version is captured, the console includes `outcome=version_match; exit_code=0`, `Captured version: 1.19.26` and `WORLD WORKER VERSION DIAGNOSTIC COMPLETE`. Report other outcomes unchanged.

Return the complete console and **both** `diagnostics/world-worker-version-*.txt` and `.json`, even if collection completes. Keep the new diagnostic scratch directory locally.

A matching version is useful evidence, but diagnostic completion is not `FULL NATIVE WORLD WORKER BUILD PASSED`. A mismatching/empty version, process failure or timeout can also produce a complete diagnostic report. Review the report before selecting the preserving build-completion correction. Keep all build stages, objects, Ninja variants, journals, backups and the isolated prefix intact.

No client pull, Python installation, package preparation, migration, new backup, bridge/Room rebuild, Android rebuild or service startup is required here. Keep Python 3.14 installed until the later G acceptance. The prior once-per-batch WAN confirmation remains recorded; these logs do not independently measure the physical network state.

## Verification scope

See `WORLD_WORKER_VERSION_VERIFICATION_1192624.json` for focused collection tests, Windows execution under Wine, output-routing reproduction and preservation inventories. The reduced native routing fixture is not the user's full executable. Its actual captured version remains pending the returned report.

Before later service acceptance, review worker/companion admission-stream launches as well: their current `--no-log-to-file` invocation lacks `--wnoconsole`, allowing console allocation to redirect streams when no console is attached. That adjacent issue is recorded, not changed or runtime-accepted by this diagnostic delivery.
