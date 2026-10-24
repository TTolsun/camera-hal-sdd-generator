# Developer 독자 기준 수정과 공개 검증

**For Developer의 대상은 신입·타팀 개발자입니다.** 아키텍처 개발자로 좁혔던 가이드·템플릿·스킬과 공개 libcamera 안내를 2026-10-24에 수정했습니다.

## 바뀐 기준

For Vendor는 연동·구현 계약을 찾는 경로입니다. For Developer는 첫 파일과 진입점에서 요청·결과를 따라가고, 증상별 확인 코드와 수정 후 검증 조건을 찾는 경로입니다. 책임·수명·동시성 설명은 유지합니다. 자세한 합격 기준은 [독자별 품질](../../concepts/reader-quality.md)을 따릅니다.

`developer` 프로필에는 `entry`를 추가했습니다. 기존 아키텍처 질문 집합의 이름만 바꾸면 누락으로 실패하며, 기존 `architecture` 프로필 자체는 계속 지원합니다. mini HAL의 `architecture-contract.md` 출력 경로는 기존 링크를 위해 유지하지만 제목과 내용, 프로필은 Developer 안내입니다.

## 실제 대조한 읽기 과제

| 과제 | mini HAL에서 찾은 답 | 공개 libcamera에서 찾은 답 |
|---|---|---|
| 첫 코드를 찾습니다. | CameraModule.cpp의 camera_device_open → CameraDevice의 구성·요청 진입점 | camera_manager.cpp의 CameraManager → start → cameras/get → PipelineHandler::match |
| 한 요청을 따라갑니다. | processCaptureRequest → submit → 작업 스레드의 onFrame → sendResult | createRequest → queueRequest → 버퍼 완료와 명시적 요청 완료 → requestCompleted |
| 완료 누락을 조사합니다. | enqueue 반환과 runPipes 실패 분기, sendResult 호출 여부 | 진단 문서의 반환 코드·준비 대기·장치 전달·버퍼/요청 완료 확인 순서 |
| 종료 경로 수정의 조건을 찾습니다. | drain의 프레임 삭제와 stop의 join, 원시 포인터 수명 제약 | 획득·구성·시작·정지·최종 해제 구분과 상태 변경의 호출자 동기화 |

현재 작성 에이전트가 문서와 소스를 대조했습니다. 새 독립 에이전트 시험이나 실제 신입·타팀 독자의 이해도 시험으로 기록하지 않습니다. [이전 독립 시험](mini-hal-forward-test.md)은 당시의 아키텍처 질문으로 수행한 기록입니다.

## 자동 검사와 공개 생성

- 전체 회귀 테스트: 715개 통과, 1개 건너뜀. 최종 계약·용어집·번역 수정 뒤 관련 22개 테스트도 통과했습니다. 필수 답변 삭제 시 원고와 사이트를 보존하는 검사가 포함됩니다.
- 공개 upstream은 `2c4b67c0792f88f69bcdf9cbf73e81b3d8cf4b6f`로 동일했습니다. 기존 전체 빌드 facts를 재사용하고 수정된 발췌를 다시 수집했습니다. 이번 작업에서 새 전체 컴파일·추출을 수행했다고 주장하지 않습니다.
- 개요는 소스와 대조한 `statements`로 재생성했습니다. 시도한 로컬 LLM 초안은 오래된 주석의 `list()`를 실제 API로 안내하고 준비·시작 조건을 흐리게 써서 채택하지 않았습니다. 실제 `cameras()`·`get()` 정의를 근거로 포함했습니다. 결과의 생성 방식은 `source-bound-contract`이며 LLM 결과로 표시하지 않습니다.
- mini HAL 사이트 4페이지, 공개 한영 사이트 38페이지에서 깨진 내부 링크 0과 manifest 일치를 확인했습니다. 개요를 재생성하면 생성 시각만 바뀌고 본문과 근거는 같았습니다. 생성 시각 변경도 영어 원문 지문 검사를 차단하므로 카탈로그를 다시 대조했습니다. 같은 원고와 카탈로그로 반복 빌드한 산출물 88개와 manifest가 모두 동일했습니다.
- 브라우저에서 첫 진입점 링크, 근거의 Enter·Space 접기, 영어 모바일 메뉴를 조작했습니다. 390px 뷰포트에서 문서 너비와 스크롤 너비는 모두 375px였습니다. 이번 작업은 CSS·JS를 바꾸지 않았으며 모든 기존 조작을 새로 시험했다고 주장하지 않습니다.

재현 명령은 [반입 시작 안내](../package.md)의 실행 순서와 [사이트 검증](../../concepts/site.md)을 따릅니다. 사내 HAL, 실제 장치, 사람 승인과 ADHD 사용자의 이해도는 검증하지 않았습니다.
