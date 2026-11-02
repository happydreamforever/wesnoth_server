# Reinstall the VPS development environment

This directory contains recipes, version inventories and redistributable package inputs. It contains no Docker image export, installed virtual environment, game database, `.env`, production TLS private key or Android signer. The separate migration package must preserve the original Android signer privately.

Use a Linux **x86_64** VPS with Docker Engine available to your user. The original host runs Docker **29.1.3**; the project tools run in the containers below. Do not install the Windows MongoDB ZIP or run Windows service launchers on Linux. The supplied Windows game's runtime-v3 remains on Windows and is not initialized or migrated by these commands.

## Commands

Extract the migration package so the two repositories are siblings. Set these two variables to your actual extracted paths:

```bash
export WESNOTH_WORKSPACE="$HOME/wesnoth-workspace"
export WESNOTH_ENVIRONMENT="$WESNOTH_WORKSPACE/migration/environment"
cd "$WESNOTH_ENVIRONMENT"
sha256sum --check SHA256SUMS
bash restore-environment.sh --workspace "$WESNOTH_WORKSPACE" --phase images
bash restore-environment.sh --workspace "$WESNOTH_WORKSPACE" --phase python --jobs 4
bash restore-environment.sh --workspace "$WESNOTH_WORKSPACE" --phase verify
```

`--phase images` needs internet access for pinned base images, system packages, Boost and Python build-tool packages. It builds seven tool images in dependency order and retains any existing image tag rather than replacing it. `--phase python` and `--phase verify` run with Docker networking disabled. The script prints each command before executing it. Add `--dry-run` to inspect the commands without building, installing or running tests. No command initializes a player database or changes the Windows installation.

The Python phase builds official **CPython 3.12.10** from the included SHA256-pinned source and installs all **17** pinned Linux wheels using `--no-index --require-hashes`. Its prefix is `wesnoth_server/build/host-python-3.12.10`, with `/workspace` as the container mount point. An existing prefix is retained, including an incomplete installation; verification must pass before using it. If compilation stops, preserve its console and prefix and review the first error before retrying.

Expected verification result: `success: true`, `failures: 0`, `errors: 0`, `skips: 0`, Python 3.12.10 and MongoDB 8.0.32. Reports are written beneath `wesnoth_server/build/migration-environment-check-*/` as `result.json`, `unit-tests.txt`, `tests.txt` and `mongodb-fixture.log`. The database is a new disposable loopback replica set inside a network-disabled container. It never reads a game runtime or production credentials. File descriptor limit is 65536, required by the accumulated integration suites.

The smoke runner covers startup/progress, real TLS relay and Court battle/team domain checks. This is an environment check. Android compilation, native-engine combat, rendered UI and Windows device acceptance remain separate checks.

## Images and versions

| Tag | Purpose |
|---|---|
| `wesnoth-server-verify:1.19.26` | GCC 16.2.0, CMake 4.3.0, Ninja 1.13.2, Boost 1.91.0, native server compilation |
| `wesnoth-alliance-verify:python3.14.3-mongo8.0.32` | Compatible MongoDB 8.0.32 binary and libraries; explicitly run the separate Python 3.12.10 prefix |
| `wesnoth-alliance-native-verify:python3.14.3-gcc16.2` | Combined compiler and historical interpreter support for native protocol fixtures |
| `wesnoth-account-integration-verify:20261020` | Native tools plus MongoDB and account dependencies for rendered/native encounters |
| `wesnoth-android-cache-verify:8.9-java21.0.9` | Gradle 8.9 and Temurin Java 21.0.9 |
| `wesnoth-android-sdl-verify:ndk26-java21` | Native/compiler base combined with Java/Gradle; NDK is supplied by the client inputs, not embedded by this Dockerfile |
| `wesnoth-text-toolchain-verify:meson1.12` | Meson 1.12.0 and gperf for rebuilding text dependencies |

The historical `python3.14.3` text in image names does **not** select the project interpreter. Always call `/workspace/wesnoth_server/build/host-python-3.12.10/bin/python3.12` explicitly in these containers. Do not silently use `python`, `python3` or the image's default interpreter for current backend validation.

`pins/docker-bases.json` fixes six base-image digests. `pins/docker-images-observed.json` records original image IDs, architecture and installed package inventories; it is an observation of the old VPS, not a claim that a fresh build will have the same image ID. `pins/dpkg-*.tsv` contain only package names and versions. The original compatible compiler image uses Debian GLIBC 2.41, OpenSSL 3.5.7, ICU 76.1 and Boost 1.91.0. MongoDB 8.0.32 cannot simply be copied into an older incompatible GLIBC environment such as Debian bookworm.

