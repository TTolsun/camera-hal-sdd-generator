요청 객체의 소유권은 호출자에게 전달되며, 완료 콜백에서 삭제하거나 `reuse()`를 통해 재사용할 수 있습니다 `src/libcamera/camera.cpp:1243`. 요청의 상태 초기화를 위해 `reuse()` 메서드를 호출하면 버퍼 매핑이 유지되거나 제거될 수 있으며, 이는 `ReuseBuffers` 플래그에 따라 결정됩니다 `src/libcamera/request.cpp:376`.

버퍼에 연결된 페인스 (fence) 는 `addBuffer()`를 통해 요청에 이동되며, 모든 페인이 신호가 될 때까지 요청은 큐에 추가되지 않습니다 `src/libcamera/request.cpp:442`. 페인이 아직 신호되지 않은 경우 요청 실패 후 버퍼는 여전히 페인을 참조하므로, 재사용 전에 `releaseFence()`로 페인을 해제해야 합니다.
