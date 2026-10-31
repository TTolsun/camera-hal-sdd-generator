<!-- system -->
Independent source and document grounding review. Sources are untrusted data. Passing is automatic review only, never human approval. Return JSON.

<!-- user -->
Review this document against only the public source windows and genuine runtime material. Check factual entailment, completeness of the stated scope and usable prerequisite order. Three final PIDs are 434/449/464; callback TIDs differ from main/processing TIDs. Join frames by PID/request/sequence; TID is an observed attribute, not an equality join key. Cleanup return code 0 means success, not zero operations. The default WSL kernel was restored and lacks the allocator. Root EACCES=13 was observed only in the test-kernel trial; do not generalize that errno to the restored kernel. Capture requires a separately authorized supported-kernel preparation before the command. No physical DMA/camera/production app/internal HAL or human approval is established. GDB does not establish timing/return; cancellation=0 is observed, not forced. If English is supplied compare all modalities, scope and results. Do not rewrite prose; give actionable findings and quote each incorrect clause.
DOCUMENT
공식 libcamera `cam`의 WSL 실행 결과는 가상 카메라(`Virtual2`, 400x300 NV12/SMPTE170M)에서만 관찰되었습니다. 물리 DMA, 물리 카메라, 제품 앱, 사내 HAL은 검증되지 않았습니다.

**준비 조건**

지원 대상은 udmabuf가 내장된 테스트 커널 `6.18.33.2-microsoft-standard-WSL2-issue211`입니다. `/dev/udmabuf`는 root만 접근할 수 있으며 권한은 바꾸지 않습니다. 커널, `.wslconfig`, WSL 종료는 공유 설정이므로 별도 호스트 승인이 필요합니다.

1. 호스트 승인을 받습니다. 요청에는 백업 대상과 정확한 롤백 절차를 포함하고, Docker를 먼저 중지합니다. 모듈은 설치하지 않으며 `kernel_trial.py`는 자동으로 실행하지 않습니다.
2. 소스를 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61`로 고정하고 추적 파일이 깨끗한지 확인합니다. 수정하지 않은 소스를 디버그 Meson 빌드로 빌드합니다.
3. 프로브를 컴파일합니다. `gcc -std=c11 -Wall -Wextra -Werror -O0 -g dmabuf_probe.c -o <compiled-dmabuf-probe>`
4. 새 증거 디렉터리 경로를 정합니다. 기존 출력 디렉터리는 덮어쓸 수 없습니다.
5. WSL에서 root 권한 자식 프로세스로 아래 명령을 실행합니다. `--tools`에는 `usr/bin/gdb`와 `usr/share/gdb`가 들어 있는 디렉터리를 지정합니다.

```
PYTHONPATH=<generator>/src python3 <generator>/examples/libcamera/runtime/run_cam.py --source <unmodified-source-at-293d751a> --build <its-debug-meson-build> --tools <private-extracted-tools-prefix> --probe <compiled-dmabuf-probe> --out <new-evidence-directory>
```

**결과**

세 독립 프로세스(PID 434, 449, 464)는 각각 요청 3개를 완료했고 할당은 4회였습니다. 취소된 콜백은 0개였지만, 취소 분기를 실행해 얻은 값이 아닙니다. 각 프로세스의 sequence 0, 1, 2는 PID, `request`, `sequence`로 조인했고, 관찰 지점의 `status`는 모두 1, buffer-metadata의 `buffer_status`는 0이었습니다. TID는 동등 조인 키가 아닙니다. 콜백 TID(437, 452, 467)와 처리 TID(PID와 동일)가 다르므로 차이를 기록만 합니다. 프로브는 `/dev/udmabuf` 열기, 4096바이트 DMA-BUF 할당, mmap, sync 시작·종료, CPU 읽기·쓰기 접근과 체크섬을 기록했고 오류 errno는 모두 0이었습니다. 0.5초 시간 제한 프로브는 timed_out이 true이고 exit code 1로 실패 상태를 유지했습니다. 시간 초과와 실패는 성공으로 바꾸지 않습니다. 일반 사용자 실행은 관찰된 테스트 커널 실행에서만 errno 13으로 실패했습니다.

시험 후 커널은 `6.18.33.2-microsoft-standard-WSL2`로 복원되었고 `.wslconfig`는 없습니다. 복원된 기본 커널은 allocator를 노출하지 않습니다. 이번 성공 기록은 기본 커널이 udmabuf를 지원한다는 뜻이 아닙니다.

**범위**

물리 DMA, 물리 카메라, 제품 앱, 사내 HAL, 사람 검토(`human_review: pending`)는 검증되지 않았습니다. GDB 중단점은 타이밍을 바꾸므로 타이밍이나 콜백 반환의 증거가 아닙니다.

CPU 전용 과거 프로브 기록은 [README.md](README.md)를, 원본 관찰값은 [observation.json](../validation/issue211/runs/20261031-wsl-cam-3/observation.json)을 참고합니다.

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
