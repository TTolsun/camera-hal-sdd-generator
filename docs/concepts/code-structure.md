# 생성기 코드의 책임 분리

SOLID 원칙 중 단일 책임과 의존 방향을 우선 적용합니다. 실제 교체 지점이 없는 인터페이스·상속 계층은 추가하지 않습니다. CLI 사용법과 `impact.json`의 schema 1 형식은 유지합니다.

| 모듈 | 책임 |
|---|---|
| `source_git.py` | ref를 커밋으로 고정하고 소스 상대 변경 경로를 조회합니다. |
| `document_metadata.py` | 수동 Markdown의 근거 메타데이터와 생성 방식·검증 범위 표시를 관리합니다. |
| `scenario_document.py` | 시나리오 facts를 주요 확인 지점·호출 경계·접을 수 있는 전체 기록으로 구성합니다. 실행 순서를 추정하지 않습니다. |
| `generate.py` | 문서 종류별 조립과 생성 순서를 관리합니다. |
| `narration.py`, `prompting.py` | 작은 `ChatPort` 계약으로 모델을 호출하고 예산·재시도·문장 검사를 적용합니다. |
| `fact_presenter.py` | 이미 추출된 facts에서 표를 만듭니다. Git·모델·출력 파일에 접근하지 않습니다. |
| `page_writer.py` | Markdown 레이아웃·메타데이터·파일 출력을 관리합니다. |
| `contract_schema.py`, `reader_profiles.py` | 문서 설정과 독자별 필수 질문을 검사합니다. |
| `evidence.py` | 고정 커밋에서 발췌하고 설명과 소스 지문을 대조합니다. |
| `design_contracts.py` | 필수 질문과 답변·근거 연결을 판정합니다. 렌더러에 의존하지 않습니다. |
| `contract_render.py` | 질문별 검증표와 페이지마다 중복을 제거한 원문 보기를 만듭니다. |
| `state_io.py` | 자동 실행과 유휴 검토가 공유하는 상태를 원자적으로 저장합니다. |
| `localization_cli.py` | 번역 카탈로그 갱신 명령에서 사이트 렌더링과 번역 모듈을 연결합니다. |
| `config.py` | YAML 병합·경로 해석과 책임별 설정 객체를 제공합니다. 옵션 검증은 기존 소비 시점에 수행하며, 새 필수 키를 추가하지 않습니다. |
| `generated_design.py` | 생성 순서·검증된 원고 재사용·최종 artifact 조립과 게시 재검증을 연결합니다. 기존 함수 import와 네 항목 반환 계약을 유지합니다. |
| `design_request.py` | 요청·분할 단위·프롬프트·입력 지문을 준비합니다. 모델을 호출하거나 답변을 수용하지 않습니다. |
| `design_response.py` | 응답 JSON·구절·문장·필수 질문을 판정하고 검증할 문서 모델을 구성합니다. 파일·Git·CLI·렌더러에 접근하지 않습니다. |
| `design_execution.py` | 한 단위의 호출·입력 예산·기존 제한 재시도와 grounding 호출을 관리합니다. |
| `design_types.py` | `RequestPlan`, `TopicPrompt`, `UnitRequest`, `UnitResult`, `DesignResult`로 경계 값을 명명합니다. 저장하는 schema 1은 바꾸지 않습니다. |
| `design_trials.py`, `design_compat.py` | 명시적 HTTP 비교 체크포인트·기록 재생을 연결하고, 과거 HTTP 정책 해시의 정확한 허용 쌍을 판정합니다. CLI 실패의 대체 실행기로 사용하지 않습니다. |
| `response_bundle.py`, `agent_errors.py` | 요청 지문에 연결된 파일 교환과 공통 전송 오류를 담당합니다. 파일 교환을 실제 호출로 표시하지 않습니다. |
| `matching.py` | 파일 접근 없이 경로 glob과 C++ 심볼 선택 규칙을 제공합니다. |
| `impact.py` | 설정과 근거를 모아 재생성 대상을 계산하고 보고서를 구성합니다. |
| `coverage.py` | 주입받은 facts·섹션·근거 목록에서 문서 범위 누락을 판단합니다. Config·Git·파일에 접근하지 않습니다. |
| `document_health.py` | 원고 분량·증가·중복과 Feature 문서 계약·폐기 계획을 검사하고 성공 결과를 다음 비교 기준으로 저장합니다. 의미 승인이나 원고 자동 삭제는 수행하지 않습니다. |
| `change_kind.py` | 파일의 두 판이 주석·공백·`#include`만 다른지 판정합니다. 파일과 Git에 접근하지 않습니다. |
| `coverage_triage.py` | 남은 범위 검토 항목을 LLM으로 판정하고 승인 장부와 별도로 기록합니다. 관문 통과 여부는 설정이 정하며 승인을 만들지 않습니다. |
| `impact_review.py` | 검사 결과를 Markdown으로 표현합니다. 분석하거나 저장하지 않습니다. |
| `approvals.py` | 사람 검토 승인을 본문 해시와 함께 장부에 기록·판정합니다. 승인을 자동으로 만들지 않습니다. |
| `update.py` | 새 커밋을 차례로 처리하는 증분 갱신 orchestration입니다. 순서·재개는 Git과 상태 파일이 보장하고, 관문 판정은 `approvals.py`와 원고 상태를 읽습니다. |
| `compdb.py` | compile DB 확보(ndk-build·simple)와 정규화(절대 경로, `-working-directory`, `-resource-dir`)를 담당합니다. |
| `mermaid_assets.py` | Mermaid ESM 배포본(본체 + chunk)을 tarball에서 꺼내 오프라인 자산으로 놓습니다. |
| `cli.py` | 입력을 검증하고 각 기능을 연결하며 결과를 저장·출력합니다. |

