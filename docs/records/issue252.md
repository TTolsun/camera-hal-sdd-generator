# 요청·버퍼 경로의 조건과 변경 경계를 검증하기

이 기록은 [이슈 #252](https://github.com/TTolsun/camera-hal-sdd-generator/issues/252)의 생성기 변경과 공개 libcamera 소스·빌드 증거를 소유합니다. 최종 원고·한영 검토·사이트와 배포 증거는 [공개 publication/issue252](https://github.com/TTolsun/libcamera-sdd/tree/main/publication/issue252)에 연결합니다. 생성기 PR 병합만으로 이슈 전체를 완료하지 않습니다.

## 고정 질문과 선택 범위

생성 전 질문은 제출 0 뒤의 미진입·준비 대기, 부분 제어 적용과 QBUF 실패, 요청 완료와 프레임 유효성, 소유권·수명, 정지 실패, 콜백 문맥·재진입, 변경 후 검증의 Q1–Q7입니다. 원래 기본 설명은 유지하며 답의 조건·관찰값·다음 분기·변경 검증 조건을 보완합니다.

| 질문 | 기존 설명만으로 판단하기 어려웠던 조건 |
| --- | --- |
| Q1 | queued 메서드 진입 전과 waitingRequests_ 대기를 구분하고 fence·선두·한도를 추적합니다. |
| Q2 | 개별 제어 변환의 무시된 반환, setControls의 부분 적용과 QBUF 실패 뒤 취소를 구분합니다. |
| Q3 | FrameError와 RequestComplete를 구분하고 데이터·metadata의 유효성 계약을 확인합니다. |
| Q4 | bufferCompleted 발생 뒤의 pending 정리와 별도 지연 수신자의 마지막 포인터 사용을 구분합니다. |
| Q5 | STREAMOFF/releaseBuffers 오류, 잔존 알림·cache, 연결 해제 뒤 stop의 조기 반환을 확인합니다. |
| Q6 | Direct·Queued·Blocking의 스레드 분기, 메인 스레드의 이벤트 루프 기본 조건과 수신 종료 경계를 확인합니다. |
| Q7 | 정상 erase와 bulk 취소 clear, 실패별 ret·index·큐·상태·횟수를 변경 검증 계획으로 연결합니다. |

분석 커밋은 `293d751a814e0d4c34e85ad457ccd9d5eefd1a61`입니다. 확인한 공식 upstream과 공개 mirror는 `be7e83e91348250c015aad6d6f59f1468555bae8`이며, 사이의 세 변경 파일과 선택한 25개 전체 소스 파일은 겹치지 않습니다. 최초 20개 창 이후 Thread·Message·기본 dispatcher까지 확장한 시점과 원래 창의 검토 결과를 따로 보존합니다. 과거 검토를 25개 창의 새 검토로 바꾸지 않습니다.

범위는 공통 Camera·Request·PipelineHandler와 UVC의 제출·장치 알림·취소·정지, 기본 Thread/Signal 전달입니다. 다른 파이프라인·IPA·커널·물리 DMA·장치 성능·사용자 dispatcher·동시 연결 파괴·사내 HAL은 검증하지 않습니다. 실제 비작성자 평가와 #215 전체 보완도 포함하지 않습니다.

## 빌드·추출과 제한된 실행

새 UVC 전용 Meson/Ninja 전체 빌드에서 생성 입력을 보존했습니다. 그 빌드에 결합한 libclang 추출은 135개 TU·파싱 오류 0개이며, 원래 facts의 해시와 meta 통계를 별도 현재 검사 기록으로 다시 확인했습니다. controls.cpp의 GCC 확장에는 분석용 `-Wno-error=c99-designator`만 명시적으로 적용했으며 다른 파싱 오류는 허용하지 않습니다. 이 facts를 전체 사이트의 역사적 구조 facts로 바꾸어 표시하지 않습니다.

별도 새 빌드에서 libcamera-base 출력 해시를 기록하고, 프로브의 컴파일 전 해시·실제 로더 경로·실행 뒤 불변을 확인했습니다. Auto의 타스레드 Queued 선택과 명시적 Queued에서 두 번째 동기 슬롯이 emit을 진행 중으로 유지한 동안 수신 본문 표식을 관측했습니다. 명시적 Direct는 타스레드 affinity에도 발신 문맥에서 실행됐습니다. 이 반례는 emit 반환 뒤라는 일반 주석을 구현의 선후 보장으로 사용할 수 없음을 보여 줍니다. 수신 함수의 정확한 반환 명령·실제 카메라 촬영·포인터 오류 주입을 관측한 결과가 아닙니다.

## 공통 변경과 검토

그림 인용 검사는 C++ 식별자·화살표·비교 연산·숫자와 guard의 확장 경계를 구분합니다. 서로 다른 발췌를 이어 붙여 guard를 만들지 못하며, 수신자 변경·수치 접미사·논리 연산·호출·중괄호·unary/cast 확장을 거부합니다. 정확히 일치하는 과거 입력은 현재 검사를 통과해야만 원래 fingerprint·모델을 보존한 재검증으로 이월합니다. `new_inference: false` 이월을 새 CLI 생성으로 집계하지 않습니다.

한 함수의 서로 다른 인용을 잇는 정상 간선도 있으므로 모든 간선의 두 심볼을 한 발췌 안에 강제했던 실험적 제한은 철회했습니다. enum 상태의 중복 검사에 새 예외를 추가하는 실험도 철회했고 기존 한정된 이름 처리를 사용합니다. 실패·철회 원본은 archive에 남깁니다. 공통 검사는 의미·순서의 독립 검토를 대신하지 않습니다.

생성·번역과 독립 검토는 실제 Codex CLI의 `gpt-6.1-terra`, `-c model_reasoning_effort="high"`를 사용합니다. 문장 정확성과 전체 소스 창의 근거 충분성은 별도 호출입니다. 검토 도구는 Q1–Q7의 필수 진단 필드·소스 참조와 모든 H2/H3의 그림 또는 생략 사유가 빠지면 통과를 기록하지 않습니다. 자동 판정은 사람 승인이 아닙니다.

코드 검토 25의 통과 뒤 바뀐 계획 upsert와 발췌 보완은 원래 검토 파일의 해시에 결합한 별도 delta 검토 27에서 확인했습니다. 최초 CI에서 발견한 주제 개수와 역할별 소유권 연결도 수정했습니다. 최종 로컬 그림·설정·역할 연결·검토 펜스 회귀 200개가 통과했습니다. 전체 CI와 병합 상태는 PR에서 별도로 확인합니다.

[코드·소스 원본 archive](../libcamera/records/issue252/code-and-source-evidence.zip), [항목별 해시](../libcamera/records/issue252/code-and-source-index.json), [패키지 범위](../libcamera/records/issue252/code-and-source-package.json)에서 실제 요청·응답·native stdout·영수증·실패 시도·빌드·추출·프로브를 확인할 수 있습니다. 최종 원고의 질문별 전후 답변 가능성과 한영·화면·배포 결과는 공개 기록에서 구분합니다. 분량·그림 수·검토 반복 수를 개선 성과로 세지 않습니다.
