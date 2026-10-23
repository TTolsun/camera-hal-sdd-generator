# 공개 카메라 모델 문서의 충분성 검토

**판정: 소스를 읽기 전에 계약을 파악하는 검토 초안으로는 쓸 수 있습니다. 그러나 버퍼 수명과 스레드 계약이 빠져 있어서, 요청 처리 변경을 검토하는 근거 문서로는 아직 부족합니다.** 2026-09-26에 [게시된 카메라와 요청 모델](https://ttolsun.github.io/libcamera-sdd/camera-model.html)의 실제 HTML을 읽고, 본문의 주장을 같은 커밋의 libcamera 소스와 한 문장씩 대조했습니다.

| 항목 | 값 |
|---|---|
| 분석 기준 커밋 | `279d355ef8f7a4f98bb0a3004c0f788387814506` |
| 문서 생성 시각 | 2026-09-24 14:05:15+00:00 |
| 문장 생성 모델 | `ollama/qwen3.5:4b` |
| 표시 상태 | 사람 검토 전, 자동 검사 `ok` |

`ok`는 인용한 위치가 facts에 존재한다는 뜻입니다. 이 평가는 사람이 내용을 검토한 기록이지만, 이 기록만으로 문서를 사람 검토 통과로 승격하지 않습니다.

## 이전 판(2026-09-21) 대비 변화

이전 판은 세 클래스의 책임이 모두 "확인 필요"였고 설명이 한 문단뿐이었습니다. 현재 판은 여덟 개 절로 나뉘었고, 모든 문장에 코드 위치가 붙었습니다.

| 이전 판에서 지적한 문제 | 현재 판의 상태 |
|---|---|
| 세 클래스의 책임이 "확인 필요"입니다. | 해결되었습니다. CameraManager·Camera·Request의 책임을 각각 코드 근거로 설명합니다. |
| 대괄호 인용이 검사 규약을 충족하지 않습니다. | 해결되었습니다. 인용 검사가 `ok`로 통과합니다. |
| 요청의 생성·버퍼 연결·완료·재사용 설명이 없습니다. | 대부분 해결되었습니다. 버퍼 자체의 수명 계약은 여전히 빠져 있습니다(아래 1번). |
| 상태 전이와 실패·취소·종료 계약이 없습니다. | 해결되었습니다. 상태도 전이, `queueRequest()` 오류 코드, `stop()`의 취소 동작을 설명합니다. |
| 스레드와 동기화 제약이 없습니다. | 일부 해결되었습니다. 호출자 동기화 책임은 설명하지만, 완료 통지 스레드는 "확인 필요"로 남았습니다(아래 2번). |
| 그림이 상속 관계만 보여 줍니다. | 해결되지 않았습니다. 그림은 여전히 다섯 노드와 다섯 상속 관계뿐입니다. |

## 코드와 대조한 결과: 맞게 쓴 내용

다음 주장은 소스와 일치하며, 오해하기 쉬운 지점을 스스로 한정한 점도 좋습니다.

- **상태 전이**: Available → Acquired → Configured → Running, `stop()`이 Stopping을 거쳐 Configured로 돌아가는 경로가 [상태도](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/camera.cpp#L789)와 같습니다. "상태도에 없는 호출까지 금지된 것으로 해석하지 않는다"는 문장도 원문과 일치합니다.
- **`stop()`의 반환값**: API 주석에는 `-EACCES`가 적혀 있지만 구현은 실행 중이 아니면 즉시 0을 반환합니다. 문서가 이 차이를 짚어서 잘못된 해석을 막습니다.
- **`queueRequest()` 오류**: `-ENODEV`, `-EACCES`, `-EXDEV`, `-EINVAL`은 구현과 일치합니다. `-ENOMEM`은 구현에서 직접 반환하지 않는데, 문서가 "API가 명시한다"고 한정해서 썼습니다.
- **fence 소유권**: `addBuffer()`가 성공한 경우에만 fence가 버퍼로 이동하고, 타임아웃된 fence는 `releaseFence()`로 꺼내야 한다는 설명이 [원문](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/request.cpp#L464)과 같습니다.
- **threadsafe 범위**: `createRequest()`와 `queueRequest()`의 threadsafe 보장을 다른 Request 메서드로 확대하지 않는다고 명시합니다.

## 보완이 필요한 내용

| 우선순위 | 관찰한 문제 | 설계 검토에 미치는 영향 | 근거 위치 |
|---|---|---|---|
| 높음 | 1. 문서는 "이 근거만으로 프레임 버퍼의 소유권 이전을 단정하지 않는다"고 씁니다. 그러나 인용한 `addBuffer()` 주석 안에 "호출자가 완료 콜백까지 버퍼의 유효성을 보장해야 한다"는 계약이 있습니다. | 버퍼를 언제 해제해도 되는지 판단할 수 없습니다. 근거를 인용하고도 핵심 계약을 놓쳤습니다. | [request.cpp:447](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/request.cpp#L447) |
| 높음 | 2. 완료 통지 스레드를 "확인 필요"로 남겼습니다. 소스에는 `PipelineHandler::completeRequest()`를 CameraManager 스레드에서 호출해야 하고, 반환 후 파이프라인이 요청에 접근하지 않으며, 제출 순서대로 완료를 돌려준다는 계약이 있습니다. | 완료 핸들러에서 무엇을 해도 되는지, 완료 순서에 의존해도 되는지 판단할 수 없습니다. | [pipeline_handler.cpp:571](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/pipeline_handler.cpp#L571) |
| 높음 | 3. `queueRequest()`가 파이프라인을 `ConnectionTypeQueued`로 호출한다는 사실이 빠졌습니다. 반환값 0은 "큐에 넣었다"는 뜻이지 "장치에 제출했다"는 뜻이 아닙니다. | 반환 직후 요청이 처리 중이라고 오해할 수 있습니다. | [camera.cpp:1356](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/camera.cpp#L1356), [camera.cpp:1377](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/camera.cpp#L1377) |
| 보통 | 4. `reuse(ReuseBuffers)`는 fence를 재사용하지 않으며, fence를 쓰는 경우 이 플래그를 쓰지 말라는 주의가 빠졌습니다. `addBuffer()`의 `-EEXIST`(같은 스트림 중복, fence가 남은 버퍼) 조건도 없습니다. | fence와 버퍼 재사용을 함께 쓰는 경로에서 잘못 구현할 수 있습니다. | [request.cpp:333](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/request.cpp#L333) |
| 보통 | 5. 허용되지 않은 상태에서의 호출이 "정의되지 않은 동작"이라는 계약과, `disconnected` 신호 이후 모든 API 호출이 오류를 반환한다는 계약이 빠졌습니다. | 오류 처리와 핫플러그 경로를 검토할 수 없습니다. | [camera.cpp:789](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/camera.cpp#L789), [camera.cpp:925](https://github.com/TTolsun/libcamera-sdd/blob/279d355ef8f7a4f98bb0a3004c0f788387814506/src/libcamera/camera.cpp#L925) |
| 보통 | 6. 본문이 상태 전이를 설명하지만 그림은 상속 관계만 보여 줍니다. | 상태와 요청 흐름을 그림으로 확인할 수 없습니다. | — |
| 낮음 | 7. 인용이 함수 주석의 `\brief` 줄(예: `camera.cpp:1308`)을 가리킵니다. 오류 코드, 큐잉 방식처럼 서로 다른 주장이 모두 같은 줄을 인용합니다. | 검토자가 주장마다 주석 블록 전체를 다시 읽어야 합니다. | — |

## 반복 생성 시스템에 반영할 기준

원고를 한 번 손으로 고치는 것으로 끝내지 않고, 다음 결함이 반복되지 않도록 생성기를 보강해야 합니다.

1. **클래스 밖의 근거 공급**: 2번 결함은 근거가 이 문서의 선택 클래스가 아닌 PipelineHandler에 있어서 생겼습니다. 스레드·완료 계약 같은 질문에는, 해당 신호를 발생시키는 호출 경로의 `\context` 주석을 facts로 함께 공급해야 합니다.
2. **인용한 주석 전체의 활용 점검**: 1번 결함은 근거를 인용하고도 그 안의 계약을 놓친 경우입니다. 인용한 주석 블록에 "responsible", "shall", "must" 같은 계약 문구가 있는데 본문이 다루지 않으면 검토 과제로 표시할 수 있습니다.
3. **그림의 근거 확대**: 상태도는 LLM이 그리지 않고 facts에서만 만든다는 원칙을 유지합니다. 그러려면 Doxygen `\dot` 상태도 같은 소스 내 구조 정보를 추출 대상에 넣어야 합니다.
4. **주장 단위 인용**: 인용이 `\brief` 줄이 아니라 주장이 실제로 기대는 줄을 가리키도록 위치 정보를 세분화해야 합니다.

근거가 없는 상태도나 호출 순서를 LLM으로 채우거나, 자동 검사 `ok`를 사람 검토 통과로 바꾸면 안 됩니다. 이번 작업에서는 평가만 기록했으며 공개 원고를 재생성하거나 재배포하지 않았습니다. 이 평가는 libcamera 테스트 결과이며, 사내 HAL에서는 프로젝트 고유의 요청·버퍼·콜백·종료 계약을 다시 검증해야 합니다.
