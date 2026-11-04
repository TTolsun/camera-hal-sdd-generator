---
generated_at: 2026-11-04T19:00:15+00:00
source_commit: 0c92b75dd1f9fc2ac97d2ef08e246bc081faaf48
status: ok
section: completion-demo
generation_method: facts-and-llm
evidence_fingerprint: 1025de69c9557ea5e87b9b661b6de905110cec70e77c27d4564a1bff0c29852a
semantic_review: human-review-required
agent: cli/codex/gpt-6.1-terra
generated_design: {"schema": 1, "input_fingerprint": "1025de69c9557ea5e87b9b661b6de905110cec70e77c27d4564a1bff0c29852a", "answers": {"completion": [{"text": "runPipes의 반환값이 0 이상이면 if 블록에서 sendResult를 호출하며, 음수이면 호출하지 않습니다. onFrameDone은 if 블록 밖에서 반환값과 관계없이 무조건 호출하므로 음수 반환 시에도 호출합니다.", "evidence": ["on-frame"], "covers": ["completion-rule"], "kind": "behavior", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}\n\nvoid RequestManager::sendResult", "part_id": "completion-rule"}]}, "topic_inputs": {"completion": "aba2b1eebce45f793cd6a9783368cff3393514fc655f53a5d58916f1c7aab013"}, "reused_topics": [], "replayed_units": [], "generated_topics": ["completion"], "topic_agents": {"completion": "cli/codex/gpt-6.1-terra"}, "grounding_review": "not-run", "grounding_policy": null, "validation_policy": {"manuscript": "367d18b95f8f0d01a15ae0f4d1b70f7e13e4d0298df4215e2c449ac4905db6f9", "semantic": "571896e4854c21322a1ce4580107c235cae5a9f94e71adc8c97a7e2897405968", "duplicates": "93f0e8b5bdc1b40bf4ab38168e92c2772aa36747bec6add25921fbb90b909e38", "design_contracts": "9f54ecddce57c7a9caa6c02af77904b57eff2471f2a052951c1cffd18256a4f0", "validate": "78d29ffd1bf6235067edf5a0c7d9b1290f1f11e90599605a0e192e90be5f3372", "reader_profiles": "ad9005d08295212371f59e8934ace86786c0683f7a4c416301ee0e0cadc8b797", "contract_schema": "2f593eec0430a4e6b5822e642c0a7a1227fc150a0b27d8a71f521acf93b6439e", "answer_contracts": "1e0d24e0cf26ded53ecec2e5a6fbc51836bac6e17530318a9fa7cffaa936c00b", "reader_scope": "1b9c26b10b74ae8cf034f5863cbac2114e1d844e5d8332eb1f10562a18371782", "product_context": "050c20aa2fdcceae10c6275fbb5f850f616ab5051bb67ccbcb4a204877a238d9", "design_response": "deb70dda7ad27f001267e4a9712c5b0dc1fe9fa67acd13bedbfefaaad0ad83c8", "design_validation": "946deebb694018f6361ee86669e1a7a26cd61dfffef11bb3a7de0a193639fabe"}, "validation_model": "fc0f9d144be21e1679646f90ac179a632ed005035e875cb201ed1b47848dbfe8", "style_policy": {"fluent-korean.md": "ce5aa71e58371e3fc02ff8cb165e07c9234f5166f6541423a91cc4cb40878975", "i-have-adhd.md": "3170b16ace00aecb0dd7feb54c0b5aa642e7502acda06ecd24fd89a11c7127e9", "README.md": "b87a84b1bc31079837dc4dc4527ce02c9dc2cbc3a26ff7e99e0872941d213995"}, "body_sha256": "030108e48a470f550ab58406e2346267916ceb93bfd1584ec1d79b4e1ab0a022"}
generated_visuals: {"schema": 1, "records": {"completion-branches": {"input_fingerprint": "79bf1e6721a303370e43a78c6058c8789f2b46bf0236ef2590b375cd07272df9", "draft": {"nodes": {"n0": {"label": "runPipes가 frame을 처리합니다.", "label_en": "runPipes processes frame.", "shape": "process", "quote_ids": ["on-frame:0"]}, "n1": {"label": "sendResult가 frame의 결과를 전송합니다.", "label_en": "sendResult sends the result for frame.", "shape": "process", "quote_ids": ["on-frame:0"]}, "n2": {"label": "onFrameDone이 frame의 완료를 처리합니다.", "label_en": "onFrameDone handles completion of frame.", "shape": "process", "quote_ids": ["on-frame:0"]}}, "edges": [{"from": "n0", "to": "n1", "label": "sendResult를 호출합니다.", "label_en": "Calls sendResult.", "condition_ref": "c0:true", "quote_ids": ["on-frame:0"]}, {"from": "n1", "to": "n2", "label": "onFrameDone을 호출합니다.", "label_en": "Calls onFrameDone.", "condition_ref": "c0:true", "quote_ids": ["on-frame:0"]}, {"from": "n0", "to": "n2", "label": "onFrameDone을 호출합니다.", "label_en": "Calls onFrameDone.", "condition_ref": "c0:false", "quote_ids": ["on-frame:0"]}]}, "graph": {"id": "completion-branches", "topic": "completion", "kind": "decision", "title": "파이프 결과와 완료 처리의 분기", "question": "RequestManager::onFrame에서 runPipes, sendResult, onFrameDone의 연결을 그리세요. 결과 전송 조건의 condition_ref를 원문 조건 ID의 참·거짓으로 선택하고 성공·실패 경로를 구분하세요. onFrameDone이 성공·실패 양쪽에서 호출되는 것을 보존하세요. 기기 동작이나 스레드 보장은 추정하지 마세요. 세 호출을 각각 한 노드로 표현하며 진입점·변수·성공실패별 가상 상태 노드는 추가하지 마세요. label과 label_en에는 함수의 역할만 적으세요. 비교식·숫자·성공실패 판정은 레이블에 쓰지 말고 분기는 현재 원문 조건의 condition_ref로만 지정하세요.", "nodes": [{"id": "n0", "label": "runPipes가 frame을 처리합니다.", "label_en": "runPipes processes frame.", "shape": "box", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}, {"id": "n1", "label": "sendResult가 frame의 결과를 전송합니다.", "label_en": "sendResult sends the result for frame.", "shape": "box", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}, {"id": "n2", "label": "onFrameDone이 frame의 완료를 처리합니다.", "label_en": "onFrameDone handles completion of frame.", "shape": "box", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}], "edges": [{"from": "n0", "to": "n1", "label": "sendResult를 호출합니다. · ret >= 0 [true]", "label_en": "Calls sendResult. · ret >= 0 [true]", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}, {"from": "n1", "to": "n2", "label": "onFrameDone을 호출합니다. · ret >= 0 [true]", "label_en": "Calls onFrameDone. · ret >= 0 [true]", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}, {"from": "n0", "to": "n2", "label": "onFrameDone을 호출합니다. · ret >= 0 [false]", "label_en": "Calls onFrameDone. · ret >= 0 [false]", "evidence": [{"source": "completion/on-frame", "sha256": "64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe", "quote": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}"}]}], "producer": "cli/codex/gpt-6.1-terra"}, "producer": "cli/codex/gpt-6.1-terra", "generation_commit": "0c92b75dd1f9fc2ac97d2ef08e246bc081faaf48", "citation_binding_policy": "identifier-boundaries-v1", "reused": true}}, "body_sha256": "030108e48a470f550ab58406e2346267916ceb93bfd1584ec1d79b4e1ab0a022"}
---

# 공개 mini HAL의 완료 분기

**파이프 반환 조건과 완료 정리를 소스와 함께 확인하세요.**



## 결과 전송과 프레임 정리

runPipes의 반환값이 0 이상이면 if 블록에서 sendResult를 호출하며, 음수이면 호출하지 않습니다. onFrameDone은 if 블록 밖에서 반환값과 관계없이 무조건 호출하므로 음수 반환 시에도 호출합니다. `src/device/RequestManager.cpp:37`

<!-- sdd:visual:completion-branches -->
### 파이프 결과와 완료 처리의 분기

```mermaid
flowchart TB
%% sdd:translations {"onFrameDone을 호출합니다. · <br/>ret #62;= 0 #91;false#93;": "Calls onFrameDone. · ret #62;= <br/>0 #91;false#93;", "onFrameDone을 호출합니다. · <br/>ret #62;= 0 #91;true#93;": "Calls onFrameDone. · ret #62;= <br/>0 #91;true#93;", "onFrameDone이 frame의 <br/>완료를 처리합니다.": "onFrameDone handles <br/>completion of frame.", "runPipes가 frame을 <br/>처리합니다.": "runPipes processes frame.", "sendResult가 frame의 결과를 <br/>전송합니다.": "sendResult sends the result <br/>for frame.", "sendResult를 호출합니다. · <br/>ret #62;= 0 #91;true#93;": "Calls sendResult. · ret #62;= <br/>0 #91;true#93;"}
  v_n0["runPipes가 frame을 <br/>처리합니다."]
  v_n1["sendResult가 frame의 결과를 <br/>전송합니다."]
  v_n2["onFrameDone이 frame의 <br/>완료를 처리합니다."]
  v_n0 -->|"sendResult를 호출합니다. · <br/>ret #62;= 0 #91;true#93;"| v_n1
  v_n1 -->|"onFrameDone을 호출합니다. · <br/>ret #62;= 0 #91;true#93;"| v_n2
  v_n0 -->|"onFrameDone을 호출합니다. · <br/>ret #62;= 0 #91;false#93;"| v_n2
```

[Mermaid 원문](completion.completion-branches.mmd)

??? note "그림 근거와 확인 범위"
    RequestManager::onFrame에서 runPipes, sendResult, onFrameDone의 연결을 그리세요. 결과 전송 조건의 condition_ref를 원문 조건 ID의 참·거짓으로 선택하고 성공·실패 경로를 구분하세요. onFrameDone이 성공·실패 양쪽에서 호출되는 것을 보존하세요. 기기 동작이나 스레드 보장은 추정하지 마세요. 세 호출을 각각 한 노드로 표현하며 진입점·변수·성공실패별 가상 상태 노드는 추가하지 마세요. label과 label_en에는 함수의 역할만 적으세요. 비교식·숫자·성공실패 판정은 레이블에 쓰지 말고 분기는 현재 원문 조건의 condition_ref로만 지정하세요.
    
    소스에 연결한 설계 해석입니다. 자동 연결 검사는 의미 승인이나 기기 실행 검증이 아닙니다.
    
    LLM 그림 초안 · 사람 검토 전
    
    작성 모델: `cli/codex/gpt-6.1-terra`
    
    | 요소·전이 | 소스 근거 |
    |---|---|
    | <span data-sdd-label-en="runPipes processes frame.">runPipes가 frame을 처리합니다.</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
    | <span data-sdd-label-en="sendResult sends the result for frame.">sendResult가 frame의 결과를 전송합니다.</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
    | <span data-sdd-label-en="onFrameDone handles completion of frame.">onFrameDone이 frame의 완료를 처리합니다.</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
    | <span data-sdd-label-en="Calls sendResult. · ret &gt;= 0 [true]">sendResult를 호출합니다. · ret &gt;= 0 &#91;true&#93;</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
    | <span data-sdd-label-en="Calls onFrameDone. · ret &gt;= 0 [true]">onFrameDone을 호출합니다. · ret &gt;= 0 &#91;true&#93;</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
    | <span data-sdd-label-en="Calls onFrameDone. · ret &gt;= 0 [false]">onFrameDone을 호출합니다. · ret &gt;= 0 &#91;false&#93;</span> | [src/device/RequestManager.cpp:37](#source-da034a9a1147d012) |
<!-- /sdd:visual:completion-branches -->

근거 원문: [src/device/RequestManager.cpp:37](#source-da034a9a1147d012)

??? note "설계 질문과 검증 범위"
    질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.
    
    | 설계 질문 | 설명 위치 | 확인 범위 |
    |---|---|---|
    | RequestManager::onFrame에서 runPipes 반환값에 따른 sendResult 조건과 onFrameDone 호출을 설명하세요. if 블록 안팎을 구분하고 실패 시 정리도 설명하세요. 실행 스레드나 성공 보장을 추정하지 마세요. | [결과 전송과 프레임 정리](#결과-전송과-프레임-정리) | 코드 근거와 설명 연결 |

## 소스 근거

같은 발췌는 한 번만 싣습니다. 필요한 원문을 펼쳐 설명과 대조하세요.

<a id="source-da034a9a1147d012"></a>

??? note "소스 근거: src/device/RequestManager.cpp:37"
    `src/device/RequestManager.cpp:37`에서 시작하는 발췌입니다. 종료 줄은 47이며, 아래 원문을 설명과 대조할 수 있습니다.
    
    SHA-256: `64ce50dbc9085701f44bbba8bc5573bc9ed24bb9eedbc15e7676446eb4f629fe`
    
    ```text
    void RequestManager::onFrame(Frame &frame) {
        FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)
                                                : static_cast<FrameFactory &>(captureFactory_);
        int ret = factory.runPipes(frame);
        if (ret >= 0) {
            sendResult(frame);
        }
        onFrameDone(frame);
    }
    
    void RequestManager::sendResult
    ```

??? note "근거와 검토 정보"
    - 생성 방식: 추출 사실과 LLM 설명
    - 검증 범위: 표·그림은 facts로 만들고 설명은 LLM이 작성합니다. 인용·문장 및 설정된 구조 검사를 적용합니다.
    - 근거 파일: `src/device/RequestManager.cpp`
    - 근거 수준: 코드 확인 (정적 분석, public-excerpt-fixture 구성, commit `0c92b75dd1`)
    - 자동 검사 (인용·문장 및 설정된 구조 검사): 통과
    - 검토 상태 기록일: 2026-11-05 · 사람 검토 전

다음 단계: [완료 분기](completion.md)
