# Windows World worker compiler correction

The supplied 2026-10-28 F transcript accepts the bridge rebuild and native Room server build. The full World worker stopped at its first Lua compilation with `fatal error: string.h: No such file or directory`. Android rebuilding did not start. Keep A–E and the two successful F builds accepted.

The pinned headers are present. The relocated GCC was still using its compiled-in `/mingw64` system root. The corrected builder supplies the verified isolated prefix through an owned CMake toolchain, including the separate resource compiler. It checks C/C++ compilation, threads, runtime DLL execution and Windows resource compilation before touching the previous worker stage. This follows the [CMake sysroot toolchain requirement](https://cmake.org/cmake/help/v4.3/variable/CMAKE_SYSROOT.html) and [GCC system-root behavior](https://gcc.gnu.org/onlinedocs/gcc/Directory-Options.html).

Only the recognized incomplete pre-correction worker is retained under a unique `build/windows-world-worker-before-sysroot-*` directory. An external recovery journal and completion record verify its complete retained inventory and permit interrupted preservation to resume. Its old objects are not reused. Foreign or changed ownership/output is preserved and rejected. Existing package cache/prefix, migration journals, runtime, saves and completed bridge/Room stages are unchanged.

## 1. Obtain the server correction

Keep all five services stopped and Python 3.14 installed until the later G startup check. Temporarily connect to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull failed. Preserve local changes and send the output.' }

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check failed. Stop and send the output.' }
}
```

Expected: a successful fast-forward (or already up to date) and a commit hash containing correction `13e975a` (or a later commit). Preserve the unrelated README edit. No client pull, dependency download, re-extraction, Python reinstall, migration or repeated bridge/Room build is needed.

## 2. Retry only F's World worker

Disconnect WAN again while retaining local Ethernet. Keep the five services stopped. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild

    if ($LASTEXITCODE -ne 0) {
        throw 'World worker retry stopped. Preserve all files and send the new saved build log and compiler-check report.'
    }
}
```

Expected in order:

1. `WORLD WORKER COMPILER CHECK PASSED` after C, C++ and resource checks.
2. `Incomplete worker build preserved: ...before-sysroot-...` for the known failed stage (already finished preservation is reused).
3. The full engine configure/build, then `FULL NATIVE WORLD WORKER BUILD PASSED`.

The full compilation can take substantially longer than the bridge. The preflight success alone does not mean the full worker passed. Return the complete console and `diagnostics/world-worker-build-*.txt`. On a preflight failure also return the printed `build/world-worker-toolchain-check-*/report.json` and its phase logs. Retain the cache, prefix, recovery journal and both worker folders; do not delete locks or automatically retry a new failure.

After the full worker passes, review that result before the remaining Android rebuild. G five-service startup and H installation follow F completion; do not initialize a database or start services early. Preserve the existing once-recorded WAN status as historical evidence; the build output alone does not measure physical network state.

## Evidence limits

All **67 focused tests pass**, without skips, on Python 3.12.10 with networking disabled. The exact handoff blocks and wrapper also pass PowerShell parsing. [Verification record](WORLD_WORKER_SYSROOT_VERIFICATION_1192624.json) separates actual execution from controlled test boundaries.

The VPS verification uses the actual pinned Windows compiler executables under Wine, with network disabled and the prefix mounted read-only, plus actual Python 3.12.10/CMake tests and controlled filesystem recovery tests. It is not a full native Windows worker build, Android compilation, worker readiness or gameplay acceptance. The next Windows report supplies that platform's full-build evidence.

Source report: 21,685-byte pasted attachment, SHA256 `e070e908134657820ab99f053285589b0f7968bbeaad253bca2b4a91846e715a`. F's failed worker log: `diagnostics/world-worker-build-20261028-065115-429-661ddeee6ac449e6beeb5c1272b687bf.txt`. Its saved Windows file itself was not supplied.
