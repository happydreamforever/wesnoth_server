# Windows World worker dependency preparation

Current Windows checkpoint (2026-10-28): the 107-package cache and Python 3.12 P1–P3 passed. The subsequent targeted aom diagnostic now passes on Windows after the earlier full-prefix ReadError. Resume full preparation once using the [current archive handoff](WORLD_ARCHIVE_DIAGNOSTIC_1192624.md); return its new console/log before migration. Preserve cache/journal/partial files; no new pull, download or repeated Python installation is needed.

The user's Windows inventory reports 24 installed MINGW64 packages and the same 24 cached archives. The console is accepted at that scope; the saved Windows file itself was not opened on the VPS. It does not establish archive integrity, usable installed headers or worker execution. No new WAN state was supplied.

The full worker needs SDL3/image/mixer, Pango/Cairo/Fontconfig, Vorbis, Curl, gettext tools and their dependency chain. The reviewed closure contains 107 packages. Its 24 baseline versions exactly match the user inventory; the remaining 83 archives total 100,641,401 bytes. No UCRT libraries or replacement compiler are introduced.

## Source and integrity

The exact package versions, archive sizes/SHA256s, detached signature sizes/SHA256s, dependency metadata and compressed mtree hashes are committed in [the server package lock](https://github.com/happydreamforever/wesnoth_server/blob/1d79391/tools/world-worker-packages-1192624.json). The captured repository database is signed by the official MSYS2 development key. All 107 real archives and detached signatures were downloaded or read from the existing cache and verified on the VPS against that signed snapshot and the pinned official public keyring.

The source snapshot is `mingw64.db`, SHA256 `07b58b5c8a81a6a4d03373efa5f4b06763b015e261019e293a1aa67f2effddb8`. The official keyring is pinned to MSYS2-keyring commit `5d249077a0cfeec9dbf51515e5e01da413d28859`; the approved signer is `5F944B027F7FE2091985AA2EFA11531AA0AA7F57`. Package URLs come from the [official MINGW64 repository](https://repo.msys2.org/mingw/mingw64/). MINGW64 and UCRT64 have distinct [package prefixes](https://www.msys2.org/docs/package-naming/).

The lock also binds the exact materialized prefix: 57,474 files, 1,686,953,610 bytes, file-manifest SHA256 `118b1baf407947a528f80130cfebce9430149e138dea0974f1e312923c9a6b2f`. Its compiler, Boost, OpenSSL and ICU archives match the user's existing versions.

## Why archives are used directly

Inspecting the actual packages found legitimate hardlinks and installer-generated certificate/cache files. Treating all installed package files as immutable mtree bytes would incorrectly reject those generated files. The worker therefore receives a private, reproducible archive prefix:

- No `pacman` install, refresh, upgrade or removal is performed.
- Original MSYS2 packages and its keyring remain untouched.
- Every regular payload is checked against the signed archive's mtree. Hardlink aliases become independent ordinary files.
- Package scripts and ALPM hooks are not executed or copied into the worker prefix. Signed zero-byte certificate placeholders retain their exact archive bytes; this prefix is for local worker compilation/execution, not a general-purpose replacement MSYS installation or public Internet trust store.
- Paths, case collisions, special files, symlinks, unreviewed payloads, wrong metadata and content changes are rejected.
- The preparation journal retains incomplete extraction. A retry verifies existing bytes and resumes; it does not erase foreign or changed files.
- The final receipt, full tree and package lock must agree before the prefix is used. The native worker build also binds the preparation sources and lock.

## Windows sequence

Follow [A–D in the release checklist](WORLD_ACCEPTANCE_1192624.md): save and stop services, make the private cold backup, pull the coordinated release, then run `Prepare-WindowsWorldWorkerPackages.ps1 -Download` while connected. Expect `WORLD WORKER PACKAGE CACHE VERIFIED` and its text/JSON reports under server `diagnostics`. Stop and return this result even on success; offline preparation and migration follow after review.

Disconnect WAN while retaining Ethernet and record this once for the new offline batch. Run `Prepare-WindowsWorldWorker.ps1`. It rechecks the entire cache and signatures without downloading, then prepares `build/world-worker-prefix`. Expect `WORLD WORKER ISOLATED DEPENDENCIES PREPARED` or `VERIFIED` on reuse. Retain at least 3 GB free for dependency preparation, in addition to backup, worker build and retained Android build storage.

Migration is after this gate. Native Windows compilation, DLL startup, actual AI execution and LDPlayer acceptance remain F–Z checks; successful cache/extraction does not claim them. The old installed-file dependency audit is available for diagnosis but is not the archive-prefix acceptance gate.

Evidence is recorded in `docs/WORLD_WORKER_DEPENDENCY_VERIFICATION_1192624.json`. VPS cryptographic verification uses real Linux GPG; Windows MSYS process/path adaptation is still a Windows acceptance item. Test substitutions and native execution are reported separately.
