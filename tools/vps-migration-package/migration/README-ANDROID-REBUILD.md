# Android rebuild after VPS restoration

This compact migration preserves source and inputs, not the old compiled workspace. Native objects/prefixes and Docker images are omitted. Rebuild prerequisites before the account APK. Historical receipts and update journals belong in migration evidence, not active `build/` directories: they bind omitted files and cannot certify fresh outputs. No clean end-to-end rebuild was performed for this migration; the commands below were checked against current scripts and retained successful commands. Stop at the first failure, retain logs and inspect before retrying.

## Retained inputs

Paths are relative to the restored root containing `wesnoth_client`, `wesnoth_server` and `gamedata-1.19.26`.

- All tracked client source, `engine/`, engine manifests/Gradle wrapper, native/presentation assets, tests and docs. Empty upstream scaffolding outside `engine/` is not the active source.
- `wesnoth_client/packaging/android/download/`: all23 pinned archives (313,798,831bytes).
- `build/android-icu-sources/icu4c-78.3-sources.tgz` and `build/android-layout-sources/fribidi-1.0.17.tar.xz` under the client.
- Client `build/downloads/android-ndk-r26d-linux.zip`, `build-tools_r34-linux.zip`, `platform-35_r02.zip` and SDK provenance JSON/XML.
- Client `build/android-game-gradle-cache/wrapper/dists/` and `caches/modules-2/`, including the complete Gradle8.9 distribution, `.zip.ok` marker, artifacts and metadata. Exclude lock files. These input caches total approximately256MB; daemon, transforms, `.tmp`, native and incremental caches regenerate. This minimum cache selection has not yet been verified by a complete clean build.
- **Private original signer:** `wesnoth_client/build/android-game-host-user/.android/debug.keystore` (2,618bytes). Restore before Gradle; never silently replace it.
- **Private VPS fixture:** `build/audit-startup-profile-1192621/public-build-fixture/` with public profile, certificate, public-config reference and fixture key. This is not the Windows production identity. Certificate expiry/pin checks remain mandatory.
- Exact four-file client `build/android-game-data/` stage and sibling `gamedata-1.19.26/`.
- Original guest and current account APKs plus receipts/signature reports as historical evidence. Their comparison paths are listed in the migration inventory.

The target remains x86_64/API23 for LDPlayer. Physical ARM phones are not covered.

## Environment and tool extraction

Follow the environment README to reinstall Docker and Python3.12.10 and rebuild images online. It supplies the pinned source-build process for `wesnoth_server/build/host-python-3.12.10`. Do not restore a host virtualenv as if it were portable.

After the environment phase already built the seven images, retain them and set the workspace root. Do not rebuild the same images a second time:

```bash
set -euo pipefail
workspace_root="$PWD"
docker image inspect wesnoth-server-verify:1.19.26 wesnoth-android-sdl-verify:ndk26-java21 wesnoth-text-toolchain-verify:meson1.12 >/dev/null
```

The preserved text-toolchain recipe adds gperf and Meson1.12.0. Distribution host packages may differ after image recreation; record versions again. This is not a claim that recreated images are bit-for-bit identical.

Verify the migration manifest first. Extract installers only into absent destinations:

```bash
cd "$workspace_root/wesnoth_client"
test ! -e build/toolchains/android-ndk-r26d
test ! -e build/toolchains/android-sdk/platforms/android-35
test ! -e build/toolchains/android-sdk/build-tools/34.0.0
mkdir -p build/toolchains/android-sdk/platforms build/toolchains/android-sdk/build-tools build/sdk-unpack
unzip -q build/downloads/android-ndk-r26d-linux.zip -d build/toolchains
unzip -q build/downloads/platform-35_r02.zip -d build/toolchains/android-sdk/platforms
unzip -q build/downloads/build-tools_r34-linux.zip -d build/sdk-unpack
mv build/sdk-unpack/android-14 build/toolchains/android-sdk/build-tools/34.0.0
rmdir build/sdk-unpack
```

