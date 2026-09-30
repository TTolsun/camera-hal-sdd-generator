<!-- system -->
당신은 libcamera(C/C++) 설계 문서의 본문을 쓰는 기술 문서 작성자입니다. 독자는 공개 소스로 사내 Camera HAL 문서화 파이프라인을 검증하는 개발자입니다.

1. 사실 블록에 있는 내용만 서술합니다. libcamera 자체를 Android Camera HAL 구현이라고 단정하지 않습니다.
2. 클래스, 함수, 호출 관계를 설명하는 문장에는 사실 블록에 존재하는 `파일:줄` 인용을 붙입니다.
3. 스레드, 프로세스 경계, 콜백 순서, 설계 의도는 근거가 부족하면 "확인 필요: 확인할 항목"으로 남깁니다.
4. Markdown 본문만 출력합니다. 제목, 표, 다이어그램은 파이프라인이 만듭니다.
5. 문단마다 한 가지 주제를 다루고, 독자가 먼저 확인할 코드 위치를 설명합니다.
6. 메서드 목록은 호출 순서나 내부 호출 관계의 근거가 아닙니다. 메서드 이름만 보고 소유권, 콜백 전달, 스레드 동기화, 실행 순서를 만들어 내지 않습니다.
7. 본문은 짧은 두 문단으로 제한합니다. 번호 목록, 코드 블록, 결론 요약을 추가하지 않습니다. 사실이 비어 있으면 설명을 만들지 말고 근거 누락을 명시합니다.

---

개발자 가이드 집필 규칙:
1. 각 페이지는 독자가 먼저 할 일이나 알아야 할 결론으로 시작합니다. 절차는 번호를 붙이고, 한 단계에는 한 가지 작업을 씁니다.
2. 문단은 한 가지 주제를 설명합니다. 목록이 길면 주제별로 나누되, 조건·예외·미구현 사항을 삭제해서 길이를 줄이지 않습니다.
3. 조사와 서술어를 갖춘 한국어 문장을 씁니다. 제목·표의 열 이름·코드 식별자는 필요한 만큼 짧게 유지합니다. 코드, 주석, 로그 문자열, 인용문은 원문을 보존합니다.
4. 페이지 끝에는 관련 절차나 다음에 읽을 문서 하나를 연결합니다. 대화의 진행 상태나 작업 시간 추정은 문서에 넣지 않습니다. 관측 시간과 실패 횟수처럼 코드로 확인한 수치는 그대로 유지합니다.
5. 코드로 확인한 동작, 설계 결정, 기기 관찰 기록을 구분합니다. 설명이 부족한 부분은 무엇을 확인해야 하는지 적고, 근거가 없는 확신이나 설계 이유를 추가하지 않습니다.

<!-- user -->
절: 스레드와 프로세스 경계
독자: 영상 처리 알고리즘과 프로세스 경계를 분석하는 개발자

이 절이 답해야 하는 질문:
- 동기 호출과 비동기 호출은 어디에서 실행됩니까?

사실 (이 목록 밖의 내용은 쓰지 않습니다):
소스 발췌 `utils/codegen/ipc/generators/libcamera_templates/module_ipa_proxy.cpp.tmpl:48`
{{proxy_name}}Threaded::{{proxy_name}}Threaded(IPAModule *ipam, const CameraManager &cm)
	: {{proxy_name}}(ipam, cm), thread_("{{proxy_name}}")
{
	LOG(IPAProxy, Debug)
		<< "initializing {{module_name}} proxy in thread: loading IPA from "
		<< ipam->path();

	if (!ipam->load())
		return;

	IPAInterface *ipai = ipam->createInterface();
	if (!ipai) {
		LOG(IPAProxy, Error)
			<< "Failed to create IPA context for " << ipam->path();
		return;
	}

	ipa_ = std::unique_ptr<{{interface_name}}>(static_cast<{{interface_name}} *>(ipai));
	proxy_.setIPA(ipa_.get());

{% for method in interface_event.methods %}
	ipa_->{{method.mojom_name}}.connect(this, &{{proxy_name}}Threaded::{{method.mojom_name}}Handler);
{%- endfor %}

	valid_ = true;
}

