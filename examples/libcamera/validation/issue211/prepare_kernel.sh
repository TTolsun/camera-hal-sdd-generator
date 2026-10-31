#!/bin/bash
# Preparation only. Never install modules, edit .wslconfig, or stop WSL.
set -euo pipefail
work=${1:-$(mktemp -d "$HOME/.cache/issue211-kernel-XXXXXXXX")}
[[ "$work" == "$HOME"/.cache/issue211-kernel-* && -d "$work" ]]
echo "$work"
exec 9>"$work/preparation.lock"
flock -n 9 || { echo 'Another preparation is active' >&2; exit 1; }
mkdir -p "$work/packages" "$work/toolchain"
cd "$work/packages"
apt-get download flex bison m4 libfl2 libelf-dev libssl-dev libssl3t64 pahole libdwarves1 libbpf1 libdw1t64 libelf1t64
for package in ./*.deb; do dpkg-deb -x "$package" "$work/toolchain"; done
export PATH="$work/toolchain/usr/bin:$PATH"
export LD_LIBRARY_PATH="$work/toolchain/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export C_INCLUDE_PATH="$work/toolchain/usr/include:$work/toolchain/usr/include/x86_64-linux-gnu${C_INCLUDE_PATH:+:$C_INCLUDE_PATH}"
export LIBRARY_PATH="$work/toolchain/usr/lib/x86_64-linux-gnu${LIBRARY_PATH:+:$LIBRARY_PATH}"
export M4="$work/toolchain/usr/bin/m4"
export BISON_PKGDATADIR="$work/toolchain/usr/share/bison"
cd "$work"
if [[ ! -f kernel.tar.gz ]]; then
    curl -fL --retry 2 --max-time 300 https://github.com/microsoft/WSL2-Linux-Kernel/archive/refs/tags/linux-msft-wsl-6.18.33.2.tar.gz -o kernel.tar.gz
fi
sha256sum kernel.tar.gz
if [[ ! -d WSL2-Linux-Kernel-linux-msft-wsl-6.18.33.2 ]]; then tar -xzf kernel.tar.gz; fi
source="$work/WSL2-Linux-Kernel-linux-msft-wsl-6.18.33.2"
cd "$source"
zcat /proc/config.gz > "$work/running.config"
cp "$work/running.config" .config
scripts/config --enable UDMABUF --set-str LOCALVERSION '-microsoft-standard-WSL2-issue211'
make olddefconfig
scripts/diffconfig "$work/running.config" .config
make -j8 bzImage
make kernelrelease
sha256sum .config arch/x86/boot/bzImage
printf '%s\n' "$source" > "$work/prepared-source.txt"
echo "PREPARED_ONLY:$work"
