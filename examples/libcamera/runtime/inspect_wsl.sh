#!/bin/bash
# Read-only inventory. Capture stdout, stderr and exit status with run_recorded.
set -u
date -u --iso-8601=seconds
uname -a
id
cat /etc/os-release
cat /proc/version
zcat /proc/config.gz | grep -E 'CONFIG_(UDMABUF|DMABUF_HEAPS|DMA_SHARED_BUFFER|MEMFD_CREATE|SHMEM|MMU|MODULES|MODVERSIONS|MODULE_SIG|CMA|DEBUG_INFO_BTF|USB_VIDEO_CLASS|USBIP_VHCI_HCD)'
lsmod
ls -ld /dev/dma_heap /dev/dma_heap/* /dev/udmabuf /dev/video* /dev/media* /lib/modules/"$(uname -r)" 2>&1
find /lib/modules/"$(uname -r)" -iname '*dmabuf*' -o -name Module.symvers -o -name build
for tool in cam gdb strace meson ninja g++ gcc make flex bison bc pahole claude codex; do
    command -v "$tool" || true
done
for source in "$HOME/work/libcamera" "$HOME/work/camera-sdd-goal-20261027" "$HOME/.cache/camera-hal-sdd-issue193-293/source"; do
    echo "SOURCE:$source"
    git -C "$source" rev-parse HEAD
    git -C "$source" status --short --untracked-files=no
    git -C "$source" remote -v
    find "$source" -maxdepth 5 -type f -path '*/apps/cam/cam' -print
done
df -h /tmp
nproc
free -m
