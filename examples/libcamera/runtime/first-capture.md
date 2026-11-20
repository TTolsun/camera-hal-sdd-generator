# 가상 카메라의 첫 프레임 확인

Linux 셸에서 `Virtual2` 첫 프레임을 캡처하세요. 멈추면 `$OUT/serial.log`에서 마지막으로 통과한 단계와 다음 확인 위치를 찾으세요. 이 시험은 libcamera 가상 파이프라인을 다루며, 실제 카메라나 사내 Camera HAL을 검증하지 않습니다.

<a id="prepare-environment"></a>
## 환경 준비

기록 기준일은 2026-11-21 KST입니다. 관측한 호스트는 Windows 11 Home build 26300의 Ubuntu 26.04 LTS x86_64 WSL2입니다. 시험에는 별도로 추출한 공개 도구인 QEMU 10.2.1 TCG와 GDB를 사용했습니다. 아래 공개 패키지로 처음부터 설치한 전체 과정은 검증하지 않았습니다.

1. 배포판 GDB와 일치하는 Ubuntu 시스템 Python을 사용하고 표준 패키지를 설치합니다.

   ```bash
   sudo apt update
   sudo apt install build-essential git meson ninja-build pkg-config python3 python3-yaml python3-jinja2 python3-ply libyaml-dev libgnutls28-dev libudev-dev libevent-dev libdrm-dev libyuv-dev openssl qemu-system-x86 seabios busybox-static cpio gdb bc bison flex libelf-dev libssl-dev dwarves
   ```

2. 공백이 없는 절대 경로를 지정합니다. `$GENERATOR`는 이미 클론한 이 저장소이고, 나머지는 아직 존재하지 않는 경로입니다. 실행기는 `$OUT`을 직접 만듭니다.

   ```bash
   export GENERATOR=/absolute/path/to/camera-hal-sdd-generator
   export LIBCAMERA=/absolute/path/to/new-libcamera
   export KERNEL=/absolute/path/to/new-kernel
   export BUILD=/absolute/path/to/new-build
   export OUT=/absolute/path/to/new-output
   ```

3. 공식 libcamera 소스를 고정하고 디버그 빌드를 만듭니다.

   ```bash
   git clone https://gitlab.freedesktop.org/camera/libcamera.git "$LIBCAMERA"
   git -C "$LIBCAMERA" checkout --detach adfa719f8ed67d18fd8a0739fc088a1f8b9e7252
   meson setup "$BUILD" "$LIBCAMERA" --buildtype=debug -Dpipelines=virtual '-Dipas=[]' -Dcam=enabled -Dqcam=disabled -Dtest=false -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled -Dv4l2=disabled -Dlc-compliance=disabled
   ninja -C "$BUILD" -j6
   ```

4. 커널을 고정하고 [보관된 test.config](../validation/issue211/runs/20261031-kernel-config/test.config)로 빌드합니다.

   ```bash
   git clone https://github.com/microsoft/WSL2-Linux-Kernel "$KERNEL"
   git -C "$KERNEL" checkout --detach linux-msft-wsl-6.18.33.2
   test "$(git -C "$KERNEL" rev-parse HEAD)" = c21a03b2943d147c280bdf32530d4fe6badfd6bd
   cp "$GENERATOR/examples/libcamera/validation/issue211/runs/20261031-kernel-config/test.config" "$KERNEL/.config"
   make -C "$KERNEL" olddefconfig
   make -C "$KERNEL" -j6 bzImage
   ```

<a id="first-frame"></a>
## 첫 프레임 실행

1. 일반 사용자로 [실행기](run_first_capture_vm.sh)를 실행합니다.

   ```bash
   bash "$GENERATOR/examples/libcamera/runtime/run_first_capture_vm.sh" "$KERNEL/arch/x86/boot/bzImage" "$LIBCAMERA" "$BUILD" "$OUT"
   ```

2. `$OUT/serial.log`를 읽습니다. 실행기는 먼저 계측 없이 프레임을 파일로 저장하고, 별도의 두 번째 캡처에서 GDB로 요청 반환값과 콜백을 관찰합니다. 파일과 종료 코드는 첫 실행에서, 콜백과 버퍼 상태는 두 번째 실행에서 확인합니다.

게스트는 격리되어 있고 root 권한은 게스트 안에서만 사용합니다. NIC와 하드웨어 패스스루는 없으며 호스트 WSL 설정은 바꾸지 않습니다. 실행기는 마지막에 게스트의 `/dev/udmabuf`만 숨겨 할당기 누락 시험을 합니다. 이때 카메라 설정은 성공하지만 버퍼 할당은 실패해야 합니다.