{{proxy_name}}Threaded::~{{proxy_name}}Threaded() = default;

{% for method in interface_main.methods %}
{{proxy_funcs.func_sig(proxy_name + "Threaded", method)}}
{
{%- if method.mojom_name == "stop" %}
	{{proxy_funcs.stop_thread_body()}}
{%- elif method.mojom_name == "init" %}
	{{ method|method_return_value + " _ret = " if method|method_return_value != "void" -}}
	ipa_->{{method.mojom_name}}(
	{%- for param in method|method_param_names -%}
		{{param}}{{- ", " if not loop.last}}
	{%- endfor -%}
);

	proxy_.moveToThread(&thread_);

	return {{ "_ret" if method|method_return_value != "void" }};
{%- elif method.mojom_name == "start" %}
	state_ = ProxyRunning;
	thread_.start();

	return proxy_.invokeMethod(&ThreadProxy::start, ConnectionTypeBlocking
	{{- ", " if method|method_param_names}}
	{%- for param in method|method_param_names -%}
		{{param}}{{- ", " if not loop.last}}
	{%- endfor -%}
);
{%- elif not method|is_async %}
	return ipa_->{{method.mojom_name}}(
	{%- for param in method|method_param_names -%}
		{{param}}{{- ", " if not loop.last}}
	{%- endfor -%}
);
{% elif method|is_async %}
	ASSERT(state_ == ProxyRunning);
	proxy_.invokeMethod(&ThreadProxy::{{method.mojom_name}}, ConnectionTypeQueued
	{%- for param in method|method_param_names -%}
		, {{param}}
	{%- endfor -%}
);
{%- endif %}
}
{% endfor %}

{% for method in interface_event.methods %}
{{proxy_funcs.func_sig(proxy_name + "Threaded", method, "Handler")}}
{
	ASSERT(state_ != ProxyStopped);
	{{method.mojom_name}}.emit({{method.parameters|params_comma_sep}});
}
{% endfor %}

/* ========================================================================== */

소스 발췌 `utils/codegen/ipc/generators/libcamera_templates/module_ipa_proxy.cpp.tmpl:130`
{{proxy_name}}Isolated::{{proxy_name}}Isolated(IPAModule *ipam, const CameraManager &cm)
	: {{proxy_name}}(ipam, cm),
	  controlSerializer_(ControlSerializer::Role::Proxy), seq_(0)
{
	LOG(IPAProxy, Debug)
		<< "initializing {{module_name}} proxy in isolation: loading IPA from "
		<< ipam->path();

	const std::string proxyWorkerPath = resolvePath("{{module_name}}_ipa_proxy");
	if (proxyWorkerPath.empty()) {
		LOG(IPAProxy, Error) << "Failed to get proxy worker path";
		return;
	}

	auto ipc = std::make_unique<IPCPipeUnixSocket>(ipam->path().c_str(),
						       proxyWorkerPath.c_str());
	if (!ipc->isConnected()) {
		LOG(IPAProxy, Error) << "Failed to create IPCPipe";
		return;
	}

	ipc->recv.connect(this, &{{proxy_name}}Isolated::recvMessage);

	ipc_ = std::move(ipc);
	valid_ = true;
}

{{proxy_name}}Isolated::~{{proxy_name}}Isolated()
{
	if (ipc_) {
		IPCMessage::Header header =
			{ static_cast<uint32_t>({{cmd_enum_name}}::Exit), seq_++ };
		IPCMessage msg(header);
		ipc_->sendAsync(msg);
	}
}

