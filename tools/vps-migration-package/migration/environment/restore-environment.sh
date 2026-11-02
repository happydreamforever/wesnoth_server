#!/usr/bin/env bash
# Rebuild the VPS verification tools. Never initializes a game database.
set -euo pipefail
migration_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
workspace=''
phase=''
jobs=4
with_wine=false
dry_run=false
while (($#)); do
    case "$1" in
        --workspace) workspace=${2:?Missing workspace}; shift 2 ;;
        --phase) phase=${2:?Missing phase}; shift 2 ;;
        --jobs) jobs=${2:?Missing job count}; shift 2 ;;
        --with-wine) with_wine=true; shift ;;
        --dry-run) dry_run=true; shift ;;
        *) printf 'Usage: %s --workspace /absolute/workspace --phase images|python|verify|all [--with-wine] [--jobs 4] [--dry-run]\n' "$0" >&2; exit 2 ;;
    esac
done
[[ "$workspace" = /* && -d "$workspace/wesnoth_server" && -d "$workspace/wesnoth_client" ]] || { printf 'Supply the extracted workspace containing both repositories.\n' >&2; exit 2; }
[[ "$phase" =~ ^(images|python|verify|all)$ && "$jobs" =~ ^([1-9]|1[0-6])$ ]] || { printf 'Invalid phase or job count (1–16).\n' >&2; exit 2; }
[[ $(uname -m) = x86_64 ]] || { printf 'This pinned verification environment requires an x86_64 VPS.\n' >&2; exit 2; }
workspace=$(cd -- "$workspace" && pwd -P)
show_or_run() {
    printf 'RUN'; printf ' %q' "$@"; printf '\n'
    if ! "$dry_run"; then "$@"; fi
}
ensure_image() {
    local tag=$1 recipe=$2
    if ! "$dry_run" && docker image inspect "$tag" >/dev/null 2>&1; then
        printf 'Retaining existing image %s; verify its tools before accepting the new environment.\n' "$tag"
        return
    fi
    show_or_run docker build --platform linux/amd64 --pull=false -f "$migration_dir/docker/$recipe" -t "$tag" "$migration_dir"
}
if ! "$dry_run"; then
    command -v docker >/dev/null
    docker info >/dev/null
    (cd -- "$migration_dir" && sha256sum --check SHA256SUMS)
fi
if [[ "$phase" = images || "$phase" = all ]]; then
    ensure_image wesnoth-server-verify:1.19.26 Dockerfile.server-verify
    ensure_image wesnoth-alliance-verify:python3.14.3-mongo8.0.32 Dockerfile.alliance-verify
    ensure_image wesnoth-alliance-native-verify:python3.14.3-gcc16.2 Dockerfile.native-verify
    ensure_image wesnoth-account-integration-verify:20261020 Dockerfile.account-integration-verify
    ensure_image wesnoth-android-cache-verify:8.9-java21.0.9 Dockerfile.android-cache-verify
    ensure_image wesnoth-android-sdl-verify:ndk26-java21 Dockerfile.android-sdl-verify
    ensure_image wesnoth-text-toolchain-verify:meson1.12 Dockerfile.text-toolchain-verify
    if "$with_wine"; then
        ensure_image wesnoth-mingw-worker-wine-verify:20261028 Dockerfile.wine-verify
        ensure_image wesnoth-mingw-worker-cmake-wine-verify:20261028 Dockerfile.cmake-wine-verify
    fi
fi
if [[ "$phase" = python || "$phase" = all ]]; then
    show_or_run docker run --rm --network none --user "$(id -u):$(id -g)" \
        --mount "type=bind,src=$migration_dir,dst=/migration,readonly" \
        --mount "type=bind,src=$workspace,dst=/workspace" \
        --tmpfs /tmp:rw,exec,mode=1777,size=2g \
        --workdir /tmp wesnoth-server-verify:1.19.26 \
        bash /migration/scripts/install-python312.sh "$jobs"
fi
if [[ "$phase" = verify || "$phase" = all ]]; then
    verification_dir="$workspace/wesnoth_server/build/migration-environment-check-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    if ! "$dry_run"; then mkdir -p -- "$verification_dir"; fi
    show_or_run docker run --rm --network none --ulimit nofile=65536:65536 \
        --user "$(id -u):$(id -g)" \
        --mount "type=bind,src=$migration_dir,dst=/migration,readonly" \
        --mount "type=bind,src=$workspace,dst=/workspace,readonly" \
        --mount "type=bind,src=$verification_dir,dst=/out" \
        --tmpfs /tmp:rw,exec,mode=1777,size=2g \
        --workdir /workspace/wesnoth_server \
        wesnoth-alliance-verify:python3.14.3-mongo8.0.32 \
        /workspace/wesnoth_server/build/host-python-3.12.10/bin/python3.12 -I -B /migration/scripts/verify-environment.py
    printf 'Verification report directory: %s\n' "$verification_dir"
fi
