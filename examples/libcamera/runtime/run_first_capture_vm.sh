#!/usr/bin/env bash
# Run as a regular user. All device changes happen inside the disposable guest.
set -euo pipefail

if [[ $# != 4 ]]; then
    echo "Usage: $0 TEST_KERNEL LIBCAMERA_SOURCE DEBUG_MESON_BUILD NEW_OUTPUT_DIRECTORY" >&2
    exit 2
fi
kernel=$(realpath -e "$1")
source=$(realpath -e "$2")
build=$(realpath -e "$3")
mkdir "$4"
out=$(realpath -e "$4")
guest="$out/guest"
cam="$build/src/apps/cam/cam"
gdb=$(command -v gdb)
firmware=${QEMU_FIRMWARE:-/usr/share/seabios/bios-256k.bin}
qemu_data=${QEMU_DATA_DIR:-/usr/share/qemu}
export LC_ALL=C

test -x "$cam"
test -r "$firmware"
if [[ -n $(git -C "$source" status --porcelain --untracked-files=no) ]]; then
    echo "The libcamera source has tracked changes." >&2
    exit 1
fi

mkdir -p "$guest"/{bin,dev,proc,sys,tmp,trial}
install "$(command -v busybox)" "$guest/bin/busybox"
ln -s busybox "$guest/bin/sh"
install "$cam" "$guest/trial/cam"
install "$gdb" "$guest/trial/gdb"

copy_dependencies() {
    local binary="$1" dependencies library
    dependencies=$(ldd "$binary")
    if [[ $dependencies == *'not found'* ]]; then
        printf '%s\n' "$dependencies" >&2
        exit 1
    fi
    while IFS= read -r library; do
        if [[ $library == "$build/"* ]]; then
            install -D "$library" "$guest/trial/lib/${library##*/}"
        else
            install -D "$library" "$guest$library"
        fi
    done < <(awk '{for (i=1; i<=NF; i++) if ($i ~ /^\//) print $i}' <<< "$dependencies")
}
copy_dependencies "$cam"
copy_dependencies "$gdb"
gdb_data=$(realpath -e "$(dirname "$gdb")/../share/gdb")
cp -a "$gdb_data" "$guest/trial/gdb-data"
thread_db=$(ldconfig -p | awk '/libthread_db.so.1/{print $NF; exit}')
install -D "$thread_db" "$guest$thread_db"
install -Dm 644 "$source/src/libcamera/pipeline/virtual/data/virtual.yaml" \
    "$guest/usr/local/share/libcamera/pipeline/virtual/virtual.yaml"

# GDB initializes its embedded Python even for a plain GDB command file.
python_stdlib=$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')
cp -a --parents "$python_stdlib" "$guest"
gdb_libraries=$(ldd "$gdb" | awk '$3 ~ /^\//{print $3}' | xargs -r -n1 dirname | sort -u | paste -sd:)
printf 'export LD_LIBRARY_PATH=%q\n' "/trial/lib:$gdb_libraries" > "$guest/trial/env"

frame_line=$(awk '/info << " " << streamNames_\[stream\]/{print NR}' "$source/src/apps/cam/camera_session.cpp")
[[ $frame_line =~ ^[0-9]+$ ]]
cat > "$guest/trial/observe.gdb" <<EOF
set pagination off
set debuginfod enabled off
set startup-with-shell off
break CameraSession::queueRequest
break CameraSession::requestComplete
commands
silent
printf "CALLBACK request=%p status=", request
output request->status_
printf "\\n"
continue
end
break camera_session.cpp:$frame_line
commands
silent
printf "FRAME request=%p sequence=%u status=", request, metadata.sequence
output metadata.status
printf "\\n"
continue
end
run
finish
disable 1
continue
EOF

cat > "$guest/init" <<'EOF'
#!/bin/sh
set -eu
export PATH=/bin
export LIBCAMERA_PIPELINES_MATCH_LIST=virtual
export LIBCAMERA_LOG_COLOR=no
/bin/busybox --install -s /bin
mount -t devtmpfs devtmpfs /dev
mount -t proc proc /proc
mount -t sysfs sysfs /sys
. /trial/env
uname -a
ls -l /dev/udmabuf
test -c /dev/udmabuf

set -- --camera Virtual2 --stream role=video,width=400,height=300,pixelformat=NV12 --capture=1 --strict-formats
echo 'COMMAND cam --list'
/trial/cam --list
echo list_exit=0
echo "COMMAND cam $* --file=/tmp/frame.bin"
/trial/cam "$@" --file=/tmp/frame.bin
echo capture_exit=0
test "$(wc -c < /tmp/frame.bin)" -eq 180000
wc -c /tmp/frame.bin
sha256sum /tmp/frame.bin
echo "COMMAND gdb -nx -batch --return-child-result -D /trial/gdb-data -x /trial/observe.gdb --args cam $*"
/trial/gdb -nx -batch --return-child-result -D /trial/gdb-data -x /trial/observe.gdb --args /trial/cam "$@"

# Hide the provider in this guest only. Both commands use the same camera build.
mv /dev/udmabuf /dev/udmabuf.disabled
echo 'NEGATIVE cam --list'
/trial/cam --list
echo negative_list_exit=0
echo "NEGATIVE cam $*"
status=0
/trial/cam "$@" || status=$?
echo "negative_capture_exit=$status"
test "$status" -ne 0
echo TRIAL_FINISHED
poweroff -f
EOF
chmod +x "$guest/init"

(cd "$guest"; find . -print0 | cpio --quiet --null --create --format=newc --owner=0:0 | gzip -1) > "$out/initramfs.cpio.gz"
{
    git -C "$source" rev-parse HEAD
    sha256sum "$kernel" "$cam"
    qemu-system-x86_64 --version
    timeout 120 qemu-system-x86_64 -accel tcg -m 768 -smp 2 -vga none -display none \
        -monitor none -serial stdio -nic none -no-reboot -bios "$firmware" -L "$qemu_data" \
        -kernel "$kernel" -initrd "$out/initramfs.cpio.gz" \
        -append 'console=ttyS0 rdinit=/init panic=1 loglevel=3'
} 2>&1 | tee "$out/serial.log"

grep -q 'Value returned is .* = 0' "$out/serial.log"
awk '
    /^CALLBACK request=.*status=.*RequestComplete/ { completed = $2 }
    /^FRAME request=.*sequence=0 status=.*FrameSuccess/ && completed == $2 { received = 1 }
    END { exit !received }
' "$out/serial.log"
grep -q 'seq: 000000 bytesused: 120000/60000' "$out/serial.log"
grep -q "Can't allocate buffers" "$out/serial.log"
grep -q 'TRIAL_FINISHED' "$out/serial.log"
