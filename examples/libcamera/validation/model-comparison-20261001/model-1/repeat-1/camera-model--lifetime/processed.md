요청 객체의 소유권은 호출자에게 전달되며, 완료 콜백에서 삭제하거나 `reuse()` 를 통해 상태 초기화 후 재사용할 수 있습니다 `src/libcamera/camera.cpp:1243`. 요청이 삭제될 때나 재사용될 때 버퍼의 소유권 처리는 해당 메서드의 구현을 확인해야 합니다.

버퍼에 `fence` 가 연결된 경우, `addBuffer()` 를 호출하여 요청에 추가할 때에만 fence 의 소유권이 요청에게 이전되며, 이는 모든 buffer 의 fence 가 신호링되어야만 요청이 큐에 등록됩니다 `src/libcamera/request.cpp:376`, `src/libcamera/request.cpp:442`.
