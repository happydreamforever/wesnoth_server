# Resume the Windows World worker after Ninja generation failure

The supplied JSON was opened and checked: `world-worker-ninja-20261028-134310-139-aba19effeed9452caf5de5c8aab5626d.json`, 93,837 bytes, SHA256 `ec2ad389eaf2c256b80665d3c0433d6f4a02fb7f8bdb77f7489348b97db930ee`.

It confirms that `.ninja_log` is missing and `.ninja_log.restat` retains the **exact original 64,517 bytes** recorded by the resource-recovery journal. SHA256: `5dcaf12944cd883d3b801a2140e42e09357ce3f5310f9d8e453e8adae5710ace`. There are 575 unique output records: 571 object files and four archives. `.ninja_deps` is unchanged, and the recorded source binding matches. These records do not replace checking the actual compiled files on Windows.

File read/write/delete access probes succeeded at collection time; the directory DELETE_CHILD probe returned error 5. This does not identify the historical rename failure cause. Do not change permissions, elevate the build, disable security software or delete metadata as a workaround.

## What the correction does

The helper accepts this exact reviewed diagnostic and the known incomplete worker binding. It rechecks the live metadata, original resource journal and all 575 recorded outputs, validates the generated source, and records an immutable recovery inventory. It restores the missing log by exclusive copy, preserving `.restat`, `.ninja_deps`, compiled files and older journals. Only the builder/helper source binding is advanced; unrelated source or dependency changes are rejected.

Every subsequent explicit CMake configure retains verified backups of both Ninja metadata files, temporarily withholds them from CMake's restat/recompaction, and restores their bytes, timestamps and attributes before compilation. An interrupted operation has a resumable journal. Changed or unexpected files stop recovery. Automatic CMake regeneration is disabled and checked before compiling. A shared build lock prevents two updated helpers operating on this stage together.

This is metadata recovery and incremental continuation. It does not establish full worker readiness until the normal executable, DLL, version and receipt verification completes. Previously accepted Python, dependency, migration, bridge and Room steps remain accepted. Android remains pending.

Implementation: server **5acf828** or a descendant containing it.

## 1. Pull the server correction

Keep all five services stopped. Temporarily connect to GitHub and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $worldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $worldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) {
        throw 'Server pull failed. Preserve local changes and send the output.'
    }
}
```

No client pull or additional package download is required. Keep the original JSON at its existing Windows diagnostics path; do not edit or regenerate it.

## 2. Resume only the worker

Disconnect WAN again while retaining local Ethernet. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild `
        -NinjaReportPath 'D:\Test\wesnoth-setup\wesnoth_server\diagnostics\world-worker-ninja-20261028-134310-139-aba19effeed9452caf5de5c8aab5626d.json'

    if ($LASTEXITCODE -ne 0) {
        throw 'Worker recovery/build stopped. Preserve all files and send the complete console and saved build log.'
    }
}
```

Expected sequence:

1. Compiler and actual game-resource checks pass.
2. `WORLD WORKER NINJA HISTORY RECOVERED; existing compilation retained`
3. CMake configuration/generation completes.
4. `WORLD WORKER NINJA CONFIGURE GUARDED; original history restored`
5. Incremental compilation/linking and the existing artifact checks.
6. `FULL NATIVE WORLD WORKER BUILD PASSED`

The history/guard markers alone are not full build acceptance. Return the entire console and newly printed `diagnostics/world-worker-build-*.txt`. Stop at the first unexpected result; include any printed compiler/resource reports on failure. Retain new `.ninja-recovery*`, `.ninja-configure-*` and `.build.lock` files along with all previous recovery journals, builds, cache/prefix, runtime, backup and saves. Do not manually rename/delete them or run Ninja/CMake separately.

Wait for the worker result review before Android rebuilding or service startup. Do not repeat the accepted migration, dependency preparation, bridge/Room builds or Python installation. Keep Python 3.14 installed until the later five-service acceptance gate. The existing once-per-batch WAN confirmation remains recorded; these reports do not independently measure WAN status.

## Verification

See `WORLD_WORKER_NINJA_RECOVERY_VERIFICATION_1192624.json` for the final tested source hashes, regression results and real-tool evidence. Native Windows tools run under isolated Wine on the VPS; that evidence is separate from the pending build on the user's Windows computer.
