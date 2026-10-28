# Windows World worker compiler corrections

Current retry (2026-10-28): **all six Windows compiler checks now pass**. The helper then stops during old-stage inventory with `Worker recovery file changed while opening`. Log: `diagnostics/world-worker-build-20261028-082809-546-84c11e64678842bfb6048b43bd7e5e6b.txt`; compiler report: `build/world-worker-toolchain-check-884af478a55748c89d9ce4d5678363c1/report.json`. Only the pasted console was supplied. Full worker preservation/compilation and Android remain pending.

Correction `428402f` handles Windows Python's filename-derived executable permission bits when comparing a file's path and open handle. Only the exact `.exe`/`.bat`/`.cmd`/`.com` difference is permitted; identity, content, links, other metadata and strict post-read checks remain enforced. The exact original failure is reproduced with official Windows Python 3.12.10. Follow the server-only pull and worker-only retry below; preserve every existing recovery file.

The supplied 2026-10-28 F transcript accepts the bridge rebuild and native Room server build. The full World worker stopped at its first Lua compilation with `fatal error: string.h: No such file or directory`. Android rebuilding did not start. Keep A–E and the two successful F builds accepted.

The second defect is in the previous update: Windows Python stores `SYSTEMROOT` in its environment mapping. Copying it into a plain dictionary then requesting `SystemRoot` raises `KeyError`. This has now been reproduced with the official Windows Python 3.12.10 executable and corrected. The old generic user message does not expose its precise exception; new phase messages will distinguish any additional problem.

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

Expected: a successful fast-forward (or already up to date) and HEAD at `428402f` or a descendant containing that preservation correction. Preserve the unrelated README edit. No client pull, dependency download, re-extraction, Python reinstall, migration or repeated bridge/Room build is needed.

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

First, named `RUN World worker` stages: `host`, `isolated-dependencies`, `game-data`, `compiler-environment`, `build-tools`, `compiler-identity` and `compiler-check`. These show progress; they are not the build success marker. Then:

1. `WORLD WORKER COMPILER CHECK PASSED` after C, C++ and resource checks.
2. `Incomplete worker build preserved: ...before-sysroot-...` for the known failed stage (already finished preservation is reused).
3. The full engine configure/build, then `FULL NATIVE WORLD WORKER BUILD PASSED`.

The full compilation can take substantially longer than the bridge. The preflight success alone does not mean the full worker passed. Return the complete console and `diagnostics/world-worker-build-*.txt`. On a preflight failure also return the printed `build/world-worker-toolchain-check-*/report.json` and its phase logs. Retain the cache, prefix, recovery journal and both worker folders; do not delete locks or automatically retry a new failure.

After the full worker passes, review that result before the remaining Android rebuild. G five-service startup and H installation follow F completion; do not initialize a database or start services early. Preserve the existing once-recorded WAN status as historical evidence; the build output alone does not measure physical network state.

## Evidence limits

All **83 focused tests pass**, without skips, on Python 3.12.10 with networking disabled. The exact handoff blocks and wrapper also pass PowerShell parsing. [Current preservation verification](WORLD_WORKER_RECOVERY_VERIFICATION_1192624.json) separates actual execution from controlled test boundaries.

The new VPS check uses official Windows Python 3.12.10 under network-disabled Wine for actual stat/open/hash/journal/lock/rename operations on disposable fixtures. Seven recovery groups pass, including interruption/resumption, uppercase and read-only executables, changed-file/hardlink rejection and real competing-process locks. Only crash boundaries are injected. Linux fixtures separately test every retained metadata guard. [Earlier environment verification](WORLD_WORKER_ENVIRONMENT_VERIFICATION_1192624.json) and [sysroot verification](WORLD_WORKER_SYSROOT_VERIFICATION_1192624.json) remain historical. This is not a full native Windows worker build, Android compilation, worker readiness or gameplay acceptance. The next Windows report supplies that platform's full-build evidence.

Source report: 21,685-byte pasted attachment, SHA256 `e070e908134657820ab99f053285589b0f7968bbeaad253bca2b4a91846e715a`. F's failed worker log: `diagnostics/world-worker-build-20261028-065115-429-661ddeee6ac449e6beeb5c1272b687bf.txt`. Its saved Windows file itself was not supplied.
