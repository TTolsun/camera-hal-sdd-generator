동기 호출은 `IPCPipeUnixSocket::sendSync` 메서드를 통해 블로킹 방식으로 실행되며, 비동기 호출은 `IPCPipeUnixSocket::sendAsync` 메서드를 사용하여 큐에 추가됩니다 `src/libcamera/ipc_pipe_unixsocket.cpp:27`.

`{{proxy_name}}Threaded` 클래스는 이벤트 핸들러를 별도의 스레드에서 처리하고, `{{proxy_name}}Isolated` 클래스는 IPC 파이프를 통해 격리된 프로세스와 통신합니다 `utils/codegen/ipc/generators/libcamera_templates/module_ipa_proxy.cpp.tmpl:48`.

동기 호출 시 응답을 기다리는 로직은 `IPCPipeUnixSocket::call` 내부의 타임아웃 처리와 이벤트 루프 처리에 의존하며, 구체적인 실행 순서와 스레드 동기화 메커니즘은 추가 확인이 필요합니다 `src/libcamera/ipc_pipe_unixsocket.cpp:104`.