{% for method in interface_main.methods %}
{{proxy_funcs.func_sig(proxy_name + "Isolated", method)}}
{
{%- if method.mojom_name == "configure" %}
	controlSerializer_.reset();
{%- endif %}
{%- set has_output = true if method|method_param_outputs|length > 0 or method|method_return_value != "void" %}
{%- set cmd = cmd_enum_name + "::" + method.mojom_name|cap %}
	IPCMessage::Header _header = { static_cast<uint32_t>({{cmd}}), seq_++ };
	IPCMessage _ipcInputBuf(_header);
{%- if has_output %}
	IPCMessage _ipcOutputBuf;
{%- endif %}

{{proxy_funcs.serialize_call(method|method_param_inputs, '_ipcInputBuf.data()', '_ipcInputBuf.fds()')}}

{% if method|is_async %}
	int _ret = ipc_->sendAsync(_ipcInputBuf);
{%- else %}
	int _ret = ipc_->sendSync(_ipcInputBuf
{{- ", &_ipcOutputBuf" if has_output -}}
);
{%- endif %}
	if (_ret < 0) {
		LOG(IPAProxy, Error) << "Failed to call {{method.mojom_name}}: " << _ret;
{%- if method|method_return_value != "void" %}
		return static_cast<{{method|method_return_value}}>(_ret);
{%- else %}
		return;
{%- endif %}
	}
{% if method|method_return_value != "void" %}
	{{method|method_return_value}} _retValue = IPADataSerializer<{{method|method_return_value}}>::deserialize(_ipcOutputBuf.data(), 0);

{{proxy_funcs.deserialize_call(method|method_param_outputs, '_ipcOutputBuf.data()', '_ipcOutputBuf.fds()', init_offset = method|method_return_value|byte_width|int)}}

	return _retValue;

{% elif method|method_param_outputs|length > 0 %}
{{proxy_funcs.deserialize_call(method|method_param_outputs, '_ipcOutputBuf.data()', '_ipcOutputBuf.fds()')}}
{% endif -%}
}

{% endfor %}

void {{proxy_name}}Isolated::recvMessage(

소스 발췌 `src/libcamera/ipa_proxy.cpp:204`
\brief Find a valid full path for a proxy worker for a given executable name
 * \param[in] file File name of proxy worker executable
 *
 * A proxy worker's executable could be found in either the global installation
 * directory, or in the paths specified by the environment variable
 * LIBCAMERA_IPA_PROXY_PATH. This function checks the global install directory
 * first, then LIBCAMERA_IPA_PROXY_PATH in order, and returns the full path to
 * the proxy worker executable that is specified by file. The proxy worker
 * executable shall have exec permission.
 *
 * \return The full path to the proxy worker executable, or an empty string if
 * no valid executable path
 */
std::string IPAProxy::resolvePath(const std::string &file) const
{
	std::string proxyFile = "/" + file;

	/* Try paths from the configuration first. */
	for (const auto &dir : execPaths_) {
		if (dir.empty())
			continue;

		std::string proxyPath = dir + proxyFile;
		if (!access(proxyPath.c_str(), X_OK))
			return proxyPath;
	}

	/*
	 * When libcamera is used before it is installed, load proxy workers
	 * from the same build directory as the libcamera directory itself.
	 * This requires identifying the path of the libcamera.so, and
	 * referencing a relative path for the proxy workers from that point.
	 */
	std::string root = utils::libcameraBuildPath();
	if (!root.empty()) {
		std::string ipaProxyDir = root + "src/libcamera/proxy/worker";

		LOG(IPAProxy, Info)
			<< "libcamera is not installed. Loading proxy workers from '"
			<< ipaProxyDir << "'";

		std::string proxyPath = ipaProxyDir + proxyFile;
		if (!access(proxyPath.c_str(), X_OK))
			return proxyPath;

		return std::string();
	}

	/* Else try finding the exec target from the install directory. */
	std::string proxyPath = std::string(IPA_PROXY_DIR) + proxyFile;
	if (!access(proxyPath.c_str(), X_OK))
		return proxyPath;

	return std::string();
}

/**
 * \var IPAProxy::valid_

소스 발췌 `src/libcamera/ipc_pipe_unixsocket.cpp:27`
IPCPipeUnixSocket::IPCPipeUnixSocket(const char *ipaModulePath,
				     const char *ipaProxyWorkerPath)
	: IPCPipe()
{
	socket_ = std::make_unique<IPCUnixSocket>();
	UniqueFD fd = socket_->create();
	if (!fd.isValid()) {
		LOG(IPCPipe, Error) << "Failed to create socket";
		return;
	}
	socket_->readyRead.connect(this, &IPCPipeUnixSocket::readyRead);

	std::array args{ std::string(ipaModulePath), std::to_string(fd.get()) };
	std::array fds{ fd.get() };

	proc_ = std::make_unique<Process>();
	int ret = proc_->start(ipaProxyWorkerPath, args, fds);
	if (ret) {
		LOG(IPCPipe, Error)
			<< "Failed to start proxy worker process";
		return;
	}

	connected_ = true;
}

IPCPipeUnixSocket::~IPCPipeUnixSocket()
{
}

int IPCPipeUnixSocket::sendSync(const IPCMessage &in, IPCMessage *out)
{
	IPCUnixSocket::Payload response;

	int ret = call(in.payload(), &response, in.header().cookie);
	if (ret) {
		LOG(IPCPipe, Error) << "Failed to call sync";
		return ret;
	}

	if (out)
		*out = IPCMessage(response);

	return 0;
}

int IPCPipeUnixSocket::sendAsync(const IPCMessage &data)
{
	int ret = socket_->send(data.payload());
	if (ret) {
		LOG(IPCPipe, Error) << "Failed to call async";
		return ret;
	}

	return 0;
}

void IPCPipeUnixSocket::readyRead()
{
	IPCUnixSocket::Payload payload;
	int ret = socket_->receive(&payload);
	if (ret) {
		LOG(IPCPipe, Error) << "Receive message failed" << ret;
		return;
	}

	/* \todo Use span to avoid the double copy when callData is found. */
	if (payload.data.size() < sizeof(IPCMessage::Header)) {
		LOG(IPCPipe, Error) << "Not enough data received";
		return;
	}

	IPCMessage ipcMessage(payload);

	auto callData = callData_.find(ipcMessage.header().cookie);
	if (callData != callData_.end()) {
		*callData->second.response = std::move(payload);
		callData->second.done = true;
		return;
	}

	/* Received unexpected data, this means it's a call from the IPA. */
	recv.emit(ipcMessage);
}

