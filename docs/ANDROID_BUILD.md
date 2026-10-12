# Android build checkpoint

Current checkpoint (2026-10-12): Windows font compilation and actual LDPlayer shaping/rasterization now pass; see the latest BASELINE.md evidence. The first MSYS diagnostic confirmed tool versions but stopped at an interpreter path comparison before compilation. Pull and rerun the corrected Test-WindowsAndroidTextToolchain.ps1 from NEXT_TEST.md; it verifies executable aliases and actual Python/Meson runtime identity before the Make/pkg-config/native-NDK path check. Completed stages below are retained as reproduction history.

The first emulator target is x86_64 on the user's verified LDPlayer Android9/API28. The native minimum API remains23. Compile/target SDK35 is a build setting and does not require the emulator to run Android35. The ARM entries in the reported ABI list and libnb.so identify advertised translation support; ARM APK execution has not been tested. A physical-phone ABI will be selected from that phone's actual report later.

## Selected inputs

The machine-readable profile lives in client tools/android-build-profile.json. These are selected project inputs; their installation and full operation on both hosts are not yet verified.

| Component | Selected value | Reason/status |
| --- | --- | --- |
| Engine/data core | Wesnoth1.19.26 | Restored engine commit75c84d2ed344b954d1fd308e588dfe13aef53b20; game-data delivery still pending |
| First APK ABI | x86_64 | Actual LDPlayer primary ABI |
| Native/minimum API |23 | Upstream minimum; compatible with actual device API28 |
| Java compile/target SDK |35 | Upstream; installed Windows package metadata observed |
| SDK build tools |34.0.0 | AGP8.7 default and existing upstream tool path; observed installed |
| NDK |26.3.11579264 | Installed and verified on Windows; clang 17.0.2 runs; existing 30beta retained |
| Gradle / AGP |8.9 /8.7.3 | Windows online and offline Java/AAPT2 resolution passed; 24 unique artifact files |
| Java |21 (Windows21.0.9) | Existing Android Studio JBR; compatible with Gradle8.9 |
| SCons |4.11.0 | Private verified wheel prepared and runnable through MSYS Python 3.12.13 |

[AGP8.7 compatibility](https://developer.android.com/build/releases/agp-8-7-0-release-notes), [Gradle Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html), [SCons4.11](https://scons.org/scons-4110-is-available.html). The Gradle8.9 distribution checksum is pinned from the [official checksum](https://services.gradle.org/distributions/gradle-8.9-bin.zip.sha256). The server continues to use its independently verified Windows compiler/dependency set; this Android profile does not alter it.

## Delivered preparation

client tools/prepare_android_source.py verifies the pinned engine manifest and1591 source-file byte hashes, ignoring executable modes. It copies only those files into ignored build/android-source, applies reviewed overlays there and records exact provenance. Original engine/, local edits and empty legacy files are preserved. The generated Gradle project selects the profile and x86_64; a staged Lua check accepts the already-flattened verified Lua source instead of demanding missing submodule .git metadata. Repeating preparation on an unchanged stage is safe; edited, incomplete or unrelated destinations are refused. No force-overwrite option is provided.

Actual Windows preparation now passed with all 1,591 source hashes matching and exit 0 at `D:\Test\wesnoth-setup\wesnoth_client\build\android-source`. Keep that stage; the reporting fix does not alter its generator or profile. This result verifies source bytes regardless of executable modes, not staged Git changes or an Android build.

The staged Gradle native tasks and preBuild explicitly stop while native integration is incomplete. The tool produces source preparation, not a buildable APK. Do not run the original Linux dependency scripts on Windows merely because staging succeeded; they contain downloads, Linux host paths, mixed NDK assumptions and host-tool behavior that still need adapting.

client tools/Test-WindowsAndroidPrerequisites.ps1 writes client diagnostics/android-prerequisites-*.txt. It checks manifest integrity, the actual selected compiler/Java, required SDK files, MSYS tooling/SCons, specific cache-file presence and native archive identities. It never downloads or starts Gradle, ADB, a game or a database. Reports omit .env, Git remotes and full environment dumps. Local paths appear. Source differences are reported for review; no repair/reset is performed.

The repaired prerequisite helper completed on Windows at client 29c1d42/server 848f832. Its report `android-prerequisites-20261011-210739-944-b8ec9ddce151499184b2ffbddb41ca03.txt` confirms Java/javac 21.0.9, selected SDK files, all 15 MSYS tools, MSYS Python 3.12.13, all source hashes and all 23 archive hashes. Twelve BLOCKED entries identify missing stable NDK inputs, SCons, selected Gradle launcher and AndroidX core/documentfile AARs. The report saved without retries or fallback; the logging repair is verified for this Windows run.

New `Prepare-WindowsAndroidTools.ps1 -Download` is a connected preparation step: use the existing SDK manager for only NDK 26.3.11579264; verify/reuse the source stage; prepare the published SCons 4.11.0 universal wheel in a project-private directory; then invoke the preserved Gradle wrapper JAR to load AGP and resolve debug Java artifacts plus matching Windows AAPT2. Repeat that resolution with --offline. The SCons package is pinned by published byte size/SHA256 in android-scons-package.json and remains reusable offline; its runner verifies installed contents before every version/run. The prerequisite helper .3 uses the private runner through MSYS Python, not a global module.

The Windows retry at client fccfc96/server 9935a53 completed: NDK26.3 installed, private SCons prepared, online Gradle resolution passed in 39m23s and offline resolution passed in 13s. The two sets of 24 artifact hashes match exactly. Prerequisite .3 then completed with zero blockers, exit 0, and saved android-prerequisites-20261011-225623-901-ed23df5cdee7479fb5831ebd8f923fd2.txt. The connection-reset retry is finished; its original cause remains unknown. These results validate selected inputs and cache resolution, not full APK readiness.

No wrapper .bat is present upstream, so setup explicitly runs org.gradle.wrapper.GradleWrapperMain through the selected Java executable. A separate init script registers only the cache-resolution task. It downloads actual files rather than only reporting a dependency tree, keeps the project cache outside the preserved stage, and leaves native/preBuild guards intact. Cache resolution does not prove that every artifact required by a later APK build is prepared.

The VPS retains all23 upstream-named native source archives in original client packaging/android/download/, totaling313,798,831bytes. Their tar member traversals succeeded and compressed byte hashes are recorded in tools/android-native-archives.json. These hashes establish parity with the audited VPS cache, not publisher signature/checksum verification or successful compilation. Windows now verified all 23 source archive sizes and SHA256 values against these copies. No usable native .a/.so outputs were found in the original client tree, and no binary archives are committed to Git.

## Completed native build and device checkpoint

The bootstrap tools build verified bzip2 1.0.8 and a small Android x86_64/API23 C++ executable, using the official NDK CMake toolchain with the existing native CMake/Ninja versions. The executable checks compression through bzip2 and Android system zlib, plus C++ STL/exception support. Artifact/receipt checks precede an explicit-serial ADB test on LDPlayer. Existing engine and prepared Gradle source are unchanged. This is a first real native dependency build and runtime test, not an APK, graphics/SDL test or LAN game.

Google documents [CMake as a supported NDK build route](https://developer.android.com/ndk/guides/cmake). The remaining upstream dependencies mix Autoconf, Meson, Boost and SDL build systems; [Google cautions that Autoconf projects are generally not buildable on Windows](https://developer.android.com/ndk/guides/other_build_systems#autoconf). Therefore full Windows native integration remains substantive work. Future choices may include portable recipes or a reproducible target-library bundle built on the VPS with the same NDK; neither approach is claimed completed or selected for all remaining libraries in this checkpoint.

## VPS native build verification

The real bootstrap cross-build passed using Linux NDK r26d/clang 17.0.2 and CMake 4.3.0 with Docker networking disabled. The verification container reports Ninja 1.13.2.git.kitware.jobserver-pipe-1 and Python 3.13.5; Windows reports plain Ninja 1.13.2 and Python 3.14.3. The build records full versions. This aligns the selected NDK/compiler release and CMake while retaining explicit host/package differences.

With the already prepared Linux NDK under ignored build/toolchains/android-ndk-r26d and the existing verification image, run from the client checkout:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  wesnoth-server-verify:1.19.26 \
  python3 -I tools/build_android_bootstrap.py \
    --ndk /workspace/build/toolchains/android-ndk-r26d \
    --cmake /opt/build-tools/bin/cmake \
    --ninja /opt/build-tools/bin/ninja --jobs 2
```

The tool validates seven x86_64 bzip2 objects, the executable's Android API23 note and linker64 interpreter, expected dynamic libraries and absence of host RPATH. It records the current input and output hashes in receipt.json. A receipt is build evidence; only the subsequent LDPlayer test establishes device execution. No Docker or Linux NDK installation is needed on Windows.

For changes to these helpers, run `python3 tests/test_android_bootstrap.py` and `python3 tests/test_android_bootstrap_windows.py --pwsh /tmp/wesnoth-audit-pwsh/pwsh` on the VPS. The latter uses the locally available Linux PowerShell to simulate Windows tools and ADB. Nineteen builder tests and 17 wrapper fixtures passed; the wrapper also accepted the real cross-build receipt/artifacts with ADB simulated. Neither test replaces actual Windows/LDPlayer evidence.

## SDL graphics/input APK checkpoint

Actual Windows bootstrap compilation and LDPlayer execution now passed, including bzip2/system-zlib roundtrips, C++ STL and exception unwinding. The effective zlib header version is 1.2.8 for native target API23; the device reports runtime 1.2.11. The NDK applies that header compatibility override deliberately, and the roundtrip passed. Keep the successful bootstrap and original game stage.

The new tools/build_android_sdl_check.py uses the verified cached SDL3-3.4.2 archive, which contains 2,176 regular files and eleven Java glue sources matching the restored engine byte for byte. It creates a separate managed build/android-sdl-apk project and compiles shared SDL3/main libraries with NDK r26d, x86_64/API23 and shared libc++. A simple SDL callback program uses the built-in debug font, so this checkpoint needs no SDL_image, SDL_ttf or game assets. It explicitly selects the OpenGL ES 2 renderer, draws a landscape target/animation and reports input after presentation. These libraries are a reusable foundation, but the probe does not compile the game engine.

The isolated Gradle project uses the existing 8.9/AGP 8.7.3, SDK35/build-tools34 and Java21. It needs no AndroidX artifacts. Gradle runs with --offline; the exact completed wrapper cache must exist before invoking Java, and SDK auto-downloads are disabled. The builder preserves the old managed source before regenerating its own project files, validates native ELF/API/dependencies, compares the packaged three-library payload, checks package/SDK/ABI metadata with AAPT2 and verifies the debug signature with apksigner. Failed builds do not leave a successful APK receipt. Project and artifact hashes gate installation.

Build-WindowsSdlCheck.ps1 uses the confirmed Windows paths and reports the selected SDK package revisions. Test-AndroidSdlCheck.ps1 installs only org.wesnoth.offlinecheck, launches with a unique run identifier, reads process-specific logs and requires both first-frame and input-response markers. It leaves the app open for the user's visual click/counter/color/animation confirmation. The Windows build and actual LDPlayer READY/INPUT automation now passed in attachment75f03ca5. Manual clicks, changing counter/color and moving animation are also confirmed; the latest NEXT_TEST.md advances to the media libraries.

The native/Java arrangement follows the [SDL Android port](https://github.com/libsdl-org/SDL/blob/release-3.4.2/docs/README-android.md); native source comes from the existing pinned archive. The latest SDL wiki may describe newer NDK defaults, so it does not silently change this project's proven r26d profile.

## Reproduce the SDL APK build on the VPS

The complete SDL APK build passed with Docker networking disabled. Fifteen builder tests, seventeen wrapper fixtures and a real-APK/receipt integration with mocked ADB passed. The resulting signed debug APK is 3,483,756 bytes. Those VPS checks establish compilation, packaging, signature and helper control flow. The subsequent Windows log separately establishes real APK installation and LDPlayer graphics/input automation; it also confirms SDK35 revision2/build-tools34.0.0 parity.

The combined tools/Dockerfile.android-sdl-verify reuses the existing server verification image and Java/Gradle image. For the current prepared VPS, run from the client repository:

```sh
docker build --network none -t wesnoth-android-sdl-verify:ndk26-java21 \
  -f tools/Dockerfile.android-sdl-verify tools
docker run --rm --network none \
  -v "$PWD:/workspace" -v /tmp/wesnoth-gradle-cache-check:/cache \
  -w /workspace wesnoth-android-sdl-verify:ndk26-java21 \
  python3 -I tools/build_android_sdl_check.py \
    --ndk /workspace/build/toolchains/android-ndk-r26d \
    --cmake /opt/build-tools/bin/cmake --ninja /opt/build-tools/bin/ninja \
    --java /opt/java/openjdk/bin/java \
    --sdk /workspace/build/toolchains/android-sdk \
    --gradle-user-home /cache/userhome --jobs 2
```

This command assumes the recorded Linux NDK/SDK35/build-tools34 and completed Gradle/AAPT2 caches have already been prepared. Exact package provenance is in BASELINE.md. It is not a bootstrap command for an empty machine. Windows uses its existing installations and does not need Docker or these Linux downloads. The script always invokes Gradle --offline and emits a successful receipt only after APK/signature/content validation.

For relevant helper changes, run `python3 tests/test_android_sdl_check.py` and `python3 tests/test_android_sdl_check_windows.py --pwsh /tmp/wesnoth-audit-pwsh/pwsh`. The PowerShell fixtures simulate Windows/ADB and cannot establish graphics on a device. Keep the original game-stage guards intact until the actual game native build is ready.

## Reusable media dependency build

The next separate stage, build/android-media, builds the seven already pinned source archives for libpng1.6.39, libwebp1.4.0, libogg1.3.5, libvorbis1.3.7, SDL3.4.2, SDL3_image3.4.0 and SDL3_mixer3.2.0. Headers, library files and package metadata are installed under prefix for the future game build. The codec libraries use PIC static archives, while SDL and its image/mixer extensions are shared. SDL_image's bundled stb implementation handles JPEG, so no uncached libjpeg package is added. PNG/WebP and Ogg Vorbis support use the explicitly built libraries. Optional codecs without prepared sources are disabled.

The build uses the existing native CMake/Ninja and NDK r26d toolchain, explicit x86_64/API23 and shared libc++. Older package CMake files use a policy compatibility floor of3.5 with the installed CMake4.3.0; the compiler and selected tool versions are unchanged. Packages are configured, built and installed sequentially so dependency discovery uses the completed Android prefix. The recipe follows the supported [NDK CMake toolchain](https://developer.android.com/ndk/guides/cmake), with options reviewed against the pinned [SDL_image3.4.0 build](https://github.com/libsdl-org/SDL_image/blob/release-3.4.0/CMakeLists.txt) and [SDL_mixer3.2.0 build](https://github.com/libsdl-org/SDL_mixer/blob/release-3.2.0/CMakeLists.txt).

The native probe generates its own small image/audio samples, decodes them and checks the results. Its mixer renders into memory without opening an audio device. It does not use game assets, launch an APK or establish audible playback. A successful Linux cross-build establishes compilation and linkage; the user's LDPlayer run is required for codec runtime evidence. The new prefix does not replace engine/, build/android-source, build/android-native-bootstrap or build/android-sdl-apk.

### Reproduce the media cross-build on the prepared VPS

From the client checkout, use the existing compiler image and ignored Linux NDK. This is a reproduction command for the already prepared VPS, not a Windows prerequisite:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  wesnoth-server-verify:1.19.26 \
  python3 -I tools/build_android_media.py \
    --ndk /workspace/build/toolchains/android-ndk-r26d \
    --cmake /opt/build-tools/bin/cmake \
    --ninja /opt/build-tools/bin/ninja --jobs 2
```

The builder verifies seven archive hashes, safely stages their regular source files and retains their license inputs. Only the inspected unused Xcode subtree in the SDL image/mixer archives is excluded. Known Unix libpng aliases become regular files; host-only libpng shell helpers are omitted. Package metadata uses a relative install prefix and Android system link names, with no absolute path into the selected source/build/NDK tree. The prefix is independently recorded and protected against changed, missing or extra files on subsequent runs. An interrupted installation is reported for review instead of overwriting unknown work.

A success receipt requires nine static libraries containing x86_64 ELF objects, the selected public headers, four shared libraries, and the Android API23 codec executable. It inventories every installed file and records the seven current build inputs. Device execution is explicitly false in this build receipt. Test-AndroidMedia.ps1 validates the receipt and full prefix before sending its five-file runtime payload to the selected device.

The final Android cross-build passed with networking disabled:188 installed files,12 static archives with245 validated x86_64 objects, and the five-file runtime payload. Eighteen builder tests and21 Windows-helper fixtures passed. A separate offline Linux execution of the same codec algorithms also passed all six markers. Attachment 98ca3099 now also confirms actual Windows compilation and LDPlayer execution of all six markers, ending with ANDROID MEDIA TEST PASSED. This completes the media checkpoint; audible hardware output remains untested. For relevant changes, use `python3 tests/test_android_media.py` and `python3 tests/test_android_media_windows.py --pwsh /tmp/wesnoth-audit-pwsh/pwsh` on the VPS. The latter uses mocked Windows processes/ADB.

## Offline game-data copy verification

The selected asset source is the sibling folder `D:\Test\wesnoth-setup\gamedata-1.19.26`. Attachment d4ab7e23 confirms this Windows folder passed the complete reference check. For relevant future data changes, run `tools/Test-WindowsGameData.ps1` from the client checkout with the installed native Python 3.14.3; no compiler, ADB, server or internet is required. The helper calls `verify_game_data.py` with isolated, unbuffered Python and bytecode writing disabled. It hashes every file and compares against `tools/gamedata-1.19.26.reference.json`. No archive, OBB, receipt or transcript is generated. Hash checking reads about 726 MB and prints progress; let it finish.

Success means 26,748 files, 726,207,542 bytes and 13 expected empty files match the VPS copy. File names and bytes must match exactly, including hidden files and original line endings. Changes are reported by parent directory; preserve the copy and send the output before attempting repairs. This manifest is a copy-integrity reference, not a new source of game assets or a game installation. The current SDL check app does not load these assets. OBB support and Android asset import are still pending.

For relevant verifier changes, run `python3 -B tests/test_game_data.py`. Reproduce the full VPS check from the client checkout with `python3 -I -B -u tools/verify_game_data.py --data-root ../gamedata-1.19.26`. The expected tree SHA256 is recorded in BASELINE.md; never rebaseline it merely to accept a changed copy.

## FreeType/HarfBuzz font foundation

The next independent prefix, `build/android-fonts/prefix`, provides FreeType 2.13.0 and HarfBuzz 7.1.0 static libraries, development headers, package metadata and license notices. Both exact source archives are already pinned in android-native-archives.json and present in the Windows cache. The builder uses the existing native CMake/Ninja and NDK r26d, x86_64/API23, PIC and shared libc++. It does not read game data or download packages. The completed bootstrap, SDL and media output directories are preserved.

FreeType disables the optional HarfBuzz auto-hint dependency, as the preserved upstream Android configuration does, so it can build first. It uses bundled zlib and disables external PNG, bzip2 and Brotli helpers for this font foundation. HarfBuzz enables its FreeType bridge and disables unrelated optional integrations. Latin/OpenType and explicit-direction Arabic shaping do not require GLib, FriBidi, Pango or an Android window. Full paragraph layout, bidirectional paragraph analysis, fallback selection and the remaining text stack are subsequent work; this test does not stand in for them.

The native probe consumes Lato-Regular.ttf and DejaVuSans.ttf from a runtime directory. The Windows device helper checks their exact sizes/hashes plus fonts/COPYING against `tools/native-fonts/assets.json`, which is itself included in the successful build receipt's nine source hashes. The selected files come directly from the verified sibling data folder. Only the two fonts, their notice, the test and libc++ are transferred to a unique `/data/local/tmp/wesnoth-fonts-check/` directory. No game-data archive, APK, OBB or installed application data is changed.

The probe checks actual library versions and font loading, Latin ligature substitution with the feature enabled/disabled, contextual Arabic shaping with explicit direction, and nonempty glyph rasterization. Output remains in memory. Build receipt validation covers the complete prefix and x86_64 library members plus Android executable/runtime metadata. Existing changed files are preserved and a failed rebuild cannot retain a successful receipt for that attempted build. Windows commands and exact output markers are in NEXT_TEST.md.

For relevant helper changes, use `python3 -B tests/test_android_fonts.py` and `python3 -B tests/test_android_fonts_windows.py --pwsh /tmp/wesnoth-audit-pwsh/pwsh`. Windows-wrapper fixtures simulate tools and ADB; only the user's LDPlayer output can establish Android execution. Reproduce the offline cross-build from the client checkout on the prepared VPS:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  wesnoth-server-verify:1.19.26 \
  python3 -I tools/build_android_fonts.py \
    --ndk /workspace/build/toolchains/android-ndk-r26d \
    --cmake /opt/build-tools/bin/cmake \
    --ninja /opt/build-tools/bin/ninja --jobs 2
```

This uses the already prepared Linux tools and caches; Windows uses its recorded installations and needs no Docker setup. The offline cross-build, unchanged rebuild and consumer build from a relocated prefix with spaces passed: 108 installed files and 43 validated static-library objects. Fourteen builder tests, 27 PowerShell fixtures and a real-prefix integration with mocked ADB passed. A separate Linux execution using the real fonts also passed all shaping/raster checks and negative cases. Windows font compilation and LDPlayer execution remain pending; see BASELINE.md for evidence and limits.

## Remaining implementation and verification

1. The native bootstrap, SDL APK graphics/input, reusable media build/codec execution and full Windows data parity have passed. Build the font prefix and run the real-font native probe using NEXT_TEST.md; preserve the successful prior checkpoints.
2. Port the remaining native dependencies and SCons Android tool selection to the Windows NDK host. Pango 1.50.14 requires FriBidi >=1.0.6, absent from the current 23-archive cache; its wrap points to Git master. Pin and provision that source before an offline text-stack build, rather than allowing a Meson download. GLib's gvdb sources are already bundled.  Separate native API23 from Java SDK35; ensure all paths/quoting work and prohibit network downloads during offline builds. Google's [NDK guidance](https://developer.android.com/ndk/guides/other_build_systems) cautions about Autoconf on Windows, so this requires actual cross-build validation.
3. Build the x86_64 dependency libraries and libmain.so, supply matching SDL Java sources, validate ABI/nonempty outputs, then permit Gradle packaging with the complete offline cache. Windows build and matching VPS verification remain required; current source-stage tests are not compilation tests.
4. The copied Windows data folder passed full parity verification. Implement/test Android asset import/OBB behavior. Install a nonempty debug APK to the known device serial, test local single-player and a LAN turn against the verified server, then implement local MongoDB persistence. Neither successful ADB nor the server smoke test establishes those milestones.

Current user commands and expected outputs are in NEXT_TEST.md. The SDL diagnostic APK is verified; the actual Wesnoth game APK and OBB integration remain pending.


## VPS cache verification

The real generated project passed dependency resolution with Gradle 8.9, AGP 8.7.3 and Java 21.0.9 while Docker networking was disabled and source was mounted read-only. This matches Windows's Java release number, with Linux Temurin versus Windows JBR still differing. The check resolved 24 unique Java/AAPT2 files and did not compile native code or produce an APK. The image pins official Gradle and Temurin digests in client tools/Dockerfile.android-cache-verify.

For future relevant cache-task changes, build the verification image while connected, prepare its ignored cache once using the same task without --offline and without --network none, then use this offline check from the client checkout:

```sh
docker build -t wesnoth-android-cache-verify:8.9-java21.0.9 -f tools/Dockerfile.android-cache-verify tools
mkdir -p build/gradle-verification
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/work:ro" -v "$PWD/build/gradle-verification:/cache" \
  -w /work/build/android-source/packaging/android \
  wesnoth-android-cache-verify:8.9-java21.0.9 \
  gradle --no-daemon --console=plain --offline --project-cache-dir /cache/project \
  --init-script /work/tools/android-cache.init.gradle :wesnothResolveAndroidDependencies
```

The image build and initial dependency preparation need connectivity. The final command alone tests reuse with network disabled. No Docker installation is requested on Windows. For focused helper regressions on the VPS, run tests/test_prepare_scons.py, tests/test_prepare_windows_android_tools.py and tests/test_windows_android_prerequisites.py (the latter two take --pwsh pointing to the available Linux PowerShell). Their mocked Windows processes test arguments and failure handling; they do not replace the user's Windows run.

## Remaining text library build path

The cached sources require mixed build systems: libiconv1.17, gettext-runtime0.21.1, libffi3.4.4 and Cairo1.16.0 use Autotools; Pixman0.42.2, GLib2.82.1, Fontconfig2.17.1 and Pango1.50.14 offer Meson. Fontconfig requires Meson>=1.6.1 and host gperf. The earlier complete Windows collector records installed Meson1.12.0/gperf3.3, and actual MSYS Make4.4.1/pkg-config3.0.5/Python3.12.13/Ninja1.13.2 executions. Active wrapper-selected Autotools versions and the native Windows NDK bridge need the focused check. Release-generated configure scripts avoid treating every regeneration utility as mandatory now.

Test-WindowsAndroidTextToolchain.ps1 runs check_android_text_toolchain.sh with a fresh temporary scratch directory. It reports core tools and optional generators, checks that selected MSYS Python imports the same Meson version, then compiles an Android x86_64/API23 object using an isolated temporary .pc header path containing spaces, archives it and verifies ELF metadata. There are no downloads, installs, persistent environment changes, ADB calls or changes to completed output stages. This proves that narrow bridge only; it does not prove a whole Autoconf or Meson package builds on Windows.

The proposed next reusable package stage is libiconv/Pixman. GLib also needs PCRE2, libffi and real libintl even with NLS disabled; Cairo/Pango need Fontconfig/Expat, existing FreeType/HarfBuzz/media outputs, and a pinned FriBidi source not present in the current 23-archive cache. ICU is a separate missing source/backend decision for Boost.Locale. Provision future inputs separately without changing the completed stages' manifests/receipts unnecessarily. All dependency downloads must happen during explicit preparation, never during offline build/run.

The bridge uses the [NDK documented direct clang --target invocation](https://developer.android.com/ndk/guides/other_build_systems#overview) and the future recipes must isolate host/target discovery through [Meson's cross-build configuration](https://mesonbuild.com/Cross-compilation.html). The NDK documentation cautions that Autoconf projects are generally not buildable on Windows; a successful small bridge cannot override that limitation for untested packages. Keep the existing Windows tools until actual package evidence supports the next implementation choice.

### Verification of the diagnostic

Eighteen shell fixtures (real Make/pkg-config, controlled NDK) and ten PowerShell wrapper fixtures pass. A separate real NDK r26d compile/archive run passes with Docker networking disabled and a path containing spaces. These are Linux checks; the Windows MSYS/native boundary remains the user's next test. Host package differences are listed in BASELINE.md.

On the prepared VPS, run the shell fixtures from the client checkout:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace wesnoth-text-toolchain-verify:meson1.12 \
  python3 -B tests/test_android_text_toolchain.py
python3 tests/test_android_text_toolchain_windows.py \
  --pwsh /tmp/wesnoth-audit-pwsh/pwsh
```

The VPS-only verification image extends wesnoth-server-verify:1.19.26 with host gperf3.2.1 and Meson1.12.0 prepared online before these offline checks. Its temporary recipe and preparation log remain under ignored build/Dockerfile.text-toolchain-verify and build/text-toolchain-image.log. Windows uses its existing MSYS installation and needs no Docker/Linux tools.

### Windows interpreter alias correction

The first actual Windows diagnostic confirmed all listed versions, including MSYS Python3.12.13/Meson1.12.0, but rejected their binding because realpath strings differed. Compiler/archive execution was skipped. The helper now accepts actual file identity or byte-identical same-directory copies and additionally compares the shebang interpreter runtime/module identity with the selected Python. It prints both paths on success or failure. Twenty-four shell fixtures, including copied/hardlinked alias and genuine mismatch regressions, and a real network-disabled Linux NDK compile/archive run pass. Windows rerun remains pending; see NEXT_TEST.md. No Windows package changes are required by this correction.
