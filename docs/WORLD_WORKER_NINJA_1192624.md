# Windows World worker: Ninja metadata inspection

The latest worker retry passes compiler checks, actual game-resource compilation and the resource-stage preservation transition. CMake then stops while running Ninja `-t restat` with `failed recompaction: Permission denied`. The full worker has not passed and Android rebuilding has not started.

Both supplied attachments contain the same 5,827-byte console, SHA256 `b451eab9b13b38798364c7c95203897938e021a6d9fba1822ca42633ad187438`. Saved Windows log: `diagnostics/world-worker-build-20261028-121527-033-bd7e67bf76684965b1e303e324b9dcd1.txt`. The actual saved log and Ninja files have not been supplied.

## Why inspect before another build

[Pinned Ninja 1.13.2 Restat](https://github.com/ninja-build/ninja/blob/v1.13.2/src/build_log.cc#L362-L413) writes `.ninja_log.restat`, removes the original `.ninja_log`, then renames the temporary file. The generic message does not identify which operation failed. The original log might now be present or missing; a syntactically valid temporary file does not by itself establish complete build history.

The current builder/recovery review found no retained file handle or attribute change affecting these logs. The console does not establish a particular holding process, file attribute, permission rule or corrupt file. An earlier Android Network build encountered the same message; its guarded recovery is historical evidence, not authorization to apply that repair to this different worker stage.

Do not run CMake/Ninja, repeat the worker build, delete logs/locks, change permissions or remove attributes before inspecting the report. Keep all five services stopped. Existing compiled objects, retained stages, recovery journals, prefix/cache, runtime, migration and backup remain in place. No Python transition, dependency preparation, migration, bridge/Room build or Android rebuild is repeated.

## 1. Pull the diagnostic only

Temporarily connect to GitHub:

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

Diagnostic implementation: **fa44469** or a descendant containing it. This update adds only diagnostic tooling/tests and workflow records. The worker builder and its source binding are unchanged. No client pull is required.

## 2. Collect the existing state

Disconnect WAN again, retaining local Ethernet. Keep five services stopped and run once:

```powershell
& {
    $ErrorActionPreference = 'Stop'

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsWorldWorkerNinja.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Ninja inspection was incomplete. Preserve all files and send the saved text and JSON reports if produced.'
    }
}
```

Expected markers:

- `WORLD WORKER NINJA STATE COLLECTED`
- `WORLD WORKER NINJA DIAGNOSTIC COMPLETE`

These markers mean collection finished, not that the worker build is healthy or repaired. A missing original log and denied access can be valid diagnostic observations. Return both newly printed `diagnostics/world-worker-ninja-*.txt` and `.json`, even if collection passes. On any error, preserve the reports and stop; do not retry the build yet.

The Python collector reads only fixed build metadata, selected recovery-journal information and relevant source hashes. It captures bounded raw Ninja text logs and file fingerprints. Windows `OPEN_EXISTING` probes request read/write/delete access separately, immediately close each handle, and never write bytes, delete files or request deletion on close. Successful access at inspection time does not prove a later rename will succeed or explain the earlier failure. The wrapper records current file permissions and relevant process metadata without command lines. Only new diagnostic reports are written; no build or repair runs and no game runtime or credentials are read.

Retain the previously recorded WAN status once per batch. The console does not independently measure the physical network. Full worker completion, Android rebuild and later service/gameplay acceptance remain pending.

## Diagnostic verification

VPS diagnostic verification passes 35 focused tests with no skips under exact Python3.12.10/network-disabled execution, including 16 actual Linux PowerShell wrapper scenarios with controlled Windows query/child boundaries. The final collector also passes actual Windows Python3.12.10/API checks under unprivileged Wine, including read-only attributes, sharing-denied access, incomplete blocked reads and whole-fixture byte/metadata preservation. Both exact handoff blocks and the wrapper parse. This verifies collection behavior, not the user's failure cause or a worker repair. Evidence: docs/WORLD_WORKER_NINJA_VERIFICATION_1192624.json. Existing builder sources and recovery bindings remain byte-identical; unchanged native builds/tests were not repeated.