## Native bridge and Room server after restoration

These Linux builds are verification binaries, distinct from Windows artifacts. Use new output directories:

```bash
mkdir -p "$WESNOTH_WORKSPACE/wesnoth_server/build/restored-linux-bridge"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$WESNOTH_WORKSPACE,dst=/workspace,readonly" \
  --mount "type=bind,src=$WESNOTH_WORKSPACE/wesnoth_server/build/restored-linux-bridge,dst=/out" \
  wesnoth-server-verify:1.19.26 \
  sh -c 'cmake -S /workspace/wesnoth_server/alliance_bridge -B /out -G Ninja -DBOOST_INCLUDE_DIR=/opt/boost/include -DCMAKE_BUILD_TYPE=Release && cmake --build /out --parallel 4'

mkdir -p "$WESNOTH_WORKSPACE/wesnoth_server/build/restored-linux-room"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$WESNOTH_WORKSPACE,dst=/workspace,readonly" \
  --mount "type=bind,src=$WESNOTH_WORKSPACE/wesnoth_server/build/restored-linux-room,dst=/out" \
  wesnoth-server-verify:1.19.26 \
  sh -c 'cmake -S /workspace/wesnoth_server -B /out -G Ninja -DCMAKE_PREFIX_PATH=/opt/boost -DCMAKE_BUILD_TYPE=Release && cmake --build /out --parallel 4'
```

Full combat/native GUI verification also needs the client game engine, reconstructed host SDL/text dependencies, and the exact original game data. See the client reconstruction guide. Source-only recipes such as `tests/run_court_native_engine.py` do not magically replace a compiled full engine. Do not count skipped native tests as successful restoration.

## Optional Windows worker compiler verification

The included public MINGW cache contains **107 pinned package archives**, detached signatures and public keyrings. It is not an installed environment and runs no package hooks. The isolated MINGW closure includes its own Python package as a native build dependency; that does not change the project’s explicit Python 3.12.10 interpreter. The schema-5 worker source stays bound to its existing inputs.

To build the optional Wine verification images:

```bash
bash "$WESNOTH_ENVIRONMENT/restore-environment.sh" \
  --workspace "$WESNOTH_WORKSPACE" --phase images --with-wine
```

If a test expects the cache at its historical repository-relative location, copy it only into an absent destination:

```bash
worker_cache="$WESNOTH_WORKSPACE/wesnoth_server/build/world-worker-packages-1192624"
test ! -e "$worker_cache" || { echo 'Existing cache retained; stop and verify it.'; exit 1; }
mkdir -p "$(dirname "$worker_cache")"
cp -R -- "$WESNOTH_ENVIRONMENT/vendor/world-worker-packages-1192624" "$worker_cache"
```

The existing `tools/world-worker-packages-1192624.json` pins every archive and signing key. Linux/Wine compiler evidence is distinct from actual Windows execution. The separate Windows MSYS2 installation and five service windows are not migrated by this VPS package.

## Reproducibility limits and acceptance

The retained Dockerfiles pin base digests and principal tool versions, but their Debian `apt-get` layers do not pin every package revision. They require the original package/download sources still to be available. Rebuilding these recipes can resolve newer Debian package revisions, and must be followed by tool-version checks and the listed tests. Installed-image package inventories make differences reviewable; they are not an apt repository or proof of a fresh rebuild.

The account-integration Dockerfile was recovered from the three top layers of the existing image history: copied MongoDB binary, copied Python site-packages, then PATH. Its upstream native-image recipe is retained. This reconstructed Dockerfile and the fresh complete environment have **not** been rebuilt during package preparation. Do not claim bit-identical image recovery. No Docker images are included, as requested.

Stop at the first unexpected result, retain its logs and review it before dependent build or gameplay checks. No app reset, database reset, identity regeneration, signer replacement or deletion of old recovery evidence is part of environment restoration.

Package-preparation validation: the new runner passed **122 tests, zero failures/errors/skips**, under existing Python 3.12.10/MongoDB 8.0.32 images with networking disabled and sources mounted read-only. Shell/Python syntax and full dry-run commands also passed. This validates the packaged runner, not a freshly rebuilt image or newly compiled interpreter. The retained initial harness failure was corrected by running fake-clock unit tests before starting Mongo background monitors; see `verification/verification-summary.json`.
