#!/bin/bash
# New checkout/build and private tools only; no host package installation.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../../.." && pwd)
work=${1:-$(mktemp -d "$HOME/.cache/issue211-runtime-XXXXXXXX")}
[[ "$work" == "$HOME"/.cache/issue211-runtime-* && -d "$work" ]]
echo "WORK:$work"
mkdir -p "$work/packages" "$work/tools"
cd "$work/packages"
apt-get download gdb strace libdebuginfod1t64 libipt2 libsource-highlight4t64 libboost-regex1.88.0 libbabeltrace1 libdw1t64 libelf1t64 libunwind8
for package in ./*.deb; do dpkg-deb -x "$package" "$work/tools"; done
export PATH="$work/tools/usr/bin:$PATH"
export LD_LIBRARY_PATH="$work/tools/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
ldd "$work/tools/usr/bin/gdb"
gdb --version
strace --version
git clone --no-hardlinks "$HOME/.cache/camera-hal-sdd-issue193-293/source" "$work/source"
git -C "$work/source" remote set-url origin https://gitlab.freedesktop.org/camera/libcamera.git
git -C "$work/source" fetch origin
git -C "$work/source" rev-parse origin/master
git -C "$work/source" checkout --detach 293d751a814e0d4c34e85ad457ccd9d5eefd1a61
git -C "$work/source" status --porcelain --untracked-files=no
meson setup "$work/build" "$work/source" --buildtype=debug -Dpipelines=virtual '-Dipas=[]' -Dcam=enabled -Dqcam=disabled -Dtest=false -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled -Dv4l2=disabled -Dlc-compliance=disabled
ninja -C "$work/build" -j8
gcc -std=c11 -Wall -Wextra -Werror -O0 -g "$root/examples/libcamera/runtime/dmabuf_probe.c" -o "$work/dmabuf-probe"
sha256sum "$work/dmabuf-probe" "$work/build/src/apps/cam/cam" "$work/build/src/libcamera/libcamera.so" "$work/build/src/libcamera/base/libcamera-base.so"
echo "PREPARED_ONLY:$work"
