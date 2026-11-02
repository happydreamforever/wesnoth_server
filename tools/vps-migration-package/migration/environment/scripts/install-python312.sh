#!/usr/bin/env bash
set -euo pipefail
build_jobs=${1:-4}
[[ "$build_jobs" =~ ^([1-9]|1[0-6])$ ]] || exit 2
python_prefix=/workspace/wesnoth_server/build/host-python-3.12.10
python_archive=/migration/vendor/python312/Python-3.12.10.tar.xz
if [[ -e "$python_prefix" ]]; then
    printf 'Existing Python prefix retained. Run --phase verify; this installer never replaces it.\n'
    exit 0
fi
printf '07ab697474595e06f06647417d3c7fa97ded07afc1a7e4454c5639919b46eaea  %s\n' "$python_archive" | sha256sum --check
python_work=$(mktemp -d /tmp/wesnoth-python312.XXXXXXXX)
trap 'rm -rf -- "$python_work"' EXIT
mkdir -p -- /workspace/wesnoth_server/build
tar -xJf "$python_archive" -C "$python_work"
cd -- "$python_work/Python-3.12.10"
./configure --prefix="$python_prefix" --disable-test-modules --with-ensurepip=install
make -j "$build_jobs"
make install
"$python_prefix/bin/python3.12" -I -B -m pip install --no-index --no-deps --require-hashes \
    --find-links=/migration/vendor/python312/linux-wheels -r /migration/pins/requirements-linux312-hashed.txt
"$python_prefix/bin/python3.12" -I -B -m pip check
"$python_prefix/bin/python3.12" -I -B -c 'import sys,ssl,sqlite3,bz2,lzma,ctypes,venv; assert sys.version_info[:3]==(3,12,10); print(sys.version); print(ssl.OPENSSL_VERSION)'
printf 'PYTHON 3.12.10 VERIFICATION PREFIX INSTALLED\n'
