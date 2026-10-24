# 사내 HAL 설정 템플릿

**이 디렉터리를 생성기 저장소 옆에 `hal-sdd-project/`로 복사하고, 파일 안의 `<...>`를 채우세요.** 그다음 생성기 저장소의 `docs/inhouse/02-first-run.md`("4. 실행하기")에 있는 명령을 순서대로 실행합니다. 설정 뒤에는 실제 소스를 대조하여 설계 계약을 작성해야 합니다.

| 파일 | 채울 것 |
|---|---|
| `sdd.yaml` | `source_url`(코드 열람 주소), 필요하면 `ndk_build.args`, 모델을 쓸 때 `agent` |
| `config/scenarios.yaml` | `<namespace>`와 실제 시그니처, 대조한 정의 위치 |
| `config/glossary.yaml` | 사내 약어의 뜻. `export-site`가 뜻이 없는 약어를 알려 줍니다. |
| `config/sections.yaml` | `vendor-contract`·`overview`의 소스 근거와 답변, 사내 클래스 패턴 |

이 템플릿이 기본으로 켜 둔 것:

1. **ndk-build compile DB 자동 정규화**와 커밋마다 DB 재생성(`ndk_build`의 `project_dir`·`args`를 그대로 씁니다).
2. **구성 요소 색인**(`components` 섹션): 빌드한 모든 클래스·함수를 모델 없이 표로 싣습니다.
3. **Mermaid 동봉**. 사람 승인 없는 문서의 게시 차단(`site.require_approval`)은 첫 실행 뒤 게시 전에 켭니다.

모델은 `dry-run`으로 시작합니다. 사내 모델 연결과 LLM 판정은 생성기 저장소의 `docs/inhouse/03-update-system.md`에서 켭니다.

`build/`와 `sdd.local.yaml`만 Git에서 제외합니다. 원고, 승인 장부, Mermaid 사본은 커밋해야 다른 작업 공간에서도 승인과 그림이 유지됩니다.

이 디렉터리를 복사한 사내 저장소에는 사내 클래스명과 설명이 들어가므로, 공개 저장소에 올리지 않습니다.

## 문서 품질을 옮기는 방법

Vendor와 아키텍처 독자 프로필은 기본으로 필수입니다. 빈 `sources`·`statements`를 실제 소스와 대조해 채우기 전에는 생성이 실패합니다. 클래스 색인만으로 설계 문서가 완성된 것으로 처리하지 않습니다.

[공통 품질 기준과 읽기 검증](../../docs/concepts/reader-quality.md), [완성된 작은 HAL 예제](../mini-hal/config/reader-sections.yaml)를 따라 작성하세요. 소스 근거 고정과 필수 질문 검사는 libcamera와 같은 생성기를 사용합니다. 실제 사내 HAL의 동작과 설명은 사내 독자가 별도로 검토해야 합니다.
