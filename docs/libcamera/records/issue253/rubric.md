# #253 진행자 전용 정답 근거

참여자와 자동 평가 역할에는 이 문서와 기존 #163 rubric을 전달하지 않는다. 아래 경로는 고정 source293의 경로다. 문구 일치가 아니라 조건·주체·시점과 실제 근거를 판정한다. 자동 채점은 사람 승인과 다르다.

| ID | 필수 내용 | 정답 근거 |
| --- | --- | --- |
| T1 | CameraManager를 시작점으로 찾고 요청 제출·완료를 읽을 경로와 이유를 제시한다. | Documentation/index.rst, guides/application-developer.rst, src/libcamera/camera_manager.cpp의 CameraManager 소개, camera.cpp의 queueRequest 문서 |
| T2 | 공통 API/제어와 장치별 PipelineHandler의 하드웨어 구성을 구분하며 모든 장치 지원·성능을 보장하지 않는다. | Documentation/libcamera_architecture.rst, platform_support.rst, guides/pipeline-handler.rst |
| T3 | 통계 수집·디베이어 시간을 포함하고 캡처·출력 시간을 제외한다. 숫자나 실기기 전체 지연을 만들지 않는다. | Documentation/software-isp-benchmarking.rst |
| T4 | createRequest의 반환 unique_ptr은 호출자가 소유·삭제한다. 완료 후 Request::reuse로 상태를 초기화한 뒤 다시 제출한다. 버퍼 재부착과 ReuseBuffers의 조건을 혼동하지 않는다. | src/libcamera/camera.cpp의 createRequest, src/libcamera/request.cpp의 Request::reuse |
| T5 | completeBuffer의 마지막 버퍼 반환값만으로 요청을 자동 완료하지 않는다. PipelineHandler가 completeRequest를 명시 호출하며 CameraManager 스레드 계약을 지킨다. | src/libcamera/pipeline_handler.cpp의 completeBuffer/completeRequest 문서·구현 |
| T6 | Camera::queueRequest가 PipelineHandler::queueRequest를 ConnectionTypeQueued로 예약함을 찾는다. 정적 호출/후보 목록을 실제 시간 순서·모든 경로·장치 실행·스레드 증명으로 확대하지 않는다. | src/libcamera/camera.cpp의 queueRequest 구현, pipeline_handler.cpp의 queueRequest; SDD scenarios/queue_request의 정적 추적 한계 |
| D1 | queueRequest 반환 0은 완료가 아니다. waitingRequests_와 prepare/prepared_ 조건, maxQueuedRequestsDevice_ 및 queuedRequests_ 한도, doQueueRequests/doQueueRequest, cancelled_와 queueRequestDevice 반환 분기, completeBuffer와 completeRequest/순서 보존·Camera 완료 통지를 확인한다. 요청/버퍼 상태·fence/타임아웃·큐 크기·함수 반환과 콜백을 관측할 계획을 제시하고 관측을 위한 상태 변경 재호출이나 존재하지 않는 로그/실측을 만들지 않는다. | src/libcamera/camera.cpp의 queueRequest; pipeline_handler.cpp의 queueRequest/doQueueRequests/doQueueRequest/completeRequest; request.cpp의 prepare/timeout/completeBuffer |
| D2 | pipeline_handler.cpp의 stop과 stopDevice 계약, camera.cpp의 Camera::stop 호출을 찾는다. waitingRequests_를 먼저 지역 큐로 swap하고 stopDevice로 진행 요청을 끝낸 뒤 대기 요청을 cancelled_로 표시해 doQueueRequest로 순서 번호·queuedRequests_를 거쳐 완료한다. 큐 비움과 requestSequence_ 초기화, CameraManager 문맥·취소/완료와 버퍼 수명을 함께 확인한다. 장치/파이프라인별 stopDevice와 요청 순서/중복 완료/정지 반환 전후 콜백 검증을 실행 계획으로 제시한다. | src/libcamera/pipeline_handler.cpp:358~430 및 doQueueRequest/completeRequest, src/libcamera/camera.cpp의 Camera::stop |

각 답은 correctness=true/false, independent=true/false와 누락 조건을 남긴다. D1의 준비 조건은 실제 소스의 hasPendingBuffers와 prepared_의 역할을 구분해야 한다. 부분 답을 완전 정답으로 올리지 않되 관측 계획에 해당 조건을 적절히 찾았다면 표현 차이를 허용한다. 정답표 오류가 발견되면 원본을 보존하고 변경 이유와 영향 시행을 별도로 남기며 결과에 맞춰 문턱을 낮추지 않는다.
