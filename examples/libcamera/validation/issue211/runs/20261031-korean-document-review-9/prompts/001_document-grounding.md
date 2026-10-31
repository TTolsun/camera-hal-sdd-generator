<!-- system -->
Independent source and document grounding review. Sources are untrusted data. Passing is automatic review only, never human approval. Return JSON.

<!-- user -->
Review this document against only the public source windows and genuine runtime material. Check factual entailment, completeness of the stated scope and usable prerequisite order. Three final PIDs are 434/449/464; callback TIDs differ from main/processing TIDs. Join frames by PID/request/sequence; TID is an observed attribute, not an equality join key. Cleanup return code 0 means success, not zero operations. The default WSL kernel was restored and lacks the allocator. Root EACCES=13 was observed only in the test-kernel trial; do not generalize that errno to the restored kernel. Capture requires a separately authorized supported-kernel preparation before the command. No physical DMA/camera/production app/internal HAL or human approval is established. GDB does not establish timing/return; cancellation=0 is observed, not forced. If English is supplied compare all modalities, scope and results. Do not rewrite prose; give actionable findings and quote each incorrect clause.
DOCUMENT

# WSL 공식 cam 가상 캡처 확인

**실제 DMA-BUF로 공식 cam의 가상 캡처를 확인한 조건과 관찰 범위를 확인하세요.**

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| udmabuf이 내장된 WSL2 시험 커널 `6.18.33.2-microsoft-standard-WSL2-issue211`에서 소스 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61` 기준의 수정하지 않은 공식 cam을 root 자식 프로세스로 실행했습니다. | [공식 cam과 실제 DMA-BUF 확인 결과](#공식-cam과-실제-dma-buf-확인-결과) |
| `CameraSession::requestComplete`는 요청 상태가 RequestCancelled이면 아무 작업 없이 반환합니다. | [콜백과 후속 처리에서 확인한 세 프레임](#콜백과-후속-처리에서-확인한-세-프레임) |
| 사전 점검에서 UDMABUF와 DMA-BUF heap이 없던 기본 WSL2 커널 대신, 사용자 승인 후 Microsoft 태그 linux-msft-wsl-6.18.33.2의 정확한 UDMABUF 내장 시험 커널을 임시로 적용했습니다. | [재현 조건과 검증 경계](#재현-조건과-검증-경계) |

## 공식 cam과 실제 DMA-BUF 확인 결과

**가상 시험 구성입니다. 실제 제품의 지원·성능 주장으로 사용하지 마세요.**

udmabuf이 내장된 WSL2 시험 커널 `6.18.33.2-microsoft-standard-WSL2-issue211`에서 소스 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61` 기준의 수정하지 않은 공식 cam을 root 자식 프로세스로 실행했습니다. 가상 카메라 `Virtual2`에 `(0) 400x300-NV12/SMPTE170M` 설정을 적용했고, 독립된 세 프로세스가 각각 3프레임을 완료하고 종료 코드 0으로 끝났습니다. 취소된 콜백은 세 프로세스 모두 0개였으며, 비특권 실행은 errno 13으로 실패했습니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

DMA-BUF 접근 기록은 공식 cam이 아니라 별도 프로브 `dmabuf-probe-2`에서 나온 것입니다. 프로브는 allocate에서 `backing_fd` 4, `dmabuf_fd` 5, 크기 4096을 기록했고, mmap 후 `sync-start`(flags 3), cpu-access 4096바이트, `sync-end`(flags 7), munmap, close-dmabuf, close-backing, close-provider를 모두 결과 0으로 남겼습니다. 기록에 `SYNC_START`와 `SYNC_END`라는 이름은 없고, 이벤트 이름은 `sync-start`와 `sync-end`입니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

실행 확인 항목: 이 구성은 `simulation`이 true로 표시된 가상의 시험 구성이며 실제 제품이 아닙니다. 관측은 GDB 아래에서 이루어졌고, GDB 중단점이 타이밍에 영향을 준다고 기록되어 있습니다. 물리 DMA는 `not-validated`, 물리 카메라·운영 응용·내부 HAL은 `not-run`이며, 사람 검토는 `pending`이고 제품 가용성은 `unknown`입니다. 취소 분기는 동적으로 실행되지 않았고, 관측된 `cancelled_callbacks` 0은 강제된 결과가 아니라고 기록되어 있습니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

