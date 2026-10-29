# 독자 과업과 제품 근거를 연결하기

먼저 독자가 끝내야 할 과업과 필수 질문을 고정하세요. 제품 자료는 해당 질문에 필요한 사실만 선택합니다. 기능·페이지·인용 수를 늘리는 것이 완료 조건은 아닙니다.

## 독자 범위 계약

기존 `reader_profile`, `reader_family`, `design_requirements`를 유지하고 섹션에 선택적으로 `reader_scope`를 추가합니다. 기존 설정은 이 항목 없이 동작합니다.

```yaml
reader_scope:
  revision: 1
  change_reason: 도입 검토의 필수 과업을 출력 전에 고정합니다.
  tasks:
    - id: adoption
      goal: 고객사가 제공 기능과 적용 조건을 이해합니다.
      completion: 필수 질문의 답변과 그 조건·근거를 찾습니다.
      requirements: [capabilities, benefits]
  optional:
    - id: integration-detail
      location: vendor-contract.md
      reason: 내부 호출 상세는 연동 구현 단계에서 읽습니다.
  excluded:
    - id: all-functions
      reason: 전체 함수 참조서는 이 개요의 목적이 아닙니다.
  removed_requirements: []
```

모든 현재 필수 질문은 과업에 연결되어야 합니다. 선택 상세의 위치는 실제 설정된 페이지여야 합니다. 범위를 바꿀 때 `revision`, `change_reason`, 삭제한 질문 ID인 `removed_requirements`를 함께 기록합니다. 변경은 기존 페이지·주제 입력 지문을 바꾸므로 이전 완료 판정을 그대로 사용할 수 없습니다. 프로필의 필수 질문을 삭제하여 통과시키는 것은 기존 검사에서 계속 거부합니다. 필수 조건·예외를 삭제해서 분량을 줄이지 않습니다. 기존 상세 문서와 수명주기·앵커 보존 절차를 사용합니다.

`design-review.json`의 `reader_scope`와 사이트의 `reader-scope.json`에는 과업별 질문, 답변 주제, 선택된 근거, 미해결 질문, 선택 상세와 의도적 제외가 담깁니다. 구조적 연결은 의미 정확성이나 사람의 과업 성공을 뜻하지 않습니다. 모델 의미 판정과 실제 사람 시험은 각각 별도 상태입니다. #163의 사람 시험은 자동 검사로 완료하지 않습니다.

누락 점검은 `scope_decision`에 기존 과업 ID, 충족되지 않는 필요, 기존 답변 위치, 근거, 상세 위치를 기록합니다. 모델은 `required`, `optional-detail`, `already-covered`, `out-of-scope`, `deferred` 중 하나를 판단합니다. 생성기는 ID와 연결·근거를 검사합니다. 필수 과업을 돕는 후보만 개요에 추가하며 선택 상세·중복·범위 밖·근거 부족은 새 본문으로 추가하지 않습니다. 새 근거가 필요한 조건이나 예외를 설명하면 기존 질문에 연결된 새 주제로 보완할 수 있습니다.

`idle-review-state.json`과 원본 요청·응답에는 실제 검토한 파일·창의 시작 위치·길이·전체 길이와 미검토 범위가 남습니다. `no_gap`은 해당 창에 대한 결과입니다. 모든 설정 창을 소진해도 전체 코드나 실제 사람 과업을 검토한 것으로 바꾸지 않습니다. 계약이 바뀌면 이전 창 판정과 같은 작업 ID의 완료 결과도 재사용하지 않습니다.

## 선택적 제품 입력

`sdd.yaml`의 `products.file`로 로컬 YAML을 선택하고, 기존 설계 주제에 `product: {id: ..., feature: ...}`를 연결합니다. 제품 설정에는 답변 문장이나 홍보 원고를 넣지 않습니다. 선택 CLI가 근거에서 고객 이점을 작성하며 기존 질문·인용·의미 검사와 승인 절차를 거칩니다. 로컬 자료만으로 생성하고 발췌를 읽을 수 있습니다.

