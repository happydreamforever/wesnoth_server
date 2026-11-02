# Deliberate exclusions

No original workspace file was deleted to create this transfer.

- Raw `.git` directories/config/hooks, SSH/Git credentials, unrelated home settings: replaced by fresh full reachable-ref bundles, exact working trees and staged/unstaged binary patches. Reflog-only/unreachable objects are not promised. Reconfigure your own Git author/authentication.
- Old duplicated `wesnoth/` checkout and untracked upstream scaffolding outside the two repos' active pinned `engine/`: not used by current builders; active code is included with its history.
- Copied root `msys64/` and installed Windows/Python/SDK/NDK/native prefixes: environment installations, recreated from exact package/source pins and retained dependency archives. Actual Windows installation remains on Windows.
- Docker image layers/cache: reinstall from included recipes and recorded digests/versions. Package-layer availability remains an environment acceptance gate.
- Compiled objects, native libraries, obsolete/prior complete APK stages, repetitive compiler/audit caches, Gradle daemon/transforms and lockfiles: rebuildable outputs. Current1192629and originalbaseAPKs plus selected source/evidence and update journals are retained outside active stages. Builders must create fresh receipts after fresh output verification.
- Temporary audit MongoDB databases, throwaway users/passwords/sessions, diagnostics crash dumps and process/operation locks: not source or needed persistent game state. No production Windows database was copied or reset.
- Old expanded `gamedata-1.19.26`: omitted to avoid a second copy and because it missed one pinned40387-byte pyc. Complete verified OBB/index/receipt/owner files are included; restoration recreates every original byte.
- Obsolete root `handoff/*.bundle`: replaced by fresh complete bundles for both current repos.
- Historical bulk screenshots/logs and optional experiments: tracked published evidence is retained; selected current1192629 raw evidence/render scripts remain. Old absolute paths in reports describe original runs, not new-VPS files.
- Original Windows cold backups/runtime/private credentials/campaign saves/signing identity were not in this Linux workspace and remain on the user's Windows machine. This development transfer must never replace them.

Retained caches are intentional dependencies: exact native source archives, SDK/NDK installers,107pinned worker packages,17LinuxPythonwheels and the minimum reviewed Gradle offline inputs. Deleting these would make offline rebuilding dependent on re-downloading old versions.
