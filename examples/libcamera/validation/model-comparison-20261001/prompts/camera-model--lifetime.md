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
절: 소유권과 재사용
독자: libcamera의 공개 API를 분석하는 개발자

이 절이 답해야 하는 질문:
- 요청 소유권과 완료 뒤 재사용, ReuseBuffers, fence 이전 조건을 설명하세요. 근거에 없는 버퍼 소유권은 추정하지 마세요.

사실 (이 목록 밖의 내용은 쓰지 않습니다):
소스 발췌 `src/libcamera/camera.cpp:1243`
\brief Create a request object for the camera
 * \param[in] cookie Opaque cookie for application use
 *
 * This function creates an empty request for the application to fill with
 * buffers and parameters, and queue for capture.
 *
 * The \a cookie is stored in the request and is accessible through the
 * Request::cookie() function at any time. It is typically used by applications
 * to map the request to an external resource in the request completion
 * handler, and is completely opaque to libcamera.
 *
 * The ownership of the returned request is passed to the caller, which is
 * responsible for deleting it. The request may be deleted in the completion
 * handler, or reused after resetting its state with Request::reuse().
 *
 * \context This function is \threadsafe. It may only be called when the camera
 * is in the Configured or Running state as defined in \ref camera_operation.
 *
 * \return A pointer to the newly created request, or nullptr on error
 */
std::unique_ptr<Request> Camera::createRequest(uint64_t cookie)

소스 발췌 `src/libcamera/request.cpp:376`
\brief Reset the request for reuse
 * \param[in] flags Indicate whether or not to reuse the buffers
 *
 * Reset the status and controls associated with the request, to allow it to
 * be reused and requeued without destruction. This function shall be called
 * prior to queueing the request to the camera, in lieu of constructing a new
 * request. The application can reuse the buffers that were previously added
 * to the request via addBuffer() by setting \a flags to ReuseBuffers.
 */
void Request::reuse(ReuseFlag flags)
{
	LIBCAMERA_TRACEPOINT(request_reuse, this);

	_d()->reset();

	if (flags & ReuseBuffers) {
		for (const auto &[stream, buffer] : bufferMap_) {
			buffer->_d()->setRequest(this);
			_d()->pending_.insert(buffer);
		}
	} else {
		bufferMap_.clear();
	}

	status_ = RequestPending;

	controls_.clear();
	_d()->metadata_.clear();
}

/**
 * \fn Request::controls()

소스 발췌 `src/libcamera/request.cpp:442`
\brief Add a FrameBuffer with its associated Stream to the Request
 * \param[in] stream The stream the buffer belongs to
 * \param[in] buffer The FrameBuffer to add to the request
 * \param[in] fence The optional fence
 *
 * A reference to the buffer is stored in the request. The caller is responsible
 * for ensuring that the buffer will remain valid until the request complete
 * callback is called.
 *
 * A request can only contain one buffer per stream. If a buffer has already
 * been added to the request for the same stream, this function returns -EEXIST.
 *
 * A Fence can be optionally associated with the \a buffer.
 *
 * When a valid Fence is provided to this function, \a fence is moved to \a
 * buffer and this Request will only be queued to the device once the
 * fences of all its buffers have been correctly signalled. Ownership of the
 * fence will only be taken in case of success, otherwise the fence will
 * be left unmodified.
 *
 * If the \a fence associated with \a buffer isn't signalled, the request will
 * fail after a timeout. The buffer will still contain the fence, which
 * applications must retrieve with FrameBuffer::releaseFence() before the buffer
 * can be reused in another request. Attempting to add a buffer that still
 * contains a fence to a request will result in this function returning -EEXIST.
 *
 * \sa FrameBuffer::releaseFence()
 *
 * \return 0 on success or a negative error code otherwise
 * \retval -EEXIST The request already contains a buffer for the stream
 *  or the buffer still references a fence
 * \retval -EINVAL The buffer does not reference a valid Stream
 */
int Request::addBuffer(const Stream *stream, FrameBuffer *buffer,

기존 본문:
(없음)

위 사실을 근거로 짧은 두 문단만 씁니다. 각 기술적 설명에 사실 목록의 `파일:줄` 인용을 붙입니다. 예를 들어 메서드 선언만 주어졌다면 그 메서드의 위치를 확인하도록 안내하고 내부 동작이나 호출 순서는 추측하지 않습니다. 사실이 부족하면 확인할 항목을 명시합니다.

인용 형식의 예시: `ExampleOwner`의 `create()` 정의를 먼저 확인합니다 `dir/ExampleOwner.cpp:40`.
이 예시의 클래스와 위치는 출력에 사용하지 않습니다. 실제 사실 목록의 클래스와 위치로 바꿉니다. 인용 위치는 반드시 백틱으로 감싸고 대괄호를 사용하지 않습니다. 모든 기술 설명 문장에 인용을 붙입니다. 지시문이나 이전 출력의 문제 목록을 되풀이하지 말고 본문만 출력합니다.

본문:

