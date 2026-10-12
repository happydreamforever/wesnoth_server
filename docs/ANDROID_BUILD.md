# Android build checkpoint

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

Build-WindowsSdlCheck.ps1 uses the confirmed Windows paths and reports the selected SDK package revisions. Test-AndroidSdlCheck.ps1 installs only org.wesnoth.offlinecheck, launches with a unique run identifier, reads process-specific logs and requires both first-frame and input-response markers. It leaves the app open for the user's visual click/counter/color/animation confirmation. See NEXT_TEST.md for exact commands. No actual SDL display/input success on Windows/LDPlayer is claimed until that result returns.

The native/Java arrangement follows the [SDL Android port](https://github.com/libsdl-org/SDL/blob/release-3.4.2/docs/README-android.md); native source comes from the existing pinned archive. The latest SDL wiki may describe newer NDK defaults, so it does not silently change this project's proven r26d profile.

## Reproduce the SDL APK build on the VPS

The complete SDL APK build passed with Docker networking disabled. Fifteen builder tests, seventeen wrapper fixtures and a real-APK/receipt integration with mocked ADB passed. The resulting signed debug APK is 3,483,756 bytes. These checks establish compilation, packaging, signature and helper control flow; the user's LDPlayer graphics/input result remains pending.

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

## Remaining implementation and verification

1. Run the offline SDL APK build/install/graphics/input test in NEXT_TEST.md. The native bootstrap has already passed on Windows and LDPlayer; preserve the existing installations, source stage and caches.
2. Port the remaining native dependencies and SCons Android tool selection to the Windows NDK host. Pango 1.50.14 requires FriBidi >=1.0.6, absent from the current 23-archive cache; its wrap points to Git master. Pin and provision that source before an offline text-stack build, rather than allowing a Meson download. GLib's gvdb sources are already bundled.  Separate native API23 from Java SDK35; ensure all paths/quoting work and prohibit network downloads during offline builds. Google's [NDK guidance](https://developer.android.com/ndk/guides/other_build_systems) cautions about Autoconf on Windows, so this requires actual cross-build validation.
3. Build the x86_64 dependency libraries and libmain.so, supply matching SDL Java sources, validate ABI/nonempty outputs, then permit Gradle packaging with the complete offline cache. Windows build and matching VPS verification remain required; current source-stage tests are not compilation tests.
4. Deliver game data and implement/test asset import/OBB behavior. Install a nonempty debug APK to the known device serial, test local single-player and a LAN turn against the verified server, then implement local MongoDB persistence. Neither successful ADB nor the server smoke test establishes those milestones.

Current user commands and expected outputs are in NEXT_TEST.md. No APK or OBB is ready in this checkpoint.


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