```yaml
products:
  file: config/products.yaml
# config/sections.yaml의 해당 주제:
# product: {id: example-project, feature: capture}
```

제품 파일은 `schema: 1`, `products`, `evidence`를 가집니다. 전체 예시는 [사내 시험 입력](../../examples/inhouse-template/config/products.example.yaml)에 있습니다. 이 예시는 가상 구성으로 표시되며 실제 제품 사실이 아닙니다.

| 항목 | 입력과 의미 |
|---|---|
| 제품 범위 | `id`, `scope: product 또는 project`, `release`, `configuration`, `simulation`, `as_of`를 고정합니다. |
| 기능 | `id`, 고객 필요 `need`, 사용 상황 `usage`, `availability`, `conditions`, `exclusions`, 기존 주제의 구현 소스 ID `implementation`, 자료 ID `evidence`, 요청할 `claims`를 지정합니다. |
| 제공 상태 | `unknown`, `offered`, `unsupported`를 구분합니다. 구현 확인과 조건부 측정은 별도로 기록합니다. 자료가 부족하면 `unknown`을 유지합니다. |
| 주장 유형 | `structural`, `performance`, `comparison`, `support`별로 근거 ID를 연결합니다. 구조적 이점에는 구현이, 성능에는 measurement, 비교에는 comparison, 제공 보장에는 제품 사양·릴리스가 필요합니다. 프로젝트 범위의 공식 설명은 project-document로 연결할 수 있습니다. |
| 자료 | `id`, `type`, `supplier`, `version`, `date`, `valid_until`, `product`, `release`, `configuration`, `feature`, `conditions`, `availability`, 로컬 `file`, 원본 바이트 `sha256`을 받습니다. |

자료 유형은 `specification`, `release`, `measurement`, `comparison`, `project-document`입니다. `as_of`는 재현 가능한 판단 기준일이며 자료의 유효 기간 안이어야 합니다. 운영자가 기준일을 갱신해야 하며 실행 시각을 몰래 입력에 섞지 않습니다. 조건은 선택한 기능의 조건과 정확히 같아야 합니다. 다른 제품·릴리스·구성·기능의 자료, 변조·빈 자료, 오래되거나 미래의 자료, 상충하는 제공 상태는 생성·게시 전에 실패합니다. 자료 경로는 입력 파일 디렉터리 안의 상대 경로로 제한합니다.

제품 제공 상태가 선언되어도 적합한 자료가 없으면 유효 상태는 미확인입니다. 미확인을 미지원으로 바꾸지 않습니다. 측정 자료는 명시한 조건에서의 측정만 뒷받침합니다. 제품 파일이나 자료 내용·해시·조건이 바뀌면 관련 주제의 지문과 페이지 검증이 바뀝니다. 무관한 제품은 해당 주제 입력에 들어가지 않습니다. 기존 실패 시 원고·사이트 보존과 번역 HTML 지문 검사를 유지합니다.

코드 근거는 Git 커밋·발췌로 추적합니다. 제품 자료는 `origin: product-material`과 별도 제품 메타데이터로 추적하며 소스 Git 호스트로 잘못 연결하지 않습니다. 사이트의 로컬 발췌와 `product-context.json`에서 제품·프로젝트 범위, 고객 필요, 조건·제외, 주장별 근거와 미해결 항목을 확인합니다. 자료의 해시·범위 검사는 자료 내용의 진실을 보증하지 않습니다. 수치·비교·제공 보장의 일부 알려진 오류는 기계적으로 거부하지만, 모든 표현의 의미를 자동으로 판정하지는 않습니다. 기존 모델 근거 대조와 사람 검토가 계속 필요합니다.

다음 단계: [문서 수명주기](document-lifecycle.md)에서 상세 이동과 분량·중복 관문을 확인하세요.