근거 원문: [product-evidence/libcamera-official-cam-trial/execution-contract.txt:1](#source-6722470b9620a771) · [product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1](#source-dd657648532f01f5)

## 콜백과 후속 처리에서 확인한 세 프레임

**가상 시험 구성입니다. 실제 제품의 지원·성능 주장으로 사용하지 마세요.**

`CameraSession::requestComplete`는 요청 상태가 RequestCancelled이면 아무 작업 없이 반환합니다. 그 밖의 완료 요청은 `EventLoop::instance()`->callLater로 processRequest 호출을 이벤트 루프에 미뤄, 카메라 매니저 스레드가 막히지 않도록 합니다. processRequest는 캡처 한도에 도달했으면 바로 반환하고, 그렇지 않으면 프레임 정보를 출력한 뒤 `captureCount_`를 증가시킵니다. 관찰점은 processRequest 함수 안에서 `captureCount_` 증가 직전입니다. `src/apps/cam/camera_session.cpp:458`, `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

측정 자료에서 세 독립 프로세스(pid 434, 449, 464) 각각의 callback-entry와 frame-processed 이벤트는 같은 request 주소와 sequence(0, 1, 2)로 짝지어지므로, 프로세스마다 세 프레임이 한 번씩 집계됩니다. `Request` 상태 enum은 RequestPending, RequestComplete, RequestCancelled 순으로 선언되고 숫자 값이 명시되지 않으므로, 실제 status 1은 둘째 항목인 RequestComplete에 대응합니다. callbacks 스레드의 TID는 437, 452, 467이고, `main_tid`와 processed 스레드의 TID는 434, 449, 464입니다. 성공 버퍼 상태(`buffer_status` 0)인 `buffer_sequence` 0, 1, 2는 `successful_buffer_sequences` 0, 1, 2와 일치합니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`, `include/libcamera/request.h:34`

실행 확인 항목: 취소 0건(`cancelled_callbacks` 0)은 이번 관찰값이며, 취소 분기는 동적으로 실행되지 않았으므로 관찰 0건은 강제된 결과가 아닙니다. 콜백 반환 명령은 관찰되지 않았으므로 이 측정은 취소 경로, 반환 명령, 성능에 대한 검증이 아닙니다. GDB 중단점이 타이밍에 영향을 준다는 관찰 한계가 있으며, 결과는 소스 293d751a814e0d4c34e85ad457ccd9d5eefd1a61, WSL2 커스텀 UDMABUF 커널, Virtual2 400x300 NV12 구성에만 해당하고 물리 DMA, 물리 카메라, 다른 운영 응용, 내부 HAL은 검증되지 않았습니다. 이 구성은 시뮬레이션 기반의 가상 시험 구성이며 실제 제품이 아닙니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

근거 원문: [src/apps/cam/camera_session.cpp:458](#source-6b5bd0b09b7f63ff) · [include/libcamera/request.h:34](#source-2f743f0ec1bd4560) · [product-evidence/libcamera-official-cam-trial/execution-contract.txt:1](#source-6722470b9620a771) · [product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1](#source-dd657648532f01f5)

## 재현 조건과 검증 경계

**가상 시험 구성입니다. 실제 제품의 지원·성능 주장으로 사용하지 마세요.**

사전 점검에서 UDMABUF와 DMA-BUF heap이 없던 기본 WSL2 커널 대신, 사용자 승인 후 Microsoft 태그 linux-msft-wsl-6.18.33.2의 정확한 UDMABUF 내장 시험 커널을 임시로 적용했습니다. GCC 13.2에서 Ubuntu GCC 15.2로의 compiler capability 차이와 binutils 2.41에서 2.46, pahole 1.25에서 1.31로의 차이는 전체 diff로 보존했고, 새 release용 모듈을 설치하지 않아 시험 중 Docker는 중지 상태로 두었습니다. UDMABUF 장치는 root 전용이어서 권한을 바꾸지 않고 root 자식 프로세스로 실행했으며, 일반 사용자 실행의 errno 13 실패도 보존했습니다. 이 구성은 시뮬레이션된 Virtual2 400x300 NV12 시험 설정이며, 실제 제품이 아니라 시뮬레이션 시험 구성입니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

실행 확인 항목: 기본 WSL2 커널로 원복된 뒤에는 UDMABUF 할당기가 없으므로, 재현 명령을 실행하기 전에 별도로 승인된 지원 커널을 준비하고 부팅한 뒤 장치 접근을 먼저 확인해야 합니다. 과거 시험의 승인은 미래의 새 호스트 변경 승인이 아니며, 공유 커널·모듈·.wslconfig 변경이나 WSL 배포판·VM 종료는 실행 직전에 별도 승인을 받아야 합니다. 기존 PR 병합과 Pages 배포 승인은 이런 호스트 변경의 승인으로 확대되지 않으며, 이 전제는 실행 계약 근거에 따릅니다. `product-evidence/libcamera-official-cam-trial/execution-contract.txt:1`

전용 부정 시험에서 부재 제공자는 errno 2로, 미지원 ioctl은 errno 25로 실패했으며 두 경우 모두 종료 코드 1이 기록되었습니다. 0.5초 시간 초과 시험도 `timed_out` 값이 true로 기록되어 실패 판정이 보존되었습니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

같은 0.5초 시간 초과 시험에서 `SYNC_END` 반환값 0, munmap 반환값 0, fd 닫기 반환값 0 세 건이 기록되었고 프로세스 그룹도 남지 않았습니다. 이는 시간 초과 실패 판정과 별개로 자원 정리가 성공했음을 뜻하며, 닫기 반환값 0은 성공을 뜻할 뿐 닫기가 0건이었다는 뜻이 아닙니다. 추가 공식 cam strace는 종료 코드 0으로 정상 종료했지만, `callback_observation` 값이 false로 기록되어 콜백 관찰과 별도입니다. 이 구성은 실제 제품이 아닌 가상 시험 구성입니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

임시 .wslconfig를 제거하고 커널을 원복한 결과, 실행 후 커널은 사전 시험 커널과 같은 6.18.33.2-microsoft-standard-WSL2이며 .wslconfig 파일은 존재하지 않습니다. 이 결과는 소스 293d751a814e0d4c34e85ad457ccd9d5eefd1a61 기준의 WSL2 맞춤 UDMABUF 커널, 루트 자식 프로세스, Virtual2 400x300 NV12 구성에서 얻은 것입니다. 이 구성은 시뮬레이션된 가상 테스트 구성이며 실제 제품이 아닙니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

실행 확인 항목: 물리 DMA, 물리 카메라, 다른 제품 애플리케이션, 사내 HAL, 사람 승인(`human_review`: pending)은 미검증 상태입니다. GDB 중단점 관찰은 타이밍에 영향을 주며, 콜백 반환 명령은 관찰하지 않았습니다. `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`

근거 원문: [product-evidence/libcamera-official-cam-trial/execution-contract.txt:1](#source-6722470b9620a771) · [product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1](#source-dd657648532f01f5)

??? note "설계 질문과 검증 범위"
    질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.
    
    | 설계 질문 | 설명 위치 | 확인 범위 |
    |---|---|---|
    | 어떤 WSL 환경에서 공식 cam의 캡처와 실제 DMA-BUF 접근을 확인했습니까? | [공식 cam과 실제 DMA-BUF 확인 결과](#공식-cam과-실제-dma-buf-확인-결과) | 코드 근거와 설명 연결 · 실행 확인 항목 별도 |
    | 콜백 진입과 후속 처리를 어떻게 구분해 세 프레임과 실행 스레드를 확인했습니까? | [콜백과 후속 처리에서 확인한 세 프레임](#콜백과-후속-처리에서-확인한-세-프레임) | 코드 근거와 설명 연결 · 실행 확인 항목 별도 |
    | 재현할 때 필요한 권한·커널 조건과 시간 초과·복구 결과, 검증하지 않은 범위는 무엇입니까? | [재현 조건과 검증 경계](#재현-조건과-검증-경계) | 코드 근거와 설명 연결 · 실행 확인 항목 별도 |

## 소스 근거

같은 발췌는 한 번만 싣습니다. 필요한 원문을 펼쳐 설명과 대조하세요.

<a id="source-6722470b9620a771"></a>

??? note "제품 자료: product-evidence/libcamera-official-cam-trial/execution-contract.txt:1"
    소스와 별도로 제공된 자료입니다. 제공자·버전·적용 범위를 아래 기록에서 확인하세요. 자동 검사는 사람 승인이 아닙니다.
    
    `product-evidence/libcamera-official-cam-trial/execution-contract.txt:1`에서 시작하는 발췌입니다. 종료 줄은 9이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `fe1292511ffbf64b3e2aaee046d28048675c0283b82187cfa421e0431c834e0d`
    
    ```text
    {
      "url": "https://github.com/TTolsun/camera-hal-sdd-generator/issues/211",
      "updated_at": "2026-10-31T06:00:33Z",
      "verbatim_contract_lines": [
        "1. 선택한 커널의 Kconfig·의존성·실제 사용 가능한 모듈·할당기 후보를 조사하고 하나를 선택합니다. 기존 WSL에 새 배포판을 추가하는 것만으로 커널이 격리된다고 취급하지 않습니다.",
        "2. 기존 WSL/Docker에 영향을 주지 않는 시험 환경을 우선합니다. 현재 호스트의 공유 커널·모듈·.wslconfig를 변경하거나 배포판/VM을 종료해야 하면 영향과 복구 절차를 먼저 구체화하고 실행 직전에 별도 승인을 받습니다. 기존 PR 병합·Pages 배포 승인을 이런 호스트 변경의 승인으로 확대하지 않습니다."
      ]
    }
    
    ```
    
    ```json
    {
      "type": "project-document",
      "supplier": "GitHub issue211 execution contract, verbatim selected lines",
      "version": "2026-10-31T06:00:33Z",
      "date": "2026-10-31",
      "valid_until": "2026-10-31",
      "product": "libcamera-official-cam-trial",
      "release": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
      "configuration": "wsl2-virtual2-official-cam-udmabuf",
      "feature": "wsl-virtual-capture",
      "conditions": [
        "Source 293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
        "WSL2 custom UDMABUF kernel, root child, Virtual2 400x300 NV12",
        "GDB observation; no timing/return/physical/internal HAL qualification"
      ],
      "sha256": "fe1292511ffbf64b3e2aaee046d28048675c0283b82187cfa421e0431c834e0d"
    }
    ```

<a id="source-dd657648532f01f5"></a>

??? note "제품 자료: product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1"
    소스와 별도로 제공된 자료입니다. 제공자·버전·적용 범위를 아래 기록에서 확인하세요. 자동 검사는 사람 승인이 아닙니다.
    
    `product-evidence/libcamera-official-cam-trial/official-cam-run.txt:1`에서 시작하는 발췌입니다. 종료 줄은 608이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `6724319768e46327e26f324d536ccaf22e9b71852e055a7b3c91318f0c11a7f1`
    
    ```text
    {
      "source_commit": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
      "kernel": "6.18.33.2-microsoft-standard-WSL2-issue211",
      "results": [
        {
          "completed_frames": 3,
          "cancelled_callbacks": 0,
          "observed_tids": [
            434,
            437
          ],
          "successful_buffer_sequences": [
            0,
            1,
            2
          ],
          "pid": 434,
          "allocations": 4
        },
        {
          "completed_frames": 3,
          "cancelled_callbacks": 0,
          "observed_tids": [
            449,
            452
          ],
          "successful_buffer_sequences": [
            0,
            1,
            2
          ],
          "pid": 449,
          "allocations": 4
        },
        {
          "completed_frames": 3,
          "cancelled_callbacks": 0,
          "observed_tids": [
            464,
            467
          ],
          "successful_buffer_sequences": [
            0,
            1,
            2
          ],
          "pid": 464,
          "allocations": 4
        }
      ],
      "uid": 0,
      "gid": 0,
      "binaries": {
        "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/apps/cam/cam": "1ceed18da065a383e2f573ba49e9caea77033abd6830a7ec051e3681dabc79d2",
        "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/libcamera.so": "2423e936a6ffde0fa533c76a4738f748f77b4535c881c12a616dfeec50a940eb",
        "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/base/libcamera-base.so": "441f04294e61632d080f4bb55fb38ce787bb8af173a4b6d55d7c05f0f04fd18c",
        "/home/baboess/.cache/issue211-runtime-D6sfkcnF/dmabuf-probe-2": "531e499f094cca32f03e354afe2aa5a8d48b425916cbd7be2ad7e02306c58512"
      },
      "human_review": "pending",
      "physical_dma": "not-validated",
      "physical_camera": "not-run",
      "production_application": "not-run",
      "internal_hal": "not-run",
      "status": "observed-wsl-virtual-only",
      "schema": 1,
      "camera": "Virtual2",
      "applied_configuration": "(0) 400x300-NV12/SMPTE170M",
      "official_source_tracked_clean": true,
      "kernel_tag": "linux-msft-wsl-6.18.33.2",
      "kernel_tag_commit": "c21a03b2943d147c280bdf32530d4fe6badfd6bd",
      "kernel_sha256": "cf23bf492a00a5c7517e221b0d8f742ea3cffa9351823191a5ba5c476ba15460",
      "compiler_config_diff": "GCC 13.2 to Ubuntu GCC 15.2 capability changes, binutils 2.41 to 2.46, pahole 1.25 to 1.31; full diff preserved",
      "matching_modules_installed": false,
      "docker_during_trial": "stopped",
      "allocator": "udmabuf built-in, /dev/udmabuf root-only; permissions unchanged",
      "unprivileged_run": {
        "status": "failed",
        "errno": 13
      },
      "dma_probe_events": [
        {
          "event": "provider-open",
          "provider": "/dev/udmabuf",
          "result": 3,
          "errno": 0
        },
        {
          "event": "allocate",
          "result": 5,
          "errno": 0,
          "backing_fd": 4,
          "dmabuf_fd": 5,
          "size": 4096
        },
        {
          "event": "mmap",
          "result": 0,
          "errno": 0
        },
        {
          "event": "sync-start",
          "result": 0,
          "errno": 0,
          "flags": 3,
          "retry": false
        },
        {
          "event": "cpu-access",
          "result": 0,
          "errno": 0,
          "bytes": 4096,
          "checksum": 522240
        },
        {
          "event": "sync-end",
          "result": 0,
          "errno": 0,
          "flags": 7,
          "retry": false
        },
        {
          "event": "munmap",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-dmabuf",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-backing",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-provider",
          "result": 0,
          "errno": 0
        }
      ],
      "run_threads": [
        {
          "pid": 434,
          "callbacks": [
            437
          ],
          "processed": [
            434
          ]
        },
        {
          "pid": 449,
          "callbacks": [
            452
          ],
          "processed": [
            449
          ]
        },
        {
          "pid": 464,
          "callbacks": [
            467
          ],
          "processed": [
            464
          ]
        }
      ],
      "inferior_exit_codes": [
        0,
        0,
        0
      ],
      "processed_sequences": [
        [
          0,
          1,
          2
        ],
        [
          0,
          1,
          2
        ],
        [
          0,
          1,
          2
        ]
      ],
      "timeout_probe": {
        "seconds": 0.5,
        "timed_out": true,
        "exit_code": 1,
        "sync_end_return_code": 0,
        "munmap_return_code": 0,
        "close_return_codes": [
          0,
          0,
          0
        ],
        "process_group_absent": true
      },
      "negative_probes": {
        "absent_provider_errno": 2,
        "unsupported_ioctl_errno": 25,
        "exit_codes": [
          1,
          1
        ]
      },
      "supplemental_official_cam_strace": {
        "exit_code": 0,
        "callback_observation": false
      },
      "restored_kernel": "6.18.33.2-microsoft-standard-WSL2",
      "restored_wslconfig_exists": false,
      "old_cpu_probe": {
        "callbacks": 72,
        "dma": "unvalidated-provider-and-sync-errors-retained",
        "history_unchanged": true
      },
      "observation_limits": [
        "GDB breakpoints affect timing",
        "No callback-return instruction observation",
        "Cancellation branch not dynamically exercised; observed count 0 is not forced"
      ],
      "reproduction_code": "https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/examples/libcamera/runtime/run_cam.py",
      "raw_evidence": "https://github.com/TTolsun/camera-hal-sdd-generator/tree/main/examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3",
      "buffer_metadata": [
        [
          {
            "buffer_sequence": 0,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 434,
            "point": "buffer-metadata",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 434
          },
          {
            "buffer_sequence": 1,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 434,
            "point": "buffer-metadata",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 434
          },
          {
            "buffer_sequence": 2,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 434,
            "point": "buffer-metadata",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 434
          }
        ],
        [
          {
            "buffer_sequence": 0,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 449,
            "point": "buffer-metadata",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 449
          },
          {
            "buffer_sequence": 1,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 449,
            "point": "buffer-metadata",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 449
          },
          {
            "buffer_sequence": 2,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 449,
            "point": "buffer-metadata",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 449
          }
        ],
        [
          {
            "buffer_sequence": 0,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 464,
            "point": "buffer-metadata",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 464
          },
          {
            "buffer_sequence": 1,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 464,
            "point": "buffer-metadata",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 464
          },
          {
            "buffer_sequence": 2,
            "buffer_status": 0,
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
            "pid": 464,
            "point": "buffer-metadata",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 464
          }
        ]
      ],
      "pretrial_kernel": "6.18.33.2-microsoft-standard-WSL2",
      "pretrial_udmabuf": false,
      "pretrial_dmabuf_heaps": false,
      "pretrial_provider_devices_present": false,
      "source_unmodified": true,
      "kernel_trial_authorized_by_user": true,
      "request_events": [
        [
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 434,
            "point": "callback-entry",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 437
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 434,
            "point": "callback-entry",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 437
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 434,
            "point": "frame-processed",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 434
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 434,
            "point": "callback-entry",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 437
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 434,
            "point": "frame-processed",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 434
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 434,
            "point": "frame-processed",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 434
          }
        ],
        [
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 449,
            "point": "callback-entry",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 452
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 449,
            "point": "callback-entry",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 452
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 449,
            "point": "frame-processed",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 449
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 449,
            "point": "callback-entry",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 452
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 449,
            "point": "frame-processed",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 449
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 449,
            "point": "frame-processed",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 449
          }
        ],
        [
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 464,
            "point": "callback-entry",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 467
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 464,
            "point": "callback-entry",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 467
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 464,
            "point": "frame-processed",
            "request": "0x5555556794f0",
            "sequence": 0,
            "status": 1,
            "tid": 464
          },
          {
            "cookie": 0,
            "location": "CameraSession::requestComplete",
            "pid": 464,
            "point": "callback-entry",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 467
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 464,
            "point": "frame-processed",
            "request": "0x5555556793b0",
            "sequence": 1,
            "status": 1,
            "tid": 464
          },
          {
            "cookie": 0,
            "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
            "pid": 464,
            "point": "frame-processed",
            "request": "0x555555679450",
            "sequence": 2,
            "status": 1,
            "tid": 464
          }
        ]
      ],
      "main_tid": [
        434,
        449,
        464
      ],
      "observation_points": {
        "callback-entry": "CameraSession::requestComplete entry",
        "frame-processed": "CameraSession::processRequest immediately before captureCount_++",
        "buffer-metadata": "CameraSession::processRequest after reading FrameMetadata"
      },
      "timeout_cleanup_events": [
        {
          "event": "provider-open",
          "provider": "/dev/udmabuf",
          "result": 3,
          "errno": 0
        },
        {
          "event": "allocate",
          "result": 5,
          "errno": 0,
          "backing_fd": 4,
          "dmabuf_fd": 5,
          "size": 4096
        },
        {
          "event": "mmap",
          "result": 0,
          "errno": 0
        },
        {
          "event": "sync-start",
          "result": 0,
          "errno": 0,
          "flags": 3,
          "retry": false
        },
        {
          "event": "sync-end",
          "result": 0,
          "errno": 0,
          "flags": 7,
          "retry": false
        },
        {
          "event": "munmap",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-dmabuf",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-backing",
          "result": 0,
          "errno": 0
        },
        {
          "event": "close-provider",
          "result": 0,
          "errno": 0
        }
      ]
    }
    
    ```
    
    ```json
    {
      "type": "measurement",
      "supplier": "Source-pinned official cam trial; raw events, GDB, syscall and cleanup records",
      "version": "051c8bd9f7c693a474384fa63c96dcfaa0e80cd83506b375e2f89193e6a25b91",
      "date": "2026-10-31",
      "valid_until": "2026-10-31",
      "product": "libcamera-official-cam-trial",
      "release": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
      "configuration": "wsl2-virtual2-official-cam-udmabuf",
      "feature": "wsl-virtual-capture",
      "conditions": [
        "Source 293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
        "WSL2 custom UDMABUF kernel, root child, Virtual2 400x300 NV12",
        "GDB observation; no timing/return/physical/internal HAL qualification"
      ],
      "sha256": "6724319768e46327e26f324d536ccaf22e9b71852e055a7b3c91318f0c11a7f1"
    }
    ```

<a id="source-6b5bd0b09b7f63ff"></a>

??? note "소스 근거: src/apps/cam/camera_session.cpp:458"
    `src/apps/cam/camera_session.cpp:458`에서 시작하는 발췌입니다. 종료 줄은 552이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `1cc65de3cbc313bb70f938f939d3d99420f17526290c216b538bbf117adbfd6d`
    
    ```text
    void CameraSession::requestComplete(Request *request)
    {
    	if (request->status() == Request::RequestCancelled)
    		return;
    
    	/*
    	 * Defer processing of the completed request to the event loop, to avoid
    	 * blocking the camera manager thread.
    	 */
    	EventLoop::instance()->callLater([this, request]() { processRequest(request); });
    }
    
    void CameraSession::processRequest(Request *request)
    {
    	/*
    	 * If we've reached the capture limit, we're done. This doesn't
    	 * duplicate the check below that emits the captureDone signal, as this
    	 * function will be called for each request still in flight after the
    	 * capture limit is reached and we don't want to emit the signal every
    	 * single time.
    	 */
    	if (captureLimit_ && captureCount_ >= captureLimit_)
    		return;
    
    	const Request::BufferMap &buffers = request->buffers();
    
    	/*
    	 * Compute the frame rate. The timestamp is arbitrarily retrieved from
    	 * the first buffer, as all buffers should have matching timestamps.
    	 */
    	uint64_t ts = buffers.begin()->second->metadata().timestamp;
    	double fps = ts - last_;
    	fps = last_ != 0 && fps ? 1000000000.0 / fps : 0.0;
    	last_ = ts;
    
    	bool requeue = true;
    
    	std::stringstream info;
    	info << ts / 1000000000 << "."
    	     << std::setw(6) << std::setfill('0') << ts / 1000 % 1000000
    	     << " (" << std::fixed << std::setprecision(2) << fps << " fps)";
    
    	for (const auto &[stream, buffer] : buffers) {
    		const FrameMetadata &metadata = buffer->metadata();
    
    		info << " " << streamNames_[stream]
    		     << " seq: " << std::setw(6) << std::setfill('0') << metadata.sequence
    		     << " bytesused: ";
    
    		unsigned int nplane = 0;
    		for (const FrameMetadata::Plane &plane : metadata.planes()) {
    			info << plane.bytesused;
    			if (++nplane < metadata.planes().size())
    				info << "/";
    		}
    	}
    
    	if (sink_) {
    		if (!sink_->processRequest(request))
    			requeue = false;
    	}
    
    	std::cout << info.str() << std::endl;
    
    	if (printMetadata_) {
    		const ControlList &requestMetadata = request->metadata();
    		for (const auto &[key, value] : requestMetadata) {
    			const ControlId *id = controls::controls.at(key);
    			std::cout << "\t" << id->name() << " = "
    				  << value.toString() << std::endl;
    		}
    	}
    
    	/*
    	 * Notify the user that capture is complete if the limit has just been
    	 * reached.
    	 */
    	captureCount_++;
    	if (captureLimit_ && captureCount_ >= captureLimit_) {
    		captureDone.emit();
    		return;
    	}
    
    	/*
    	 * If the frame sink holds on the request, we'll requeue it later in the
    	 * complete handler.
    	 */
    	if (!requeue)
    		return;
    
    	request->reuse(Request::ReuseBuffers);
    	queueRequest(request);
    }
    
    void CameraSession::sinkRelease(Request *request)
    ```

<a id="source-2f743f0ec1bd4560"></a>

??? note "소스 근거: include/libcamera/request.h:34"
    `include/libcamera/request.h:34`에서 시작하는 발췌입니다. 종료 줄은 38이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `ef4aa440cefbe5629113672961902a8a7c541797d19f05fa7cad90fe97030a3d`
    
    ```text
    enum Status {
    		RequestPending,
    		RequestComplete,
    		RequestCancelled,
    	};
    ```

??? note "근거와 검토 정보"
    - 생성 방식: 추출 사실과 LLM 설명
    - 검증 범위: 표·그림은 facts로 만들고 설명은 LLM이 작성합니다. 인용·문장 및 설정된 구조 검사를 적용합니다.
    - 근거 파일: `include/libcamera/request.h`, `product-evidence/libcamera-official-cam-trial/execution-contract.txt`, `product-evidence/libcamera-official-cam-trial/official-cam-run.txt`, `src/apps/cam/camera_session.cpp`
    - 근거 수준: 코드 확인 (정적 분석, simple_compdb 구성, commit `293d751a81`)
    - 자동 검사 (인용·문장 및 설정된 구조 검사): 통과
    - 검토 상태 기록일: 2026-10-31 · 사람 검토 전

다음 단계: [공식 cam 재현 절차](https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/examples/libcamera/runtime/OFFICIAL_CAM.md)

PUBLIC MEASUREMENT MATERIAL
{
  "source_commit": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
  "kernel": "6.18.33.2-microsoft-standard-WSL2-issue211",
  "results": [
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        434,
        437
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 434,
      "allocations": 4
    },
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        449,
        452
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 449,
      "allocations": 4
    },
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        464,
        467
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 464,
      "allocations": 4
    }
  ],
  "uid": 0,
  "gid": 0,
  "binaries": {
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/apps/cam/cam": "1ceed18da065a383e2f573ba49e9caea77033abd6830a7ec051e3681dabc79d2",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/libcamera.so": "2423e936a6ffde0fa533c76a4738f748f77b4535c881c12a616dfeec50a940eb",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/base/libcamera-base.so": "441f04294e61632d080f4bb55fb38ce787bb8af173a4b6d55d7c05f0f04fd18c",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/dmabuf-probe-2": "531e499f094cca32f03e354afe2aa5a8d48b425916cbd7be2ad7e02306c58512"
  },
  "human_review": "pending",
  "physical_dma": "not-validated",
  "physical_camera": "not-run",
  "production_application": "not-run",
  "internal_hal": "not-run",
  "status": "observed-wsl-virtual-only",
  "schema": 1,
  "camera": "Virtual2",
  "applied_configuration": "(0) 400x300-NV12/SMPTE170M",
  "official_source_tracked_clean": true,
  "kernel_tag": "linux-msft-wsl-6.18.33.2",
  "kernel_tag_commit": "c21a03b2943d147c280bdf32530d4fe6badfd6bd",
  "kernel_sha256": "cf23bf492a00a5c7517e221b0d8f742ea3cffa9351823191a5ba5c476ba15460",
  "compiler_config_diff": "GCC 13.2 to Ubuntu GCC 15.2 capability changes, binutils 2.41 to 2.46, pahole 1.25 to 1.31; full diff preserved",
  "matching_modules_installed": false,
  "docker_during_trial": "stopped",
  "allocator": "udmabuf built-in, /dev/udmabuf root-only; permissions unchanged",
  "unprivileged_run": {
    "status": "failed",
    "errno": 13
  },
  "dma_probe_events": [
    {
      "event": "provider-open",
      "provider": "/dev/udmabuf",
      "result": 3,
      "errno": 0
    },
    {
      "event": "allocate",
      "result": 5,
      "errno": 0,
      "backing_fd": 4,
      "dmabuf_fd": 5,
      "size": 4096
    },
    {
      "event": "mmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "sync-start",
      "result": 0,
      "errno": 0,
      "flags": 3,
      "retry": false
    },
    {
      "event": "cpu-access",
      "result": 0,
      "errno": 0,
      "bytes": 4096,
      "checksum": 522240
    },
    {
      "event": "sync-end",
      "result": 0,
      "errno": 0,
      "flags": 7,
      "retry": false
    },
    {
      "event": "munmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-dmabuf",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-backing",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-provider",
      "result": 0,
      "errno": 0
    }
  ],
  "run_threads": [
    {
      "pid": 434,
      "callbacks": [
        437
      ],
      "processed": [
        434
      ]
    },
    {
      "pid": 449,
      "callbacks": [
        452
      ],
      "processed": [
        449
      ]
    },
    {
      "pid": 464,
      "callbacks": [
        467
      ],
      "processed": [
        464
      ]
    }
  ],
  "inferior_exit_codes": [
    0,
    0,
    0
  ],
  "processed_sequences": [
    [
      0,
      1,
      2
    ],
    [
      0,
      1,
      2
    ],
    [
      0,
      1,
      2
    ]
  ],
  "timeout_probe": {
    "seconds": 0.5,
    "timed_out": true,
    "exit_code": 1,
    "sync_end_return_code": 0,
    "munmap_return_code": 0,
    "close_return_codes": [
      0,
      0,
      0
    ],
    "process_group_absent": true
  },
  "negative_probes": {
    "absent_provider_errno": 2,
    "unsupported_ioctl_errno": 25,
    "exit_codes": [
      1,
      1
    ]
  },
  "supplemental_official_cam_strace": {
    "exit_code": 0,
    "callback_observation": false
  },
  "restored_kernel": "6.18.33.2-microsoft-standard-WSL2",
  "restored_wslconfig_exists": false,
  "old_cpu_probe": {
    "callbacks": 72,
    "dma": "unvalidated-provider-and-sync-errors-retained",
    "history_unchanged": true
  },
  "observation_limits": [
    "GDB breakpoints affect timing",
    "No callback-return instruction observation",
    "Cancellation branch not dynamically exercised; observed count 0 is not forced"
  ],
  "reproduction_code": "https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/examples/libcamera/runtime/run_cam.py",
  "raw_evidence": "https://github.com/TTolsun/camera-hal-sdd-generator/tree/main/examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3",
  "buffer_metadata": [
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 434
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 434
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 434
      }
    ],
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 449
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 449
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 449
      }
    ],
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 464
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 464
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 464
      }
    ]
  ],
  "pretrial_kernel": "6.18.33.2-microsoft-standard-WSL2",
  "pretrial_udmabuf": false,
  "pretrial_dmabuf_heaps": false,
  "pretrial_provider_devices_present": false,
  "source_unmodified": true,
  "kernel_trial_authorized_by_user": true,
  "request_events": [
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 434
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 434
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 434
      }
    ],
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 449
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 449
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 449
      }
    ],
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 464
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 464
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 464
      }
    ]
  ],
  "main_tid": [
    434,
    449,
    464
  ],
  "observation_points": {
    "callback-entry": "CameraSession::requestComplete entry",
    "frame-processed": "CameraSession::processRequest immediately before captureCount_++",
    "buffer-metadata": "CameraSession::processRequest after reading FrameMetadata"
  },
  "timeout_cleanup_events": [
    {
      "event": "provider-open",
      "provider": "/dev/udmabuf",
      "result": 3,
      "errno": 0
    },
    {
      "event": "allocate",
      "result": 5,
      "errno": 0,
      "backing_fd": 4,
      "dmabuf_fd": 5,
      "size": 4096
    },
    {
      "event": "mmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "sync-start",
      "result": 0,
      "errno": 0,
      "flags": 3,
      "retry": false
    },
    {
      "event": "sync-end",
      "result": 0,
      "errno": 0,
      "flags": 7,
      "retry": false
    },
    {
      "event": "munmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-dmabuf",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-backing",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-provider",
      "result": 0,
      "errno": 0
    }
  ]
}

