# 공식 cam WSL 실행 절차

공식 cam은 WSL 가상 카메라 `Virtual2`에서만 관측되었습니다. 상태는 `observed-wsl-virtual-only`이며, 물리 DMA와 물리 카메라는 검증되지 않았습니다.

## 1. 실행 전 준비

1. 소스를 커밋 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61`로 고정하고, 추적 파일에 수정이 없는지 확인합니다.
2. 수정하지 않은 소스로 디버그 빌드를 만듭니다.
3. 프로브를 컴파일합니다: `gcc -std=c11 -Wall -Wextra -Werror -O0 -g dmabuf_probe.c -o <compiled-dmabuf-probe>`
4. 도구 접두 경로 아래에 `usr/bin/gdb`와 `usr/share/gdb`가 있는지 확인합니다.
5. 새 증거 디렉터리를 지정합니다. 이전 출력 디렉터리는 덮어쓸 수 없습니다.

## 2. 실행

WSL root 사용자 컨텍스트의 자식 프로세스에서 아래 명령을 실행합니다. `/dev/udmabuf`는 root만 접근할 수 있으며, 비루트 실행은 errno 13으로 실패했습니다.

```bash
PYTHONPATH=<generator>/src python3 <generator>/examples/libcamera/runtime/run_cam.py --source <unmodified-source-at-293d751a> --build <its-debug-meson-build> --tools <private-extracted-tools-prefix> --probe <compiled-dmabuf-probe> --out <new-evidence-directory>
```

`<generator>`는 생성기 저장소 경로입니다. 나머지 자리표시자는 위 준비 단계에서 정한 경로로 바꿉니다.

## 3. 결과 읽는 법

DMA 프로브는 실제 dmabuf를 내보낸 뒤 CPU 읽기/쓰기 동기화를 수행했고, 모든 단계가 성공했습니다. 세 프로세스(pid 434, 449, 464)는 각각 프레임 3개를 완료했고, 버퍼 시퀀스 0, 1, 2를 성공 메타데이터로 기록했습니다.

세 관측 지점은 요청(`request`), 시퀀스(`sequence`), 상태(`status`)로 묶어 봅니다. `callback-entry`는 콜백 스레드에서, `frame-processed`와 `buffer-metadata`는 처리 스레드에서 기록되므로 TID는 서로 다를 수 있습니다.

실패는 성공으로 바꾸지 않습니다. 시간 초과 프로브(0.5초)는 종료 코드 1로 남았고, 정리 단계 기록은 0건입니다. 음성 프로브(errno 2, 25)도 실패로 기록되었습니다.

## 4. 커널과 승인 경계

시험 뒤 패키지 기본 커널 `6.18.33.2-microsoft-standard-WSL2`로 복구했습니다. 복구된 커널은 udmabuf 할당기를 노출하지 않으므로, 이전 시험이 성공했다고 해서 기본 커널이 이를 지원한다는 뜻은 아닙니다. 일치하는 모듈은 설치하지 않았습니다.

커널 교체, `.wslconfig` 변경, WSL 종료는 공유 자원 변경입니다. 호스트에서 별도 승인을 받아야 하며, 승인 요청에는 정확한 백업과 롤백 절차를 포함하고 Docker를 먼저 중지해야 합니다. `kernel_trial.py`는 자동으로 실행하지 마십시오.

## 5. 검증 한계

- 물리 DMA, 물리 카메라, 제품 앱, 사내 HAL은 검증되지 않았습니다.
- 사람 검토는 `pending`입니다. 이 문서는 승인을 대신하지 않습니다.
- GDB 중단점은 타이밍을 바꿉니다. GDB 결과는 타이밍 증명도, 반환 증명도 아닙니다. 콜백 반환 명령은 관측되지 않았습니다.
- 취소 분기는 실행되지 않았습니다. 취소 0회는 강제로 만든 결과가 아닙니다.

## 관련 문서

과거 CPU 전용 프로브 기록은 [README.md](README.md)에서 확인합니다. 이번 실행의 원본 관측 자료는 [observation.json](../validation/issue211/runs/20261031-wsl-cam-3/observation.json)입니다.
