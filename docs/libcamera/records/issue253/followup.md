# 실패 과업과 다음 검증 범위

사람 평가와 전체 갱신 비용은 미완료다. 아래 목록은 자동 답변의 실패와 독립 검토의 공백이며, 제품 문서 결함이 확정됐다는 목록이 아니다. 기준을 바꾸거나 좋은 시행으로 원래 실패를 대체하지 않는다.

| 범위 | 관측 | 다음 확인과 보완 조건 |
| --- | --- | --- |
| E01/T1/A | CameraManager를 코드 시작점으로 찾지 않았다. | 공식 자료의 첫 진입과 B의 명시 코드 안내를 대조한다. 사람 첫 노출 결과를 추가하며 공식 자료 자체를 이 생성기에서 수정했다고 주장하지 않는다. |
| E02/T2/A·B | 장치별 하드웨어 구성 책임을 답에 명시하지 않았다. | source293 Documentation/libcamera_architecture.rst와 pipeline-handler 가이드, B vendor-overview/vendor-integration의 관련 절을 함께 읽어 실제 미발견인지 설명 공백인지 확인한다. 구성 책임이 이미 있으면 중복 본문 대신 탐색 경로·과업 전달을 검토한다. |
| E01/D1/B, E02/D1/A | 준비 타임아웃 또는 앱 완료 콜백 관측이 답에 빠졌다. | request.cpp의 prepare/timeout과 pipeline_handler.cpp의 prepared_·큐 제한·completeRequest, B request-diagnosis와 request-lifecycle의 같은 질문별 절을 확인한다. E02/E03의 B에서는 해당 조건을 찾았으므로 부재로 단정하지 않는다. |
| D2의 6시행 중 5실패 | 중복 완료·정지 반환 전후 콜백·장치별 stopDevice 검증 일부가 빠졌다. | source293 pipeline_handler.cpp:358~430, doQueueRequest/completeRequest와 실제 Camera::stop 범위를 올바르게 다시 고정한다. B request-lifecycle의 stop-device-observation-plan·observed-stop-callback-timing 및 official-cam-validation의 관련 발췌를 대조한다. 장치별 구현·기존 테스트의 정확한 근거를 추가 검토하며 실행 계획을 실측으로 바꾸지 않는다. |
| 자동 채점 | Camera::stop 창 하나가 비었고 모든 인용 HTML·장치 테스트를 다시 열지는 않았다. | 현재 grades를 잠정으로 보존한다. 재검토가 필요하면 누락 창과 실제 방문 자료를 제공한 새로운 독립 Terra High 실행을 별도 기록하고 판정 변경 이유를 대응시킨다. |
| 시작점·대기 계측 | E01 B 세 시행의 index 시작 기록이 없고, E02 wall time 합은 환경 지연과 같지 않다. | 실제 사람 시험은 진행자가 매 시행 시작 화면·첫 근거·제출 시각을 기록한다. 미기록은 0초나 규정 준수로 채우지 않는다. |
| qcam 비용 | 변경 파일은 watch에 걸리지만 추출 근거가 없다. | 분석 빌드에서 qcam 활성 여부를 실제 compile DB·Meson 설정으로 확인하고 Qt 빌드가 필요한지 결정한다. 부모/머리의 별도 facts, 필요한 원고·번역·검토와 사람 활동 시간을 측정한 뒤에만 전체 갱신 비용을 완료한다. |
| 최신 소스 | 공식/공개 upstream은 be7e83e, 고정 문서는 source293이다. | 최신 AGC 초기 이득·Python CameraConfiguration 변경의 영향은 별도 추출·갱신 시험으로 진행한다. 현재 자동 평가 버전이나 결과를 최신본으로 재명명하지 않는다. |

실제 비교 참가자가 없으므로 공개 libcamera 결과를 사내 생산성으로 확대하지 않는다. #163과 겹치는 실제 시행을 나중에 사용할 때는 session_id와 원본 증거를 연결하며 한 시행을 별도 성과로 두 번 세지 않는다. 실패 보완 후 시험도 노출 횟수를 남기고 첫 노출과 분리한다.