PINNED PROJECT SOURCE WINDOWS
{"official-cam-validation/completion/callback-and-processing": {"commit": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61", "selector": {"id": "callback-and-processing", "file": "src/apps/cam/camera_session.cpp", "start": "void CameraSession::requestComplete(Request *request)", "end": "void CameraSession::sinkRelease(Request *request)"}, "status": "available", "file": "src/apps/cam/camera_session.cpp", "line": 458, "end_line": 552, "text": "void CameraSession::requestComplete(Request *request)\n{\n\tif (request->status() == Request::RequestCancelled)\n\t\treturn;\n\n\t/*\n\t * Defer processing of the completed request to the event loop, to avoid\n\t * blocking the camera manager thread.\n\t */\n\tEventLoop::instance()->callLater([this, request]() { processRequest(request); });\n}\n\nvoid CameraSession::processRequest(Request *request)\n{\n\t/*\n\t * If we've reached the capture limit, we're done. This doesn't\n\t * duplicate the check below that emits the captureDone signal, as this\n\t * function will be called for each request still in flight after the\n\t * capture limit is reached and we don't want to emit the signal every\n\t * single time.\n\t */\n\tif (captureLimit_ && captureCount_ >= captureLimit_)\n\t\treturn;\n\n\tconst Request::BufferMap &buffers = request->buffers();\n\n\t/*\n\t * Compute the frame rate. The timestamp is arbitrarily retrieved from\n\t * the first buffer, as all buffers should have matching timestamps.\n\t */\n\tuint64_t ts = buffers.begin()->second->metadata().timestamp;\n\tdouble fps = ts - last_;\n\tfps = last_ != 0 && fps ? 1000000000.0 / fps : 0.0;\n\tlast_ = ts;\n\n\tbool requeue = true;\n\n\tstd::stringstream info;\n\tinfo << ts / 1000000000 << \".\"\n\t     << std::setw(6) << std::setfill('0') << ts / 1000 % 1000000\n\t     << \" (\" << std::fixed << std::setprecision(2) << fps << \" fps)\";\n\n\tfor (const auto &[stream, buffer] : buffers) {\n\t\tconst FrameMetadata &metadata = buffer->metadata();\n\n\t\tinfo << \" \" << streamNames_[stream]\n\t\t     << \" seq: \" << std::setw(6) << std::setfill('0') << metadata.sequence\n\t\t     << \" bytesused: \";\n\n\t\tunsigned int nplane = 0;\n\t\tfor (const FrameMetadata::Plane &plane : metadata.planes()) {\n\t\t\tinfo << plane.bytesused;\n\t\t\tif (++nplane < metadata.planes().size())\n\t\t\t\tinfo << \"/\";\n\t\t}\n\t}\n\n\tif (sink_) {\n\t\tif (!sink_->processRequest(request))\n\t\t\trequeue = false;\n\t}\n\n\tstd::cout << info.str() << std::endl;\n\n\tif (printMetadata_) {\n\t\tconst ControlList &requestMetadata = request->metadata();\n\t\tfor (const auto &[key, value] : requestMetadata) {\n\t\t\tconst ControlId *id = controls::controls.at(key);\n\t\t\tstd::cout << \"\\t\" << id->name() << \" = \"\n\t\t\t\t  << value.toString() << std::endl;\n\t\t}\n\t}\n\n\t/*\n\t * Notify the user that capture is complete if the limit has just been\n\t * reached.\n\t */\n\tcaptureCount_++;\n\tif (captureLimit_ && captureCount_ >= captureLimit_) {\n\t\tcaptureDone.emit();\n\t\treturn;\n\t}\n\n\t/*\n\t * If the frame sink holds on the request, we'll requeue it later in the\n\t * complete handler.\n\t */\n\tif (!requeue)\n\t\treturn;\n\n\trequest->reuse(Request::ReuseBuffers);\n\tqueueRequest(request);\n}\n\nvoid CameraSession::sinkRelease(Request *request)", "sha256": "1cc65de3cbc313bb70f938f939d3d99420f17526290c216b538bbf117adbfd6d", "whole_file": false}, "official-cam-validation/completion/request-status": {"commit": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61", "selector": {"id": "request-status", "file": "include/libcamera/request.h", "start": "enum Status {", "end": "\n\t};"}, "status": "available", "file": "include/libcamera/request.h", "line": 34, "end_line": 38, "text": "enum Status {\n\t\tRequestPending,\n\t\tRequestComplete,\n\t\tRequestCancelled,\n\t};", "sha256": "ef4aa440cefbe5629113672961902a8a7c541797d19f05fa7cad90fe97030a3d", "whole_file": false}}
VERBATIM ISSUE EXECUTION CONTRACT
{
  "url": "https://github.com/TTolsun/camera-hal-sdd-generator/issues/211",
  "updated_at": "2026-10-31T06:00:33Z",
  "verbatim_contract_lines": [
    "1. 선택한 커널의 Kconfig·의존성·실제 사용 가능한 모듈·할당기 후보를 조사하고 하나를 선택합니다. 기존 WSL에 새 배포판을 추가하는 것만으로 커널이 격리된다고 취급하지 않습니다.",
    "2. 기존 WSL/Docker에 영향을 주지 않는 시험 환경을 우선합니다. 현재 호스트의 공유 커널·모듈·.wslconfig를 변경하거나 배포판/VM을 종료해야 하면 영향과 복구 절차를 먼저 구체화하고 실행 직전에 별도 승인을 받습니다. 기존 PR 병합·Pages 배포 승인을 이런 호스트 변경의 승인으로 확대하지 않습니다."
  ]
}

ACTUAL LOADED PRODUCT CONFIGURATION (including virtual-test simulation marker)
{"id": "libcamera-official-cam-trial", "scope": "project", "release": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61", "configuration": "wsl2-virtual2-official-cam-udmabuf", "simulation": true, "as_of": "2026-10-31"}