이전의 `impact → coverage → impact` 순환 의존을 제거했습니다. 사실 추출기의 제외 규칙도 영향 분석 모듈 대신 `matching.py`를 사용합니다. 수동 문서 메타데이터는 검사 한 번당 한 번 읽고, 범위 판정에는 읽은 값을 전달합니다.

클래스·함수 이름 비교는 생성·그림·영향 분석·범위 검사에서 같은 함수를 사용합니다. C++ 이름은 운영체제와 무관하게 대소문자를 구분하며, 전체 이름과 짧은 이름을 모두 지원합니다. 경로 glob은 심볼 선택과 별도 규칙을 유지합니다.

다른 SCM을 사용할 경우 Git 어댑터 대신 변경 경로와 커밋 식별자를 공급하고, 다른 보고서 형식은 범위 판정 코드를 바꾸지 않고 결과를 렌더링합니다. 새 규칙이나 표현 형식이 실제로 여러 종류가 되어야 할 때만 별도 인터페이스를 도입합니다.

회귀 검증은 누락 클래스 검출, 삭제·이름 변경·한글 경로, 수동 근거, 반복 생성과 실패 시 출력 보존을 포함합니다. 리팩터링 전후 실제 libcamera A/B 검토 항목도 동일해야 합니다. 범위 검사 통과를 내용 정확성 통과로 승격하지 않습니다.

## 의존 방향 유지

설정 검사 → 근거 수집 → 계약 판정 → 문서 조립 → 사이트 출력의 책임을 분리했습니다. `design_contracts`는 생성기나 렌더러를 import하지 않습니다. `automation`과 `idle_review`는 서로 상태 저장을 빌리지 않고 `state_io`를 사용합니다. `site_localization` 라이브러리는 사이트 출력을 import하지 않으며 명령 진입점이 둘을 연결합니다.

`tests/test_dependencies.py`는 함수 안의 import도 포함해 라이브러리 전체의 순환 의존을 검사합니다. `__main__` 실행 진입점은 라이브러리 import에서 실행되지 않으므로 제외합니다. Liskov 치환을 주장하기 위한 상속 계층을 새로 만들지 않고 실제 교체 지점인 모델 호출만 작은 프로토콜로 정의했습니다.

## 설정 접근 경계

`Config.review`, `site`, `update`, `visuals`, `automation`, `documentation`은 책임별 설정 객체를 반환합니다. YAML 키·기본값·명시적 false/0과 로컬 덮어쓰기는 유지합니다. 사용하지 않는 선택 기능의 잘못된 옵션 때문에 다른 명령까지 새로 거부하지 않도록, 기존 기능에서 옵션을 소비하던 시점에 설정 객체의 검증을 호출합니다. 객체는 접근 시 현재 설정에서 만들므로 시험 복사본의 변경 뒤에 오래된 값이 남지 않습니다. `raw`에는 알 수 없는 프로젝트 키도 보존하여 snapshot 왕복을 유지합니다.

