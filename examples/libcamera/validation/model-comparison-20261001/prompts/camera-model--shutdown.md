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
절: 오류와 종료
독자: libcamera의 공개 API를 분석하는 개발자

이 절이 답해야 하는 질문:
- queueRequest의 오류 조건과 stop의 취소·완료·복귀 상태를 설명하세요.

사실 (이 목록 밖의 내용은 쓰지 않습니다):
소스 발췌 `src/libcamera/camera.cpp:1308`
\brief Queue a request to the camera
 * \param[in] request The request to queue to the camera
 *
 * This function queues a \a request to the camera for capture.
 *
 * After allocating the request with createRequest(), the application shall
 * fill it with at least one capture buffer before queuing it. Requests that
 * contain no buffers are invalid and are rejected without being queued.
 *
 * Once the request has been queued, the camera will notify its completion
 * through the \ref requestCompleted signal.
 *
 * \context This function is \threadsafe. It may only be called when the camera
 * is in the Running state as defined in \ref camera_operation.
 *
 * \return 0 on success or a negative error code otherwise
 * \retval -ENODEV The camera has been disconnected from the system
 * \retval -EACCES The camera is not running so requests can't be queued
 * \retval -EXDEV The request does not belong to this camera
 * \retval -EINVAL The request is invalid
 * \retval -ENOMEM No buffer memory was available to handle the request
 */
int Camera::queueRequest(Request *request)
{
	Private *const d = _d();

	int ret = d->isAccessAllowed(Private::CameraRunning);
	if (ret < 0)
		return ret;

	/* Requests can only be queued to the camera that created them. */
	if (request->_d()->camera() != this) {
		LOG(Camera, Error) << "Request was not created by this camera";
		return -EXDEV;
	}

	if (request->status() != Request::RequestPending) {
		LOG(Camera, Error) << request->toString() << " is not valid";
		return -EINVAL;
	}

	/* Make sure the Request has a valid control list. */
	if (request->controls().infoMap() != &controls()) {
		LOG(Camera, Error) << "Overwriting Request::controls() is not allowed";
		return -EINVAL;
	}

	/*
	 * The camera state may change until the end of the function. No locking
	 * is however needed as PipelineHandler::queueRequest() will handle
	 * this.
	 */

	if (request->buffers().empty()) {
		LOG(Camera, Error) << "Request contains no buffers";
		return -EINVAL;
	}

	for (const auto &[stream, buffer] : request->buffers()) {
		if (d->activeStreams_.find(stream) == d->activeStreams_.end()) {
			LOG(Camera, Error) << "Invalid request";
			return -EINVAL;
		}
	}

	/* Pre-process AeEnable. */
	patchControlList(request->controls());

	d->pipe_->invokeMethod(&PipelineHandler::queueRequest,
			       ConnectionTypeQueued, request);

	return 0;
}

/**
 * \brief Start capture from camera

소스 발췌 `src/libcamera/camera.cpp:1431`
\brief Stop capture from camera
 *
 * This function stops capturing and processing requests immediately. All
 * pending requests are cancelled and complete synchronously in an error state.
 *
 * \context This function may be called in any camera state as defined in \ref
 * camera_operation, and shall be synchronized by the caller with other
 * functions that affect the camera state. If called when the camera isn't
 * running, it is a no-op.
 *
 * \return 0 on success or a negative error code otherwise
 * \retval -ENODEV The camera has been disconnected from the system
 * \retval -EACCES The camera is not running so can't be stopped
 */
int Camera::stop()
{
	Private *const d = _d();

	/*
	 * \todo Make calling stop() when not in 'Running' part of the state
	 * machine rather than take this shortcut
	 */
	if (!d->isRunning())
		return 0;

	int ret = d->isAccessAllowed(Private::CameraRunning);
	if (ret < 0)
		return ret;

	LOG(Camera, Debug) << "Stopping capture";

	d->setState(Private::CameraStopping);

	d->pipe_->invokeMethod(&PipelineHandler::stop, ConnectionTypeBlocking,
			       this);

	ASSERT(!d->pipe_->hasPendingRequests(this));

	d->setState(Private::CameraConfigured);

	return 0;
}

/**
 * \brief Handle request completion and notify application

기존 본문:
(없음)

위 사실을 근거로 짧은 두 문단만 씁니다. 각 기술적 설명에 사실 목록의 `파일:줄` 인용을 붙입니다. 예를 들어 메서드 선언만 주어졌다면 그 메서드의 위치를 확인하도록 안내하고 내부 동작이나 호출 순서는 추측하지 않습니다. 사실이 부족하면 확인할 항목을 명시합니다.

인용 형식의 예시: `ExampleOwner`의 `create()` 정의를 먼저 확인합니다 `dir/ExampleOwner.cpp:40`.
이 예시의 클래스와 위치는 출력에 사용하지 않습니다. 실제 사실 목록의 클래스와 위치로 바꿉니다. 인용 위치는 반드시 백틱으로 감싸고 대괄호를 사용하지 않습니다. 모든 기술 설명 문장에 인용을 붙입니다. 지시문이나 이전 출력의 문제 목록을 되풀이하지 말고 본문만 출력합니다.

본문:

