---
generated_at: 2026-10-29T16:46:35+00:00
source_commit: faeab8bff751a77d47809107e47b44a0ffa098e1
status: ok
section: fixture-a
generation_method: facts-and-llm
evidence_fingerprint: 6c7fcb47efd1a99b2a01c2cce8498622fc52b8dc49b5e26269cc390a65a1a98b
semantic_review: human-review-required
agent: cli/codex/gpt-6.1-terra
generated_design: {"schema": 1, "input_fingerprint": "6c7fcb47efd1a99b2a01c2cce8498622fc52b8dc49b5e26269cc390a65a1a98b", "answers": {"capture": [{"text": "가상 테스트 구성 `fixture-a`의 고객은 통합자가 제공하는 기기 구현을 통해 이미지를 얻어야 하며, 사용 상황은 가상의 `capture` 통합 실습입니다. 릴리스 `r1`의 `sensor-a-build-x` 구성에서 명세는 센서 A와 빌드 X를 조건으로 `capture`가 제공된다고 확인합니다. 코드에서 `capture()`는 통합 시 제공된 기기 이미지 획득 동작인 `acquireImage()`를 호출합니다. 이 진입점을 분리하면 통합 과정에서 기기 구현을 선택할 수 있습니다.", "evidence": ["product-spec-a", "code"], "covers": ["value"], "kind": "behavior", "quote": "FICTIONAL TEST ONLY. fixture-a release r1 configuration sensor-a-build-x. Customer need: acquire an image through an integrator supplied device implementation. Usage: a fictional capture integration exercise. For sensor A with build X, capture offering is offered. The fictional specification confirms capture is offered under these conditions. This material supplies no performance measurement or competitive comparison."}]}, "topic_inputs": {"capture": "c58ae1e233c806bb48448023cbb0d1d8cd9effcc02bced5d1b51522372edb1a0"}, "reused_topics": [], "replayed_units": [], "generated_topics": ["capture"], "topic_agents": {"capture": "cli/codex/gpt-6.1-terra"}, "grounding_review": "passed", "grounding_policy": "3c9673abb403dee9aa554ee5b3c549ebfe95bb18ec0e9cd7bf6e495e060439c2", "validation_policy": {"manuscript": "e0c429a5c80a01c34563ce00a616df89d8f75c735f8669bcbd1f75d84cce82a6", "semantic": "571896e4854c21322a1ce4580107c235cae5a9f94e71adc8c97a7e2897405968", "duplicates": "d4af3d834d8b1c99a6c9311612712a64112c30fa4621b375904d172f361285b8", "design_contracts": "9f54ecddce57c7a9caa6c02af77904b57eff2471f2a052951c1cffd18256a4f0", "validate": "78d29ffd1bf6235067edf5a0c7d9b1290f1f11e90599605a0e192e90be5f3372", "reader_profiles": "ad9005d08295212371f59e8934ace86786c0683f7a4c416301ee0e0cadc8b797", "contract_schema": "fecc4ee78a481139776e562c164c0da9a3e5edf0a64a72be1d1c8feddee3cd08", "answer_contracts": "1e0d24e0cf26ded53ecec2e5a6fbc51836bac6e17530318a9fa7cffaa936c00b", "reader_scope": "d3c37f6f387952b38107f6eafc67436c6eb798b041ed5eac315f18e4da7ccb6b", "product_context": "9db4d42a710b4a71a7d2bb16f69db06926409281dc1a200c796e77d5deaa25a0", "design_response": "74ebb2d21768d6bdd4ef7611c1c539526a7e72e6a58604c82e8305003d24f8b7", "design_validation": "b8133c78a8eb42fd5194c2756bb649b396ec54b40c49b72544bdbbcaf3366c57"}, "validation_model": "1a4dd51b11b4f16c023c5f14b8703d5a987cc1348ee2507bb53e293f939bdffd", "style_policy": {"fluent-korean.md": "ce5aa71e58371e3fc02ff8cb165e07c9234f5166f6541423a91cc4cb40878975", "i-have-adhd.md": "3170b16ace00aecb0dd7feb54c0b5aa642e7502acda06ecd24fd89a11c7127e9", "README.md": "f8fd5a3d8041c23fc68b93ff32b8727e98393383b5099032eb00ad0013e7611c"}, "body_sha256": "99e87f8a345665cb9fee298ddd0a99e17b27f168a2fc0a5af155fc2ebaf00cd3"}
---

# fixture-a 가상 시험

**이 절의 표부터 확인하세요.**