| 기존 raw 소비 영역 | 키와 기본값 | 현재 경계 |
| --- | --- | --- |
| 생성·검토·재사용 | `design_prompt: standard`, `design_grounding: false`, `design_revision: false`, `answer_cache: false`, `reader_loop: {}`, `coverage_triage: {}` | `ReviewConfig`가 해석합니다. 섹션의 grounding·prompt 재정의가 우선합니다. |
| 사이트·번역·CLI | `enabled: false`, `title: Camera HAL SDD`, `source_url: ''`, `source_link: github`, `source_link_template: ''`, `nav_group: ''`, `nav_groups: []`, `require_approval: false`, `intro/english_catalog/mermaid_dir: null`, `mermaid: ''`, `undefined_terms: null`, `translation_batch_size: 1` | `SiteConfig`가 해석합니다. 자산 경로는 계속 설정 루트 기준이며 기존 CLI Mermaid 우선순위를 유지합니다. |
| 증분 갱신 | `extract_cmd/compdb_cmd: null` | `UpdateConfig`가 명령을 제공합니다. 기존 추출 명령 검증과 compdb의 truthy 판정을 유지합니다. |
| 질문별 그림 | `file: null`, `max_nodes: 12`, `on_stale: error` | `VisualsConfig`가 설정 키를 검사합니다. 근거·계획별 노드 한도 판정은 그림 소비자가 담당합니다. |
| 구조 그림 | `enabled: false`, `max_nodes: 16`, `direction: LR`, `strip_namespace: ''` | `Config.diagram_policy`가 섹션 재정의를 병합합니다. 그래프 유효성은 기존 그림 검사에 남습니다. |
| 자동화·문서 수명주기 | 기존 schedule/publish/hermes/idle_review 및 documentation limits/pages/features/retired_pages | 설정 객체는 옵션을 전달하며 문서 한도 검증을 모읍니다. Git 대상·출력 격리·실제 문서 계약은 해당 업무 모듈이 검사합니다. |

남은 raw 접근은 원형을 보존해야 하는 경계입니다. `site_build`, `idle_review`, `automation`은 기존 지문과 재개 식별자를 계산합니다. `trial_workspace`, `evaluate_pipeline`, `evaluate_reader`, `localization_cli`는 독립 시험의 설정을 복사·수정·저장합니다. `compdb`는 선택적인 simple compile DB의 빌드별 설정을 해석합니다. `config` 이외의 허용 모듈과 최대 접근 수는 의존성 테스트에 고정합니다. 호출 기록의 응답 원문을 뜻하는 `raw`는 Config 설정과 구분합니다.

## 변경의 영향 범위

검토 옵션을 추가할 때는 `config.ReviewConfig`와 해당 소비자만 수정합니다. 응답 검증 규칙을 교체할 때는 `design_response`와 판정 모듈·회귀를 수정하며 요청·재시도·파일 교환 코드는 바꾸지 않습니다. 재사용 적합성 검사는 `design_reuse`에서 변경하며, 실제 교체 지점인 검증 함수만 주입받습니다. 과거 HTTP 별칭은 `design_compat`에 한정되어 있습니다. 이번 책임 이동은 기존 grounding 정책 파일·정책 해시·캐시 키의 의미를 바꾸지 않습니다.

사이트 manifest의 `engine`에는 분리된 생성·판정·설정 파일도 기록합니다. 같은 코드를 다른 파일로 옮겼다고 실행 코드 추적이 사라지지 않도록 합니다. 코드 이동으로 build_id는 달라질 수 있지만 원고의 입력 정책 지문이나 승인 상태를 바꾸지 않습니다. 출력 바이트가 같은 경우와 실행 코드 기록만 달라진 경우를 검증 기록에서 구분합니다.

고정 응답 회귀는 네 전송 방식과 두 프롬프트 모드의 요청·검증 결과·artifact·출처를 변경 전 SHA의 값과 대조합니다. 시각·실행 ID·파일 기록을 포함하지 않는 메모리 경계이므로 제외할 비결정적 필드는 없습니다. 실제 CLI 실행의 문장에는 바이트 동일성을 요구하지 않습니다. 자세한 검증 기록은 [#141 작업 기록](../inhouse/records/structure-141.md)에 남깁니다.