Use `unzip` to retain executable bits/symlinks. Builders enforce NDK26.3.11579264/Clang17.0.2, SDK35 and build-tools34.0.0. No emulator is needed for VPS cross-compilation.

## Full native rebuild

From the workspace root, after Python3.12.10 and images are ready:

```bash
set -euo pipefail
workspace_root="$PWD"
client_root="$workspace_root/wesnoth_client"
python_root="$workspace_root/wesnoth_server/build/host-python-3.12.10"
test -x "$python_root/bin/python3.12"
test -s "$client_root/build/android-game-host-user/.android/debug.keystore"
core() {
  docker run --rm --network none \
    -v "$client_root:/workspace" -v "$python_root:/python312:ro" \
    -w /workspace wesnoth-server-verify:1.19.26 \
    /python312/bin/python3.12 -I -B -u "$@"
}
text() {
  docker run --rm --network none \
    -v "$client_root:/workspace" -v "$python_root:/python312:ro" \
    -w /workspace wesnoth-text-toolchain-verify:meson1.12 \
    /python312/bin/python3.12 -I -B -u "$@"
}
native_args=(--ndk /workspace/build/toolchains/android-ndk-r26d \
             --cmake /opt/build-tools/bin/cmake --ninja /opt/build-tools/bin/ninja --jobs 2)
text_args=(--ndk /workspace/build/toolchains/android-ndk-r26d --jobs 2)
core tools/build_android_media.py "${native_args[@]}"
core tools/build_android_fonts.py "${native_args[@]}"
text tools/build_android_text_base.py "${text_args[@]}"
text tools/build_android_glib_deps.py "${text_args[@]}"
text tools/build_android_glib.py "${text_args[@]}"
text tools/build_android_text_render.py "${text_args[@]}"
text tools/build_android_text_layout.py "${text_args[@]}"
core tools/build_android_icu.py "${native_args[@]}"
core tools/build_android_boost.py "${native_args[@]}"
core tools/build_android_network.py "${native_args[@]}"
core tools/build_android_engine.py "${native_args[@]}"
```

The engine has568 pinned source objects; total build-step counts vary. Earlier bootstrap/source-preparation/SDL-check APK stages are optional diagnostics, not prerequisite receipts for this current pipeline. Builders retain failures and refuse changed/unmanaged stages. Never delete an operation lock or manufacture a receipt to bypass a failure.

## Data and packaging

Verify the exact retained data stage and source tree:

```bash
docker run --rm --network none \
  -v "$workspace_root:/workspace:ro" \
  -w /workspace/wesnoth_client wesnoth-server-verify:1.19.26 \
  /workspace/wesnoth_server/build/host-python-3.12.10/bin/python3.12 -I -B -u tools/prepare_android_game_data.py --verify-only
docker run --rm --network none \
  -v "$workspace_root:/workspace:ro" \
  -w /workspace/wesnoth_client wesnoth-server-verify:1.19.26 \
  /workspace/wesnoth_server/build/host-python-3.12.10/bin/python3.12 -I -B -u tools/verify_game_data.py --data-root ../gamedata-1.19.26
```

Package a fresh base game first. The original signing key is selected with `ANDROID_USER_HOME`, as in the accepted VPS build:

```bash
cd "$workspace_root"
package() {
  docker run --rm --network none \
    -e ANDROID_USER_HOME=/workspace/build/android-game-host-user/.android \
    -v "$client_root:/workspace" -v "$python_root:/python312:ro" \
    -w /workspace wesnoth-android-sdl-verify:ndk26-java21 \
    /python312/bin/python3.12 -I -B -u "$@"
}
package_args=(--ndk /workspace/build/toolchains/android-ndk-r26d \
              --sdk /workspace/build/toolchains/android-sdk \
              --java /opt/java/openjdk/bin/java \
              --gradle-user-home /workspace/build/android-game-gradle-cache)
package tools/build_android_game.py "${package_args[@]}"
```

