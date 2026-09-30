libcamera 의 `Camera::createRequest()` 메서드는 요청 객체의 소유권을 호출자에게 이양하며, 해당 객체는 완료 콜백에서 삭제되거나 상태 초기화를 통해 재사용될 수 있습니다 `src/libcamera/camera.cpp:1243`. 요청이 재사용되려면 먼저 `Request::reuse()` 를 호출하여 상태와 컨트롤을 초기화해야 하며, 이때 `ReuseBuffers` 플래그를 설정하면 이전에 추가된 버퍼가 다시 요청에 연결됩니다 `src/libcamera/request.cpp:376`.

버퍼를 요청에 추가할 때는 `Request::addBuffer()` 메서드를 사용하며, 이 함수는 호출자가 버퍼의 유효성을 완료 콜백까지 유지하도록 보장해야 합니다 `src/libcamera/request.cpp:442`. 만약 버퍼에 신호되지 않은 펜스가 연결되어 있으면 요청이 타임아웃될 수 있으므로, 재사용 전에 `FrameBuffer::releaseFence()` 를 통해 펜스를 해제해야 합니다.
