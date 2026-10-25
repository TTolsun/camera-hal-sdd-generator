# 사내 HAL 설정 템플릿

`config/visuals.yaml`의 상태·요청·소유권·실패 질문을 실제 HAL의 `design_topics` 근거와 연결하세요. `generation: llm`이면 생성기가 승인된 사내 모델을 호출해 구조 초안을 받고 구절·심볼·조건을 검사하여 원고에 배치합니다. 빈 근거나 모델 실패는 게시를 중단합니다. [LLM 그림 자동화](../../docs/concepts/site.md#사내-llm으로-초안-자동-생성하기)에 작성·재생성 절차가 있습니다.

[반입 패키지 시작 안내](../../docs/inhouse/package.md)에서 시작 프롬프트·실행 순서·합격 기준·복구 절차를 함께 찾을 수 있습니다.

**이 디렉터리를 생성기 저장소 옆에 `hal-sdd-project/`로 복사하고, 파일 안의 `<...>`를 채우세요.** 그다음 생성기 저장소의 `docs/inhouse/02-first-run.md`("4. 실행하기")에 있는 명령을 순서대로 실행합니다. 설정 뒤에는 실제 소스를 대조하여 설계 계약을 작성해야 합니다. 에이전트에게 맡길 때는 [전달용 지시문](../../docs/inhouse/agent.md#전달할-지시문)과 [계약 작성 절차](../../docs/inhouse/contract-authoring.md)를 사용하세요.

| 파일 | 채울 것 |
|---|---|
| `sdd.yaml` | `source_url`(코드 열람 주소), 필요하면 `ndk_build.args`, 모델을 쓸 때 `agent` |
| `config/scenarios.yaml` | `<namespace>`와 실제 시그니처, 대조한 정의 위치 |
| `config/glossary.yaml` | 사내 약어의 뜻. `export-site`가 뜻이 없는 약어를 알려 줍니다. |
| `handoff.md` | 단계별 완료·실패·재개 명령과 증거 경로 |
| `config/sections.yaml` | `vendor-contract`·`overview`의 소스 근거와 답변, 사내 클래스 패턴 |

이 템플릿이 기본으로 켜 둔 것:

1. **ndk-build compile DB 자동 정규화**와 커밋마다 DB 재생성(`ndk_build`의 `project_dir`·`args`를 그대로 씁니다).
2. **구성 요소 색인**(`components` 섹션): 빌드한 모든 클래스·함수를 모델 없이 표로 싣습니다.
3. **Mermaid 동봉**. 사람 승인 없는 문서의 게시 차단(`site.require_approval`)은 첫 실행 뒤 게시 전에 켭니다.
4. **독자 → 수행할 작업 → 문서 메뉴**. `For Vendor`·`For Developer`는 `group`으로 유지하고 작업 소분류는 `config/sections.yaml`의 `nav_section`으로 지정합니다. `generate`·`export-site`가 같은 공통 생성기를 사용하므로 HTML을 따로 편집하지 않습니다.

NDK-build가 아닌 제품의 설정은 [환경별 선택](../../docs/inhouse/agent.md#1-환경과-데이터-경계)을 따릅니다.

모델은 `dry-run`으로 시작합니다. 사내 모델 연결과 LLM 판정은 생성기 저장소의 `docs/inhouse/03-update-system.md`에서 켭니다.

`build/`와 `sdd.local.yaml`만 Git에서 제외합니다. 원고, 승인 장부, Mermaid 사본은 커밋해야 다른 작업 공간에서도 승인과 그림이 유지됩니다.

이 디렉터리를 복사한 사내 저장소에는 사내 클래스명과 설명이 들어가므로, 공개 저장소에 올리지 않습니다.

## 문서 품질을 옮기는 방법

템플릿은 Vendor의 제품 개요·지원 범위와 검증을 **도입 판단**, 연동 가이드를 **연동 구현**으로 묶습니다. Developer는 **구조 이해·코드 탐색·동작 추적과 문제 진단·변경 검토**로 나눕니다. 작업과 문서의 순서는 설정에서 처음 나온 순서를 따릅니다. 장치별 구현 문서는 실제 근거가 있을 때 해당 작업 소분류에 추가하며, libcamera의 장치 이름이나 문서를 사내 기본값으로 복사하지 않습니다. 기존 사내 설정에는 이 항목을 명시적으로 옮겨야 하며 생성기를 교체하는 것만으로 기존 YAML을 자동 수정하지 않습니다.

Vendor 개요(`vendor-overview`)와 신입·타팀 Developer(`developer`) 독자 프로필은 기본으로 필수입니다. Vendor 개요의 기능·강점·연동 순서·지원 제약과 기존 입력·소유권·완료·실패·검증 질문을 실제 HAL 근거로 채웁니다. 상세 문서는 `vendor` 프로필로 나눌 수 있습니다. 기본 템플릿은 `design_generation: llm`을 사용합니다. 에이전트가 빈 `sources`를 실제 소스에 연결하고 질문·`covers`를 작성하면 사내 LLM이 답변과 그림 초안을 생성합니다. `statements`를 미리 넣지 않습니다. 직접 검토한 고정 계약을 선택한 섹션에서만 `design_generation`을 빼고 해시·`statements`를 작성합니다. 클래스 색인만으로 설계 문서가 완성된 것으로 처리하지 않습니다.

[공통 품질 기준과 읽기 검증](../../docs/concepts/reader-quality.md), [완성된 작은 HAL 예제](../mini-hal/config/reader-sections.yaml)를 따라 작성하세요. 소스 근거 고정과 필수 질문 검사는 libcamera와 같은 생성기를 사용합니다. 실제 사내 HAL의 동작과 설명은 사내 독자가 별도로 검토해야 합니다.