int IPCPipeUnixSocket::call(const IPCUnixSocket::Payload &message,
			    IPCUnixSocket::Payload *response, uint32_t cookie)
{
	Timer timeout;
	int ret;

	const auto result = callData_.insert({ cookie, { response, false } });
	const auto &iter = result.first;

	ret = socket_->send(message);
	if (ret) {
		callData_.erase(iter);
		return ret;
	}

	/* \todo Make this less dangerous, see IPCPipe::sendSync() */
	timeout.start(2000ms);
	while (!iter->second.done) {
		if (!timeout.isRunning()) {
			LOG(IPCPipe, Error) << "Call timeout!";
			callData_.erase(iter);
			return -ETIMEDOUT;
		}

		Thread::current()->eventDispatcher()->processEvents();
	}

	callData_.erase(iter);

	return 0;
}

} /* namespace libcamera */

기존 본문:
(없음)

위 사실을 근거로 짧은 두 문단만 씁니다. 각 기술적 설명에 사실 목록의 `파일:줄` 인용을 붙입니다. 예를 들어 메서드 선언만 주어졌다면 그 메서드의 위치를 확인하도록 안내하고 내부 동작이나 호출 순서는 추측하지 않습니다. 사실이 부족하면 확인할 항목을 명시합니다.

인용 형식의 예시: `ExampleOwner`의 `create()` 정의를 먼저 확인합니다 `dir/ExampleOwner.cpp:40`.
이 예시의 클래스와 위치는 출력에 사용하지 않습니다. 실제 사실 목록의 클래스와 위치로 바꿉니다. 인용 위치는 반드시 백틱으로 감싸고 대괄호를 사용하지 않습니다. 모든 기술 설명 문장에 인용을 붙입니다. 지시문이나 이전 출력의 문제 목록을 되풀이하지 말고 본문만 출력합니다.

본문:

