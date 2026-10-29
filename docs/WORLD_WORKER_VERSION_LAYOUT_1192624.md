**Current Windows step:** Both version reports have been reviewed: actual Windows version **1.19.26** and preservation checks pass. Follow [preserving worker completion](WORLD_WORKER_VERSION_COMPLETE_1192624.md) after a server-only update. Keep five services stopped; return the final build log before Android or service startup. Earlier instructions below are historical.

# Correct the version diagnostic's linked-executable path

The returned JSON identifies `failure.phase=artifacts`, `FileNotFoundError`, `errno=2` and `winerror=2`. It has `outcome=not_run`, no version result, and no build receipt. Its ownership/source-binding and build-lock checks completed before it entered the artifact phase.

Report: `diagnostics/world-worker-version-20261028-204353-453-06512b95db92479e86cff4c5655fa991.json`. The user pasted its contents; the original saved file and Windows filesystem have not been opened on the VPS. The report does not identify the missing filename.

## Diagnostic correction

The diagnostic incorrectly checked `build/windows-world-worker/engine/src/world-worker.exe`. The pinned engine's top-level CMake file sets `EXECUTABLE_OUTPUT_PATH` to `CMAKE_BINARY_DIR`; the builder configures that directory as `build/windows-world-worker/engine`. The linked executable therefore belongs at **`engine/world-worker.exe`**. The existing builder already locates it successfully and copies it to `bin/world-worker.exe` before the version check.

Both diagnostic comparisons now use the correct linked path. The private DLL, ownership, source binding, version header and before/after checks remain in place. Errors now record a fixed artifact/check label, without disclosing exception messages or private data.

The earlier tests reproduced the diagnostic's incorrect directory assumption. Their capture and preservation results did not verify the actual CMake output layout. New verification exercises the pinned CMake setting, reproduces the old failure and checks the corrected path. This is a diagnostic bug; accepted compilation/linking remains valid. The actual captured worker version and full build acceptance remain pending.

## 1. Update only the server

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

## 2. Retry only the corrected version diagnostic

Disconnect WAN again while keeping local Ethernet connected, then run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsWorldWorkerVersion.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Version inspection was incomplete. Preserve all files and send the new text and JSON reports if produced.'
    }
}
```

The helper verifies source/binary files, then invokes the existing worker once with `--simple-version --no-log-to-file --wnoconsole` and new isolated user-data/cache folders. It retains the previous diagnostic reports and all build files. Source verification may take several minutes; the executable capture has a 30-second deadline.

If the expected version is captured, the console includes:

```text
outcome=version_match; exit_code=0
Captured version: 1.19.26
WORLD WORKER VERSION DIAGNOSTIC COMPLETE
```

Send the complete console and **both new** `diagnostics/world-worker-version-*.txt` and `.json` reports, including on failure. Collection completion is not full worker acceptance; even a complete collection can report a version mismatch, timeout or process failure. Review the result before another build, Android or service startup.

This update changes only the standalone diagnostic and its tests/documentation. The builder, engine/client sources, source bindings, recovery helpers/journals, compiled files, prefix/cache and database remain unchanged. No client pull, rebuild, package preparation, migration, backup or Python installation is required. Keep Python 3.14 until the later G service-acceptance gate. Retain the once-recorded WAN batch status; no log independently measures physical network state.

Verification details and limits: `WORLD_WORKER_VERSION_LAYOUT_VERIFICATION_1192624.json`. Reduced native fixtures and Wine checks do not constitute execution of the user's full Windows engine or gameplay acceptance.