Before account packaging, use SDK `apksigner verify --print-certs` to compare certificate SHA256 of the rebuilt base APK with the archived original base APK (archive path in migration inventory). Certificate equality is required; APK byte equality is not. If certificates differ, stop. The account helper compares against the active base APK, so this independent archived-original comparison prevents a replacement key from becoming the new baseline.

Build current1192629 from empty account stages:

```bash
account_args=("${package_args[@]}" \
              --cmake /opt/build-tools/bin/cmake --ninja /opt/build-tools/bin/ninja --jobs 2 \
              --public-config /workspace/build/audit-startup-profile-1192621/public-build-fixture/client-public.env \
              --openssl /usr/bin/openssl)
package tools/build_android_account_game.py "${account_args[@]}"
package tools/build_android_account_game.py "${account_args[@]}" --verify-only
```

Do not pass `--prepare-update` on this fresh source-only restoration: it requires two complete prior account stages. Keep historical journals outside active build paths. After a complete current build exists, normal preserving updates resume for later releases.

The VPS fixture APK is not a Windows production APK. Windows continues using its retained local `.env`/public profile, original Windows signer and PowerShell helpers. Never replace Windows saves/runtime/signing identity with VPS fixture data.

## Optional native rendered verification

Large native renderer objects are omitted. Retain these small source recipes at their original relative paths:

1. `build/android-media-host-semantics/verify_host.py`.
2. `build/audit-team-practice-engine-20261022/build_host.py` and `host-project/CMakeLists.txt`.
3. `build/audit-emerald-preferences-1192623/render-build-commands.json` compile template.
4. `build/audit-menu-polish-1192625/render-build/{render_wesnoth,modal_dialog,gui_definition,render_tooltip}.cpp`.
5. `build/audit-court-feedback-1192629/{build_render.py,render_probe.cpp,court_mobile_workspace.hpp,run_render.py}` and reports.
6. `build/audit-citadel-ui-1192622/render-08-1280x720/bmp_png.py` for the old screenshot launcher.

After rebuilding Android media sources and the environment's account-integration image:

```bash
cd "$workspace_root"
docker run --rm --network none \
  -v "$client_root:/workspace:ro" \
  -v "$client_root/build/android-media-host-semantics:/hostcheck" \
  wesnoth-account-integration-verify:20261020 \
  python3 -u /hostcheck/verify_host.py

docker run --rm --network none \
  -v "$client_root:/client:ro" \
  -v "$client_root/build/audit-team-practice-engine-20261022:/audit" \
  wesnoth-account-integration-verify:20261020 \
  python3 -u /audit/build_host.py
```

The second builder links the first one's host Vorbis/Ogg libraries. Recompile the four generated C++ files from item4 with item3's saved compile template (substitute only `-c`/`-o`). Run item5's `build_render.py` with client mounted `/client:ro`, foundation `/audit:ro`, four-object directory `/previous:ro`, and current audit `/render`. The output is `mobile-render-engine`.

The retained `run_render.py` hardcodes the previous host root; adapt that audit-only root to the restored location, or invoke its Docker command directly. Container paths remain `/client`, `/audit`, `/gamedata`, `/build`, `/render`. Renderer variables: `SDL_VIDEODRIVER=dummy`, `SDL_RENDER_DRIVER=software`, `LD_LIBRARY_PATH=/audit/prefix/lib`, `WESNOTH_UI_ASSETS=/client/tools/native-account-game/ui-assets`. Store fresh results separately. Native Linux rendering and synthetic input do not replace actual Windows/LDPlayer/mobile testing.

Source-only Python tests may run before native compilation. MongoDB/TLS, renderer and APK integration tests require their rebuilt prerequisites. Historical PASS evidence does not certify the new VPS.

Environment smoke checks establish Python/dependency/Mongo versions and domain tests. Principal compiler/Java/Gradle/text versions are also recorded in the environment pins; the corresponding fresh builders must accept their versions. The smoke runner alone does not establish every toolchain version or a clean APK build.
