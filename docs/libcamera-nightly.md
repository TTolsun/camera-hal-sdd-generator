# 공개 libcamera 야간 실행 상태

**공개 검증 환경에 매일 한국 시간 21시 실행을 등록했습니다.** 공통 기능은 `sdd automate`이며, 아래 로컬 배치 설정을 사내 운영 검증으로 간주하지 않습니다.

| 단계 | 현재 구성 |
|---|---|
| upstream 이력 보관 | `TTolsun/libcamera-sdd`의 `sync-upstream.yml`이 공식 GitLab master를 `upstream/master`로 fast-forward합니다. |
| 문서 갱신 | Windows 작업 `libcamera-SDD-nightly`가 WSL에서 `sdd automate`를 실행합니다. |
| 커밋 없는 날 | 기존 카메라 모델 범위에서 Hermes/QWEN으로 소스 창 하나를 점검합니다. 유효한 근거와 형식이 없으면 보류합니다. |
| 게시 | 전용 `automation/nightly-docs` 브랜치에 사이트를 커밋하고 PR을 생성·병합합니다. 자동 검사는 사람 승인으로 표시하지 않습니다. |
| 완료 확인 | 실제 Pages manifest와 모든 산출물 해시를 확인한 뒤 게시 성공을 기록합니다. |

로컬 배치 설정과 상태는 저장소의 `build/nightly-libcamera/`에 보관합니다. `sdd.yaml`, `sections.yaml`, `scenarios.yaml`, facts, 원고, `build/automation-state.json`, `build/idle-review-state.json`과 감사 기록을 함께 유지해야 합니다. 이 디렉터리는 환경별 운영 데이터이며 Git 추적 대상이 아닙니다.

시간을 바꾸려면 해당 PC에서 다음을 실행합니다. GitHub upstream 워크플로 시간은 별도로 UTC cron 값을 바꿉니다.

```powershell
./build/nightly-libcamera/register.ps1 -Time '23:30'
```

로그는 같은 디렉터리의 날짜별 `*.stdout.log`, `*.stderr.log`에서 확인합니다. 작업 스케줄러의 종료 코드 0과 게시 상태의 완료 기록을 함께 확인하세요. 스키마·근거 검증으로 보류한 누락 후보는 원본 문서를 유지하고 감사 기록에 남습니다.

이 배치는 로그인된 사용자의 WSL·Ollama·Hermes·GitHub 인증을 사용합니다. PC가 꺼져 있거나 로그아웃한 동안의 실행을 보증하지 않습니다. 놓친 예약은 실행 가능한 상태가 되면 다시 시작하도록 설정했습니다. 실행 중인 작업이 있으면 같은 예약을 중복 실행하지 않습니다.

다음 단계: [공통 예약 실행 설정](scheduled-publication.md)을 사내 저장소·빌드·배포 방식에 맞춰 구성하세요.
