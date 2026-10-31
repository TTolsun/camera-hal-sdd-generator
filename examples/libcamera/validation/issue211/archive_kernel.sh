#!/bin/bash
set -euo pipefail
work=$1
out=$2
[[ "$work" == "$HOME"/.cache/issue211-kernel-* ]]
mkdir "$out"
source="$work/WSL2-Linux-Kernel-linux-msft-wsl-6.18.33.2"
cp "$source/arch/x86/boot/bzImage" "$out/bzImage"
cp "$source/.config" "$out/test.config"
cp "$work/running.config" "$out/running.config"
cp "$source/drivers/dma-buf/Kconfig" "$out/dma-buf.Kconfig"
cp "$source/drivers/dma-buf/heaps/Kconfig" "$out/heaps.Kconfig"
cp "$source/drivers/dma-buf/udmabuf.c" "$out/udmabuf.c"
sha256sum "$out/"*
git ls-remote https://github.com/microsoft/WSL2-Linux-Kernel.git 'refs/tags/linux-msft-wsl-6.18.33.2*'
