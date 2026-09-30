`queueRequest` 메서드는 요청이 카메라에 의해 생성되었는지, 상태가 Pending 인지, 버퍼가 비어있지 않은지, 그리고 스트림이 활성화되어 있는지 확인한 후 `PipelineHandler::queueRequest`를 호출합니다 [src/libcamera/camera.cpp:1308]. 이 과정에서 접근 권한이 없는 경우나 요청이 유효하지 않은 경우 `-EACCES`, `-EINVAL`, `-EXDEV` 등의 오류 코드를 반환하며, 요청 완료는 `requestCompleted` 신호를 통해另行通知됩니다 [src/libcamera/camera.cpp:1308].

`stop` 메서드는 카메라가 Running 상태인지 확인하고 접근 권한을 검증한 뒤 `PipelineHandler::stop`을 호출하여 캡처를 즉시 중단합니다 [src/libcamera/camera.cpp:1431]. 모든 대기 중인 요청이 오류 상태로 동기적으로 완료된 후 상태는 `CameraConfigured`로 복귀되지만, 실행되지 않은 상태일 경우 무작동 처리됩니다 [src/libcamera/camera.cpp:1431].
