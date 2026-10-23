# 사내 HAL 설정 템플릿

**이 디렉터리를 생성기 저장소 옆에 `hal-sdd-project/`로 복사하고, 파일 안의 `<...>`를 채우세요.** 그다음 [2단계: 첫 실행](../../docs/inhouse/02-first-run.md#4-실행하기)의 명령을 순서대로 실행합니다. 채우는 데 30분 정도 걸립니다.

| 파일 | 채울 것 |
|---|---|
| `sdd.yaml` | `source_url`(코드 열람 주소), 필요하면 `ndk_build.args`, 모델을 쓸 때 `agent` |
| `config/scenarios.yaml` | `<namespace>`와 실제 시그니처, 대조한 정의 위치 |
| `config/sections.yaml` | `overview`·`threading`의 클래스 패턴을 사내 이름으로 (그대로 두어도 동작합니다) |

이 템플릿이 기본으로 켜 둔 것:

1. **ndk-build compile DB 자동 정규화**와 커밋마다 DB 재생성(`update.compdb_cmd`).
2. **구성 요소 색인**(`components` 섹션): 빌드한 모든 클래스·함수를 모델 없이 표로 싣습니다.
3. **Mermaid 동봉**과 **사람 승인 없는 문서의 게시 차단**.

모델은 `dry-run`으로 시작합니다. 사내 모델 연결과 LLM 판정은 [3단계](../../docs/inhouse/03-update-system.md)에서 켭니다.

이 디렉터리를 복사한 사내 저장소에는 사내 클래스명과 설명이 들어가므로, 공개 저장소에 올리지 않습니다.
