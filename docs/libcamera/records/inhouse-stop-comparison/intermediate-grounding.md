- **`FrameCancelled`의 데이터 유효성 설명이 잘못됐습니다.** 원고는 “프레임 데이터와 상태 필드를 제외한 메타데이터 필드는 유효하지 않습니다”라고 두 차례 적어 프레임 데이터가 예외인 것처럼 읽힙니다. `vendor-contract/completion/frame-status`와 `vendor-contract/ownership/frame-status`는 “frame data is not valid”이며 메타데이터는 “but the status field” 모두 무효라고 명시합니다. 즉 프레임 데이터도 무효이고, 메타데이터에서는 `status`만 유효합니다.

- **요청 완료와 프레임 성공은 구분해야 합니다.** `vendor-contract/completion/request-status`에서 `FrameCancelled` 버퍼는 `cancelled_`를 참으로 만들고, `complete()`는 그 값에 따라 `RequestCancelled` 또는 `RequestComplete`를 설정합니다. 반면 `vendor-contract/completion/frame-status`의 `FrameError`는 프레임 데이터가 손상되거나 없거나 무효일 수 있다는 뜻입니다. 제공된 발췌에는 `FrameError` 자체가 요청을 취소한다는 조건이 없으므로, `RequestComplete`만으로 모든 버퍼의 프레임 데이터가 정상이라고 판단할 수 없습니다. 원고의 “정상 완료”는 이 구분을 명확히 해야 합니다.

- **정지 반환과 알림 수신은 같은 사실이 아닙니다.** `vendor-contract/completion/stop`에 따르면 실행 중이 아니면 바로 `0`을 반환하고, 접근 검사에 실패하면 음수 오류를 반환합니다. 실행 중 검사에 성공한 경로에서만 블로킹 방식으로 `PipelineHandler::stop`을 호출한 뒤 대기 요청이 없다고 단언하고 `0`을 반환합니다. 따라서 `0`만으로 그 호출이 실제 정지 절차를 수행했다고 단정할 수 없습니다. 또한 이 발췌는 애플리케이션이 모든 완료 신호를 **수신하거나 콜백 처리를 끝낸 시점**과 `stop()` 반환의 관계를 명시하지 않습니다.

- **정지 중 요청 처리의 범위는 원고와 대체로 맞지만 장치 구현은 미확인입니다.** `vendor-contract/completion/pipeline-stop`은 별도로 옮긴 *waiting requests*를 `stopDevice()` 뒤에 취소하고 완료 처리한다고 밝힙니다. 이미 장치에 큐된 요청은 “let the queued requests complete”라고만 되어 있어, 각각 정상 완료되는지 취소되는지와 구체적 완료 방식은 발췌만으로 확정할 수 없습니다.

- **지연된 통지는 요청의 내부 완료와 구별해야 합니다.** `vendor-contract/completion/completion`에서 요청을 먼저 `complete()` 처리한 뒤 큐 앞이 `RequestPending`이면 순회를 멈춥니다. 따라서 뒤쪽 요청은 이미 내부 완료 상태여도 앞 요청 때문에 그 시점에 통지되지 않을 수 있다는 원고의 설명은 맞습니다. `vendor-contract/ownership/completion`은 애플리케이션에 제출 순서대로 반환하도록 한다고 명시하지만, 제공된 발췌는 신호 전달 방식이나 애플리케이션의 실제 수신 지연 및 콜백 스레드를 확정하지 않습니다. 제출 측의 `ConnectionTypeQueued`와 `return 0`만으로도 제출 반환과 완료 통지의 선후 관계를 확정할 수 없습니다(`vendor-contract/completion/queue`).

- **버퍼 반환 후에도 별도 작업의 종료는 확인되지 않았습니다.** `vendor-contract/ownership/notification`은 버퍼와 요청의 완료 신호를 정의하고, `vendor-contract/ownership/reuse`는 요청 재큐 전에 `reuse()`를 호출하도록 합니다. 그러나 발췌에는 애플리케이션이나 다른 소비자가 버퍼를 이용하는 작업의 수명, 신호 수신 후 언제 안전하게 버퍼를 재사용할 수 있는지에 관한 추가 보장이 없습니다. 원고의 실행 확인 항목은 여전히 미확인 조건입니다.

- **fence 해제는 소유권 추출이며, 작업 완료의 증거는 아닙니다.** `vendor-contract/ownership/fence`는 fence 처리 실패로 오류 완료된 버퍼를 다시 `addBuffer()` 하기 전에 fence를 해제해야 하고, `releaseFence()`가 그 소유권을 호출자에게 옮긴다고 명시합니다. `vendor-contract/ownership/add-buffer`도 버퍼에 fence가 남아 있으면 `-EEXIST`를 반환합니다. 다만 발췌에는 fence 추출 자체가 fence 신호, 관련 작업 완료 또는 안전한 버퍼 재사용을 보장한다는 내용이 없습니다. `ReuseBuffers` 경로에 같은 검사가 적용되는지도 제공된 코드만으로는 확인되지 않습니다.

이 검토는 제공된 발췌에 한정한 근거 검토이며, 사람의 의미 승인이나 기기 실행 검증을 대신하지 않습니다.
