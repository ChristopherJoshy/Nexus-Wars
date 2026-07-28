#!/usr/bin/env bash
# Build nsjail with a patched kafel syscall table.
#
# nsjail 3.4's bundled kafel table is missing modern syscalls
# (rseq, statx, faccessat2, clone3, stat, lstat, fstat). Without them the
# seccomp policy (deploy/seccomp.policy) fails to compile and Python bots are
# killed at startup. We overlay the patched amd64 table, then build.
#
# Usage: build_nsjail.sh [install-prefix]   (default: /usr/local)
set -e
PREFIX="${1:-/usr/local}"
NSJAIL_VER="${NSJAIL_VER:-3.4}"

echo "== cloning nsjail ${NSJAIL_VER} =="
rm -rf /tmp/nsjail-build
if git clone --depth 1 --branch "${NSJAIL_VER}" https://github.com/google/nsjail /tmp/nsjail-build; then
    cd /tmp/nsjail-build
    git submodule update --init --recursive
else
    echo "ERROR: failed to clone nsjail"
    exit 1
fi

echo "== overlaying patched amd64 syscall table =="
PATCH_SRC="/tmp/nsjail-patch/amd64_syscalls.c"
if [ ! -f "$PATCH_SRC" ]; then
    PATCH_SRC="/tmp/amd64_syscalls.c"
fi

if [ -f "$PATCH_SRC" ]; then
    mkdir -p /tmp/nsjail-build/kafel/src/syscalls
    cp "$PATCH_SRC" /tmp/nsjail-build/kafel/src/syscalls/amd64_syscalls.c
else
    echo "Warning: amd64_syscalls.c patch file not found, continuing with upstream table"
fi

echo "== building =="
cd /tmp/nsjail-build
make -j"$(nproc)"
install -m 0755 nsjail "${PREFIX}/bin/nsjail"
echo "== nsjail installed: $(${PREFIX}/bin/nsjail --help 2>&1 | head -1 || true) =="
