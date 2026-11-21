# 증분 갱신 실행 전 기대 결과

2026년 11월 21일에 원고 생성과 증분 갱신을 실행하기 전에 작성했습니다. [#347](https://github.com/TTolsun/camera-hal-sdd-generator/issues/347)의 질문 두 개를 커밋의 부모와 커밋 자체에 각각 적용합니다.

1. Vendor 질문은 “우리 장치에서 무엇을 검증하는가?”입니다. 정상 촬영과 정지를 각각 실행해 요청 완료 알림, 요청 상태, 앱 버퍼의 프레임 상태를 관찰합니다. 특히 장치에 제출된 요청과 준비 대기열에만 있던 요청을 따로 확인합니다.
2. Developer 질문은 “취소 상태를 어느 코드에서 확인하는가?”입니다. 앱에서는 `Camera::requestCompleted` 콜백에서 `Request::status()`를 확인합니다. 공통 구현에서는 `Request::Private::complete()`의 `cancelled_` 분기와 `PipelineHandler::completeRequest()`의 반환 조건을 따라갑니다.

공개 비교 기준은 Pages 커밋 `19fc551464ac4c2e16e3d735bc0664f385803f21`, 빌드 `d3fbba05ba16342189d8a184f789e68cbe4688d9cb75f183859f6571aaf2c26b`, upstream `adfa719f8ed67d18fd8a0739fc088a1f8b9e7252`입니다. 기존 공개 문서 중 [연동 가이드의 정지 책임](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#정지와-오류-처리의-책임)과 [요청 수명 문서의 정지 설명](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#정지와-연결-해제를-구분하기)을 기준으로 삼았습니다. 기준을 확인한 시점에 #346과 #347은 열려 있었습니다. 과거 커밋의 원고는 각 부모 커밋의 코드에서 생성합니다.

## 1. 함수 이동으로 답은 유지됩니다

- Base `16a469a1ca3356783940c8362ab7583dfa578e37`, head [`b6f81b756af79bce23240f7bc48032895a3ca2c9`](https://gitlab.freedesktop.org/camera/libcamera/-/commit/b6f81b756af79bce23240f7bc48032895a3ca2c9).
- `Request::Private::hasPendingBuffers()`를 `src/libcamera/request.cpp`에서 `include/libcamera/internal/request.h`로 옮깁니다. 함수는 양쪽에서 `!pending_.empty()`를 반환합니다. Vendor의 정지·완료 확인 항목과 Developer의 상태 확인 위치는 그대로입니다.
- 두 답변의 문장, 순서, 그림의 상태 분기, 독자 링크를 유지할 것으로 예상합니다. `Request::Private::complete()`를 가리키는 인용 줄을 새 위치로 맞추고, 이동한 함수의 정의를 직접 인용하는 경우 헤더로 연결합니다.

## 2. 장치별 결함 수정으로 장치 확인 항목이 달라집니다

- Base `0d48cb6bb0883f267f9e470057fa7311c52b766c`, head [`0b0f32e7366b2de94983d8cb02d4c32a10b0f561`](https://gitlab.freedesktop.org/camera/libcamera/-/commit/0b0f32e7366b2de94983d8cb02d4c32a10b0f561).
- RKISP1에서 ISP 내부 버퍼가 취소되면 기존에도 앱의 main-path 버퍼를 완료하지만, 그 버퍼에 취소 상태를 명시하지 않습니다. dewarper 큐 등록 실패는 기록만 남깁니다. 수정 뒤에는 두 조건 모두 `cancelDewarpRequest()`로 들어가 앱 버퍼를 취소 및 완료하고 요청 완료 조건을 다시 검사합니다.
- 두 공통 답변과 그림을 유지할 것으로 예상합니다. 해당 장치의 상세 확인 항목을 다루는 절에서는 ISP 버퍼 취소와 dewarper 큐 등록 실패를 모두 이미 있는 장치 검증 항목에 연결하고, 앱 main-path 버퍼의 `FrameCancelled`를 확인하도록 갱신합니다. Developer의 공통 상태 확인 위치는 그대로이고 장치 근거만 `rkisp1.cpp`의 새 헬퍼와 두 호출부로 이동합니다.

## 3. 공통 완료 경로 수정으로 두 답변의 조건이 달라집니다

- Base `517b863bae2db2dd0c56366119318d6b2fb9ad52`, head [`731a340c8064843075cb9a41e22908eadadbf1bd`](https://gitlab.freedesktop.org/camera/libcamera/-/commit/731a340c8064843075cb9a41e22908eadadbf1bd).
- 정지 시 준비 대기열에만 있던 요청은 기존 `cancelRequest()` 호출에서 상태가 취소로 바뀌더라도 `queuedRequests_`에 없으므로 앱의 요청 완료 신호를 받지 못합니다. 수정 뒤에는 장치 정지를 마치고 각 대기 요청을 취소한 후 `doQueueRequest()`에서 순번을 붙여 `queuedRequests_`에 넣습니다. 취소 분기가 `completeRequest()`로 들어가면서 앱은 `requestCompleted`에서 `RequestCancelled`를 확인할 수 있습니다.
- Vendor는 준비 대기열에 남은 요청의 완료 통지가 정지 과정에서 도착하는지 확인할 수 있게 됩니다. Developer는 상태를 정하는 함수와 함께 대기 요청이 콜백까지 이어지는 조건을 확인할 수 있게 됩니다. 기존 정지 설명과 분기 그림에 이 조건을 반영하고 기존 독자 링크가 그 설명으로 이어지는지 확인합니다. 그 밖의 정상 완료 설명과 장치별 경로를 유지할 것으로 예상합니다.

각 사례에서 본문, 그림, 인용 위치, 관련 없는 절을 별도로 대조합니다. 같은 base/head, 설정과 사실 추출 입력으로 증분 생성을 다시 실행한 뒤 본문과 절별 문단 수를 비교합니다. 새 문단은 기존 두 질문과 연결할 수 없는 필수 과업이 근거로 확인될 때만 추가합니다. 분류에 필요한 근거가 없으면 검토 대기로 기록합니다.