## 고객 필요와 제공 조건

**가상 시험 구성입니다. 실제 제품의 지원·성능 주장으로 사용하지 마세요.**

가상 테스트 구성 `fixture-a`의 고객은 통합자가 제공하는 기기 구현을 통해 이미지를 얻어야 하며, 사용 상황은 가상의 `capture` 통합 실습입니다. 릴리스 `r1`의 `sensor-a-build-x` 구성에서 명세는 센서 A와 빌드 X를 조건으로 `capture`가 제공된다고 확인합니다. 코드에서 `capture()`는 통합 시 제공된 기기 이미지 획득 동작인 `acquireImage()`를 호출합니다. 이 진입점을 분리하면 통합 과정에서 기기 구현을 선택할 수 있습니다. `product-evidence/fixture-a/spec-a.txt:1`, `capture.cpp:1`

근거 원문: [capture.cpp:1](#source-1cbad1bc0a18dd07) · [product-evidence/fixture-a/spec-a.txt:1](#source-63a3ce7fe7a2c980)

??? note "설계 질문과 검증 범위"
    질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.
    
    | 설계 질문 | 설명 위치 | 확인 범위 |
    |---|---|---|
    | 가상 구성 fixture-a의 고객 필요와 사용 상황, capture 진입점의 구조적 이점, 해당 릴리스·센서·빌드에서 확인된 제공 상태와 조건을 설명하세요. 미확인을 미지원으로 쓰지 말고, 측정이나 비교 결과를 만들지 마세요. | [고객 필요와 제공 조건](#고객-필요와-제공-조건) | 코드 근거와 설명 연결 |

## 소스 근거

같은 발췌는 한 번만 싣습니다. 필요한 원문을 펼쳐 설명과 대조하세요.

<a id="source-1cbad1bc0a18dd07"></a>

??? note "소스 근거: capture.cpp:1"
    `capture.cpp:1`에서 시작하는 발췌입니다. 종료 줄은 4이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `05b6049357986157333bb73a860cd4b14ec72c846963a24a47135ee30e7c2051`
    
    ```text
    // FICTIONAL TEST SOFTWARE. This is not an actual camera product.
    // capture() calls the device image acquisition operation supplied at integration.
    // Separating this entry point lets the integration select the device implementation.
    void capture() { acquireImage(); }
    ```

<a id="source-63a3ce7fe7a2c980"></a>

??? note "제품 자료: product-evidence/fixture-a/spec-a.txt:1"
    소스와 별도로 제공된 자료입니다. 제공자·버전·적용 범위를 아래 기록에서 확인하세요. 자동 검사는 사람 승인이 아닙니다.
    
    `product-evidence/fixture-a/spec-a.txt:1`에서 시작하는 발췌입니다. 종료 줄은 2이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `2a36749e8e39a5c36938fa7f73223dd6c79b02fcccb81ab1a2ab8d62565a73a8`
    
    ```text
    FICTIONAL TEST ONLY. fixture-a release r1 configuration sensor-a-build-x. Customer need: acquire an image through an integrator supplied device implementation. Usage: a fictional capture integration exercise. For sensor A with build X, capture offering is offered. The fictional specification confirms capture is offered under these conditions. This material supplies no performance measurement or competitive comparison.
    
    ```
    
    ```json
    {
      "type": "specification",
      "supplier": "Fictional test author",
      "version": "1",
      "date": "2026-10-30",
      "valid_until": "2026-12-31",
      "product": "fixture-a",
      "release": "r1",
      "configuration": "sensor-a-build-x",
      "feature": "capture",
      "conditions": [
        "sensor A",
        "build X"
      ],
      "sha256": "2a36749e8e39a5c36938fa7f73223dd6c79b02fcccb81ab1a2ab8d62565a73a8"
    }
    ```

??? note "근거와 검토 정보"
    - 생성 방식: 추출 사실과 LLM 설명
    - 검증 범위: 표·그림은 facts로 만들고 설명은 LLM이 작성합니다. 인용·문장 및 설정된 구조 검사를 적용합니다.
    - 근거 파일: `capture.cpp`, `product-evidence/fixture-a/spec-a.txt`
    - 근거 수준: 코드 확인 (정적 분석, ndk-build 구성, commit `faeab8bff7`)
    - 자동 검사 (인용·문장 및 설정된 구조 검사): 통과
    - 검토 상태 기록일: 2026-10-30 · 사람 검토 전

다음 단계: [시스템 개요](overview.md)
