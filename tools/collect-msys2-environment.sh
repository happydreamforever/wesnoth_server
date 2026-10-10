#!/usr/bin/env bash
# Read-only helper for Collect-WindowsEnvironment.ps1. Run inside the installed
# MSYS2 root. It never updates packages, activates environments, or builds code.
set -u

run_version() {
    local executable="$1"
    shift
    if [[ ! -f "$executable" || ! -s "$executable" ]]; then
        printf '[UNKNOWN] Missing or empty: %s\n' "$executable"
        return
    fi
    printf '\n[INFO] Version probe: %s\n' "$executable"
    local result
    if [[ -x /usr/bin/timeout ]]; then
        result=$(/usr/bin/timeout 12 "$executable" "$@" 2>&1)
    else
        result=$("$executable" "$@" 2>&1)
    fi
    local code=$?
    if [[ $code -eq 0 ]]; then
        printf '[PASS] %s\n' "$result"
    else
        printf '[UNKNOWN] Exit %s: %s\n' "$code" "$result"
    fi
}

printf '[INFO] MSYS2 system\n'
run_version /usr/bin/uname.exe -a
run_version /usr/bin/bash.exe --version
run_version /usr/bin/pacman.exe --version

printf '\n[INFO] Installed MSYS2 packages (pacman -Q; local database only)\n'
if [[ -s /usr/bin/pacman.exe ]]; then
    if /usr/bin/pacman.exe -Q; then
        printf '[PASS] Installed package inventory complete.\n'
    else
        printf '[UNKNOWN] pacman could not read its installed package database.\n'
    fi
else
    printf '[BLOCKED] pacman.exe is missing or empty.\n'
fi

for prefix in /usr /mingw64 /ucrt64 /clang64; do
    [[ -d "$prefix/bin" ]] || continue
    printf '\n[INFO] Tool prefix: %s\n' "$prefix"
    for compiler in gcc g++ clang clang++; do
        [[ -e "$prefix/bin/$compiler.exe" ]] && run_version "$prefix/bin/$compiler.exe" --version
    done
    for tool in git python python3 cmake ninja make pkg-config; do
        [[ -e "$prefix/bin/$tool.exe" ]] && run_version "$prefix/bin/$tool.exe" --version
    done
    if [[ -s "$prefix/bin/python.exe" ]]; then
        # Module version does not load SConstruct or perform a build.
        run_version "$prefix/bin/python.exe" -m SCons --version
    fi
done

printf '\n[INFO] MSYS2 helper finished; no packages were installed or changed.\n'
