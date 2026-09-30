동기 호출과 비동기 호출은 `{{proxy_name}}Threaded` 클래스에서 구현되며, 동기 메서드는 스레드 내에서 즉시 실행되고 비동기 메서드는 `invokeMethod`를 통해 큐에 배치된 후 처리됩니다. `{{proxy_name}}Threaded::start()` 정의를 먼저 확인합니다 `utils/codegen/ipc/generators/libcamera_templates/module_ipa_proxy.cpp.tmpl:48`.

`{{proxy_name}}Isolated` 클래스는 IPC 피프라인을 통해 프로세스 경계를 넘어 통신하며, 동기 호출은 `sendSync`를 사용하여 블로킹 처리하고 비동기 호출은 `sendAsync`를 사용하여 큐에 대기합니다. `IPCPipeUnixSocket::sendSync()`와 `sendAsync()` 정의를 먼저 확인합니다 `src/libcamera/ipc_pipe_unixsocket.cpp:27`.
