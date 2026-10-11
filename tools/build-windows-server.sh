#!/usr/bin/env bash
# Invoked by Build-WindowsServer.ps1 inside the existing MSYS2 installation.
set -euo pipefail
trap 'rc=$?; printf "\nServer build failed at line %s (exit %s). Keep this log.\n" "$LINENO" "$rc" >&2; exit "$rc"' ERR

if [[ $# != 4 ]]; then
    printf 'Usage: %s WINDOWS_CMAKE WINDOWS_NINJA BUILD_TYPE JOBS\n' "$0" >&2
    exit 2
fi
cmake_bin=$(/usr/bin/cygpath -u "$1")
ninja_bin=$(/usr/bin/cygpath -u "$2")
build_type=$3
jobs=$4
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_root="$repo_root/build/windows-mingw64"

# Git and shell utilities use MSYS2. Compiler, headers and linked libraries use
# MINGW64 only. Ninja is a separate native build tool and supplies no libraries.
export MSYSTEM=MINGW64 MINGW_PREFIX=/mingw64
export PATH="/mingw64/bin:/usr/bin:$PATH"
for binary in "$cmake_bin" "$ninja_bin" /mingw64/bin/gcc.exe /mingw64/bin/g++.exe /mingw64/bin/windres.exe; do
    if [[ ! -s "$binary" || ! -x "$binary" ]]; then
        printf 'Missing or empty required tool: %s\n' "$binary" >&2
        exit 2
    fi
done
case "$build_type" in Release|Debug|RelWithDebInfo) ;; *) printf 'Invalid build type.\n' >&2; exit 2 ;; esac
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { printf 'Jobs must be a positive integer.\n' >&2; exit 2; }
[[ "$('/mingw64/bin/g++.exe' -dumpmachine)" == x86_64-w64-mingw32 ]] || {
    printf 'The selected compiler is not the expected x86_64 MinGW compiler.\n' >&2; exit 2;
}
printf 'Source: %s\nBuild: %s\n' "$repo_root" "$build_root"
"$cmake_bin" --version
"$ninja_bin" --version
/mingw64/bin/g++.exe --version
/usr/bin/pacman -Q mingw-w64-x86_64-gcc mingw-w64-x86_64-boost \
    mingw-w64-x86_64-openssl mingw-w64-x86_64-icu \
    mingw-w64-x86_64-zlib mingw-w64-x86_64-bzip2

prefix_win=$(/usr/bin/cygpath -am /mingw64)
repo_win=$(/usr/bin/cygpath -am "$repo_root")
build_win=$(/usr/bin/cygpath -am "$build_root")
ninja_win=$(/usr/bin/cygpath -am "$ninja_bin")
printf 'Using MINGW64 compiler and dependencies from %s\n' "$prefix_win"
# All path arguments below are already Windows paths. Avoid MSYS argument
# rewriting of semicolons or -D values passed to native CMake.
export MSYS2_ARG_CONV_EXCL='*'
"$cmake_bin" -S "$repo_win" -B "$build_win" -G Ninja \
    "-DCMAKE_BUILD_TYPE=$build_type" \
    "-DCMAKE_MAKE_PROGRAM=$ninja_win" \
    "-DCMAKE_C_COMPILER=$prefix_win/bin/gcc.exe" \
    "-DCMAKE_CXX_COMPILER=$prefix_win/bin/g++.exe" \
    "-DCMAKE_RC_COMPILER=$prefix_win/bin/windres.exe" \
    "-DCMAKE_PREFIX_PATH=$prefix_win" \
    "-DBoost_ROOT=$prefix_win" "-DOPENSSL_ROOT_DIR=$prefix_win" "-DICU_ROOT=$prefix_win"
"$cmake_bin" --build "$build_win" --parallel "$jobs"
"$build_root/bin/wesnothd.exe" --version
printf '\nBUILD COMPLETE: %s/bin/wesnothd.exe\n' "$build_root"
printf 'Next: run tools/Run-WindowsServer.ps1, then test the local protocol.\n'
