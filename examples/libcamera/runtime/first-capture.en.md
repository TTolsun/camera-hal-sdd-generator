# Capture the first virtual-camera frame

Run the steps below in a Linux shell, then find the first failed checkpoint in `$OUT/serial.log`. This tests the libcamera virtual pipeline; it does not validate a physical camera or an internal Camera HAL.

<a id="prepare-environment"></a>
## Prepare the environment

The observation date is 2026-11-21 KST. The measured host was Ubuntu 26.04 LTS x86_64 on WSL2 under Windows 11 Home build 26300. The test used privately extracted public tools: QEMU 10.2.1 TCG and GDB. A complete pristine installation using the packages below was not tested.

1. Use Ubuntu system Python matching the distribution GDB, and install the standard packages.

   ```bash
   sudo apt update
   sudo apt install build-essential git meson ninja-build pkg-config python3 python3-yaml python3-jinja2 python3-ply libyaml-dev libgnutls28-dev libudev-dev libevent-dev libdrm-dev libyuv-dev openssl qemu-system-x86 seabios busybox-static cpio gdb bc bison flex libelf-dev libssl-dev dwarves
   ```

2. Set absolute paths without spaces. `$GENERATOR` is an existing clone of this repository; the other paths must be new. The runner creates `$OUT` itself.

   ```bash
   export GENERATOR=/absolute/path/to/camera-hal-sdd-generator
   export LIBCAMERA=/absolute/path/to/new-libcamera
   export KERNEL=/absolute/path/to/new-kernel
   export BUILD=/absolute/path/to/new-build
   export OUT=/absolute/path/to/new-output
   ```

3. Pin official libcamera and build with debug information.

   ```bash
   git clone https://gitlab.freedesktop.org/camera/libcamera.git "$LIBCAMERA"
   git -C "$LIBCAMERA" checkout --detach adfa719f8ed67d18fd8a0739fc088a1f8b9e7252
   meson setup "$BUILD" "$LIBCAMERA" --buildtype=debug -Dpipelines=virtual '-Dipas=[]' -Dcam=enabled -Dqcam=disabled -Dtest=false -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled -Dv4l2=disabled -Dlc-compliance=disabled
   ninja -C "$BUILD" -j6
   ```

4. Pin the kernel and build it with the [archived test.config](../validation/issue211/runs/20261031-kernel-config/test.config).

   ```bash
   git clone https://github.com/microsoft/WSL2-Linux-Kernel "$KERNEL"
   git -C "$KERNEL" checkout --detach linux-msft-wsl-6.18.33.2
   test "$(git -C "$KERNEL" rev-parse HEAD)" = c21a03b2943d147c280bdf32530d4fe6badfd6bd
   cp "$GENERATOR/examples/libcamera/validation/issue211/runs/20261031-kernel-config/test.config" "$KERNEL/.config"
   make -C "$KERNEL" olddefconfig
   make -C "$KERNEL" -j6 bzImage
   ```

<a id="first-frame"></a>
## Run the first frame

1. Run the [repository runner](run_first_capture_vm.sh) as a regular user.

   ```bash
   bash "$GENERATOR/examples/libcamera/runtime/run_first_capture_vm.sh" "$KERNEL/arch/x86/boot/bzImage" "$LIBCAMERA" "$BUILD" "$OUT"
   ```

2. Read `$OUT/serial.log`. The runner first saves a frame in an uninstrumented capture. A separate second capture uses GDB to observe the request return value and callback. Do not treat them as the same request.

The guest is isolated, with root only inside it, no NIC, and no hardware passthrough. Host WSL configuration is unchanged. Finally, the runner hides only the guest's `/dev/udmabuf` for a controlled negative test: configuration succeeds, but buffer allocation must fail.

<a id="find-first-failure"></a>
## Find the first failure

Check these stages in order and stop at the first failure. Compare the log with the expected result and follow the link in that row.

| Checkpoint | Observed success | Where to check failure |
|---|---|---|
| Discovery | `Available cameras:` includes `Virtual2`. | Check `cam --list`, the virtual pipeline, and provider errors. |
| Configuration | `configuring streams: (0) 400x300-NV12/SMPTE170M` appears. | Check the requested format, the [configuration diagnosis](https://ttolsun.github.io/libcamera-sdd/en/request-diagnosis.html#구성-실패를-좁히는-순서), and the [capture startup code](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L365). |
| Allocation | Reaching the first submission breakpoint confirms that the earlier buffer allocation step passed. | Check `Could not open any dma-buf provider`, `Can't allocate buffers`, and the guest kernel configuration and access to `/dev/udmabuf`. Check `/dev/dma_heap` for builds that use DMA-BUF heaps. See the [allocator](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/libcamera/dma_buf_allocator.cpp#L119). |
| Request submission | The first call observed in GDB returns `0`. | Check the return value and capture-limit branch in [queueRequest](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L453). |
| Callback | `CALLBACK` reports `RequestComplete`. | Check [requestComplete](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L467) and the [completion diagnosis](https://ttolsun.github.io/libcamera-sdd/en/request-diagnosis.html#실패-위치별-확인-순서) for delivery and completion of the same request. |
| Valid frame | `FRAME` reports sequence `0` and `FrameSuccess` for the same request pointer. The frame log from the same run shows `120000/60000` bytes used. | Check buffer status and bytes used in each plane in [completion handling](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L479). |

In the second capture in the [measured VM log](issue337-vm.log), the request pointer matches at the `queueRequest` breakpoint, `CALLBACK`, and `FRAME`. Check the submission return, completion notification, and buffer status separately.

```text
Value returned is $1 = 0
CALLBACK request=0x5555556790d0 status=libcamera::Request::RequestComplete
FRAME request=0x5555556790d0 sequence=0 status=libcamera::FrameMetadata::FrameSuccess
cam0-stream0 seq: 000000 bytesused: 120000/60000
```

The first capture exited with code `0` and wrote a 180,000-byte `/tmp/frame.bin`. In the missing-allocator test, the provider warning also appeared during discovery, and `Virtual2` still appeared in the list and reached stream configuration. Buffer allocation was the first failed step.

```text
Can't allocate buffers
Failed to start camera session
negative_capture_exit=1
TRIAL_FINISHED
```

<a id="run-evidence"></a>
## Run evidence

The [initial WSL log](issue337-wsl-baseline.log) shows that the default kernel had `CONFIG_UDMABUF` and `CONFIG_DMABUF_HEAPS` disabled and neither provider path existed. The test kernel prescribed by the older runbook linked from deployed #211 was also absent from the live host. Separately, a bounded WSL diagnostic command was run despite that preflight gap; discovery and stream configuration succeeded. Buffer allocation failed first, and cam exited with code `1`. That log records a different libcamera commit, `293d751a814e0d4c34e85ad457ccd9d5eefd1a61`.

The 2026-10-31 #211 successful 3×3 run is a separate historical observation from a modified WSL boot. It completed three frames in each of three runs before the default kernel was restored.

The [measured VM log](issue337-vm.log) records the kernel image SHA-256. A rebuilt image is not promised to be bit-identical. Next, read [OFFICIAL_CAM.md](OFFICIAL_CAM.md).
