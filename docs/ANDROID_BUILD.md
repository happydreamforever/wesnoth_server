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

## First native build and device checkpoint

New bootstrap tools build verified bzip2 1.0.8 and a small Android x86_64/API23 C++ executable, using the official NDK CMake toolchain with the existing native CMake/Ninja versions. The executable checks compression through bzip2 and Android system zlib, plus C++ STL/exception support. Artifact/receipt checks precede an explicit-serial ADB test on LDPlayer. Existing engine and prepared Gradle source are unchanged. This is a first real native dependency build and runtime test, not an APK, graphics/SDL test or LAN game.

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

## Remaining implementation and verification

1. Run the offline native bootstrap build and LDPlayer test in NEXT_TEST.md. Tool/cache preparation and all native source archive hashes are already verified; preserve the existing installations and caches.
2. Port MSYS2/native dependency commands and SCons Android tool selection to the Windows NDK host. Separate native API23 from Java SDK35; ensure all paths/quoting work and prohibit network downloads during offline builds. Google's [NDK guidance](https://developer.android.com/ndk/guides/other_build_systems) cautions about Autoconf on Windows, so this requires actual cross-build validation.
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
