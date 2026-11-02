# Resume Wesnoth development on a new VPS

Snapshot: 2026-11-02. Android1192629, protocol5, schema5, backend/native worker1192626. This is a **private development transfer**, not a production database export or a new Windows update.

## What to do first

Use a Linux **x86_64** VPS; Ubuntu24.04 is the old host baseline. Have at least **35GB free initially**, and preferably100GB+ for native/Android builds and retained future recovery stages. The transfer includes the two source repositories, their full reachable Git histories, actual uncommitted edits, original map/design assets, complete game data, original VPS Android signing key, pinned source/dependency archives, minimal offline Gradle inputs and current workflow records. Generated build objects, installed tools, Docker images and old duplicate builds are intentionally omitted.

Copy this ZIP and its adjacent `.sha256` file to the new VPS, then:

```bash
# From the directory containing both downloaded files:
sha256sum -c future-migration-1192629-20261102.zip.sha256
umask 077
unzip -q future-migration-1192629-20261102.zip
cd future-migration-1192629-20261102
python3 -I -B migration/restore.py
```

System Python3.10+ and Git are enough for restoration; project Python3.12.10 is installed separately. Install `git`, `unzip` and `python3` using your VPS distribution package manager if absent. Do not extract over an existing checkout. The helper verifies every listed file, restores Git metadata without checking out over your edits, verifies both Git histories and reconstructs the exact game-data tree. It never starts a service, initializes MongoDB, downloads software or replaces a signing key. Expected last line: `MIGRATION SOURCE RESTORE VERIFIED`. Retain any error and stop before dependent steps.

Next read:

1. `migration/CURRENT_STATUS.md` — accepted Windows results and the exact next test.
2. `migration/environment/README-ENVIRONMENT.md` — environment versions, source pins, Docker recipes and reinstall commands. Docker must be installed separately and available to your user; see `migration/HOST-SETUP.md` for Ubuntu24.04 commands.
3. `migration/README-ANDROID-REBUILD.md` — clean native/Android prerequisite order, original signer selection and offline packaging.
4. Root `AGENTS.md`, then both repositories' `docs/NEXT_TEST.md`, `docs/WORKFLOW.md`, `docs/BASELINE.md`. Read the latest checkpoint first; the long older history does not override it.

The fresh environment and full clean Android/native builds must be verified on the new VPS. Recreated apt layers may contain different package revisions; retained version inventories make those differences reviewable. Historical PASS reports do not certify an environment that has not yet been rebuilt.

## Important preserved state

- Git bundles and dirty patches: `migration/git/`. Restored branch: `main` in both repositories. Original checkout HEADs are in `repositories.json`. Migration delivery notes/helpers are committed. Only pre-existing README/server-document edits remain uncommitted and are preserved. Review these before future commits; never use a destructive reset to hide them.
- All current code is under `wesnoth_client/engine`, `alliance_game`, `alliance_native`, presentation tools, and the server's tracked engine/backend/bridge/worker paths. Omitted untracked upstream placeholders were not the active source tree.
- Android signer: `wesnoth_client/build/android-game-host-user/.android/debug.keystore`. Keep it private. The VPS signer is not the Windows production signer.
- The bundled public-config fixture and its test TLS key remain at the historical client build fixture path. This fixture is distinct from Windows production identity; never deploy it over Windows configuration. Certificate validation/expiry is still enforced.
- Current and original base APKs, prior update journals and receipts are **evidence only** beneath `migration/evidence`. They cannot make an omitted native stage complete. Fresh account packaging does not use `--prepare-update`.
- Game data is restored from the four-file `wesnoth_client/build/android-game-data` stage. The old expanded tree was missing one pinned compiled Python file. The verified OBB contains it, so reconstruction restores the complete original bytes without changing game code or indexes.
- `map_infor` retains all original128-Area/64-Castle sources. Current PNGs,1024px overviews and hashes stay unchanged. Do not rerun the old asset generator as a verification shortcut; it does not preserve every current overview manifest entry.
- `migration/MANIFEST.json` records file hashes, byte sizes and modes. `migration/EXCLUSIONS.md` describes omissions. `migration/reference` contains the approved Emerald Court concept and the older, explicitly superseded requirement document.

## Private transfer and external files

This ZIP is **not encrypted** and contains the original VPS Android signing key and a private test fixture key. Use a private transfer/storage location. Do not upload the ZIP, signing key or fixture key to GitHub, a public sharing site or diagnostics.

Windows runtime-v3, player accounts, credentials, Crown balances, saves, trusted connection, Windows signer, MSYS2 and private backups remain on your Windows computer; they were not present as production data in this VPS source transfer. Keep them there. Host SSH keys, Git authentication, unrelated home-directory settings, installed Codex/plugins and shell credentials are not copied; set up access on the new VPS yourself. No other application database is included. The recorded Git origins are public URLs without credentials.

## Prompt for the agent on the new VPS

> Continue development of the workspace in this directory. Read START_HERE.md, migration/CURRENT_STATUS.md, root AGENTS.md and the newest client/server NEXT_TEST checkpoints. First verify the migration and rebuild the missing development environment using the preserved pins and scripts; do not initialize or replace the Windows runtime. Android1192629 is already installed on Windows and five-service startup passed. Windows manual F1–F7 remains pending. Preserve current uncommitted edits, signer, public fixture, game data and history. Stop at the first unexpected result and retain diagnostics.
