# Windows World worker resource correction

The latest Windows attempt passed preservation and reached resource compilation at step 575/589. Its full build has not completed. Correction **224034d** fixes the resource command and permits incremental continuation of this exact recognized stage. Keep all five services stopped and Python 3.14 installed until the later G startup check.

## 1. Pull only the server correction

Temporarily connect to GitHub and run:

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

Expected: a successful fast-forward, or already up to date, with HEAD at 224034d or a descendant containing it. Preserve the unrelated README edit. No client pull, package installation, dependency preparation, migration, backup or repeated bridge/Room build is needed.

## 2. Resume only the World worker

Disconnect WAN while retaining local Ethernet. Keep all five services stopped. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild

    if ($LASTEXITCODE -ne 0) {
        throw 'World worker retry stopped. Preserve all files and send the new saved build log and printed check reports.'
    }
}
```

Expected sequence:

1. `WORLD WORKER COMPILER CHECK PASSED`.
2. `WORLD WORKER GAME RESOURCE CHECK PASSED` using the actual game icon/version/manifest.
3. `WORLD WORKER RESOURCE RETRY PREPARED; existing compilation retained` for this recognized interrupted stage.
4. CMake regeneration and the remaining compilation/link work. Ninja may renumber its remaining steps; the number is not the success criterion.
5. **`FULL NATIVE WORLD WORKER BUILD PASSED`**, including executable version, private DLL closure and artifact verification.

The transition keeps existing objects and their timestamps. A separate resource-recovery journal retains original ownership and inventory; the older sysroot-recovery journal and retained failed stage remain unchanged. Interrupted preparation resumes only unchanged recognized files. Do not remove locks, journals, objects or caches.

Return the complete console and the new `diagnostics/world-worker-build-*.txt`. If it fails, stop and include the printed `build/world-worker-toolchain-check-*/report.json` and `build/world-worker-resource-check-*/report.json` when available. Full worker completion must be reviewed before the remaining Android rebuild. Do not install or start services yet.

## Verified scope

[Verification record](WORLD_WORKER_RESOURCE_VERIFICATION_1192624.json): 119 focused tests pass without skips under CPython 3.12.10 with networking disabled. Actual pinned Windows resource compilation/linking and resource API checks pass under Wine. A reduced CMake/Ninja fixture proves that only resource compilation and linking change, retaining C/C++ command lines, bytes and timestamps. Eight actual Windows Python recovery groups pass. The prospective import audit covers 65 private DLLs and identifies only Windows system libraries USP10.dll and WLDAP32.dll missing from the previous allowlist.

A cache-only RC rule failed the Windows platform check and is not shipped. The owned global make-rules override is loaded after Windows resource initialization and modifies only the RC command. All icon/manifest/version contents remain original. Failed verification attempts are retained alongside the final passing evidence.

The PE and Windows Python checks use Wine; the CMake fixture uses Linux CMake with explicit path adapters. This is not a full 589-step Windows engine build, Android build, worker-service readiness or gameplay acceptance. Existing A–E, bridge/Room builds and Python acceptance remain recorded. WAN status is recorded once per batch; console output alone does not measure network state.