<a id="find-first-failure"></a>
## 첫 실패 찾기

순서대로 확인하고 처음 실패한 행에서 멈추세요. 관측값을 해당 행과 대조한 뒤 다음 확인 위치로 이동하세요.

| 확인 단계 | 관측된 성공 | 실패 시 확인할 곳 |
|---|---|---|
| 장치 탐색 | `Available cameras:`에 `Virtual2`가 표시됩니다. | `cam --list`, 가상 파이프라인과 provider 오류를 확인합니다. |
| 설정 | `configuring streams: (0) 400x300-NV12/SMPTE170M`이 표시됩니다. | 요청 형식과 [구성 진단](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#구성-실패를-좁히는-순서), [캡처 시작 코드](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L365)를 확인합니다. |
| 할당 | 첫 요청의 제출 중단점에 도달하면 그 전에 실행되는 버퍼 할당을 통과한 것입니다. | `Could not open any dma-buf provider`, `Can't allocate buffers`, 게스트의 `/dev/udmabuf` 접근 권한과 커널 설정을 확인합니다. DMA-BUF heap을 쓰는 구성이라면 `/dev/dma_heap`도 확인합니다. [할당기 코드](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/libcamera/dma_buf_allocator.cpp#L119)를 확인합니다. |
| 요청 제출 | GDB가 관찰한 첫 호출이 `0`을 반환합니다. | [queueRequest](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L453)의 반환값과 캡처 한도 분기를 확인합니다. |
| 콜백 | `CALLBACK`에 `RequestComplete`가 표시됩니다. | [requestComplete](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L467)와 [완료 통지 진단](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서)에서 같은 요청의 전달과 완료를 확인합니다. |
| 정상 프레임 | 같은 요청 포인터의 `FRAME`에 시퀀스 `0`과 `FrameSuccess`가 표시됩니다. 같은 실행의 프레임 출력에서 두 평면은 `120000/60000`바이트입니다. | [완료 처리](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/apps/cam/camera_session.cpp#L479)에서 버퍼 상태와 각 평면의 사용 바이트를 확인합니다. |

[측정된 VM 로그](issue337-vm.log)의 두 번째 캡처에서 `queueRequest` 중단점과 `CALLBACK`, `FRAME`의 요청 포인터가 일치합니다. 제출 반환값, 완료 알림, 버퍼 상태를 각각 확인합니다.

```text
Value returned is $1 = 0
CALLBACK request=0x5555556790d0 status=libcamera::Request::RequestComplete
FRAME request=0x5555556790d0 sequence=0 status=libcamera::FrameMetadata::FrameSuccess
cam0-stream0 seq: 000000 bytesused: 120000/60000
```

첫 번째 캡처의 종료 코드는 `0`이었고, `/tmp/frame.bin`은 180,000바이트였습니다. 할당기 누락 시험에서는 탐색 중에도 할당기 경고가 나왔지만 `Virtual2`가 목록에 표시됐고 스트림 구성까지 진행했습니다. 첫 실패는 버퍼 할당입니다.

```text
Can't allocate buffers
Failed to start camera session
negative_capture_exit=1
TRIAL_FINISHED
```

<a id="run-evidence"></a>
## 실행 근거

[이번 기본 WSL 실행 로그](issue337-wsl-baseline.log)는 기본 커널에서 `CONFIG_UDMABUF`와 `CONFIG_DMABUF_HEAPS`가 꺼져 있고 두 provider 경로가 없음을 보여 줍니다. 배포된 #211의 연결된 이전 실행 안내에서 요구한 테스트 커널도 당시 실행 중인 호스트에 없었습니다. 그 사전 조건 부족과 별도로 제한 시간을 둔 WSL 진단 명령을 실행했으며, 장치 탐색과 스트림 구성까지 성공했습니다. 첫 실패는 버퍼 할당이었고, 캡처 종료 코드는 `1`이었습니다. 이 로그는 다른 libcamera 커밋 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61`의 기록입니다.

2026-10-31의 #211 기록은 수정된 WSL 부팅에서 3×3 시험이 성공한 과거 관측입니다. 시험 커널에서 각각 3프레임씩 3회 확인한 뒤 기본 커널을 복원했습니다.

[VM 측정 로그](issue337-vm.log)에는 사용한 커널 이미지의 SHA-256이 기록되어 있습니다. 다시 빌드한 이미지가 비트 단위로 같다고 보장하지 않습니다. 다음으로 [OFFICIAL_CAM.md](OFFICIAL_CAM.md)를 확인하세요.
