# #253 실행 원자료

이 디렉터리는 [#253 평가 기록](../../../../docs/libcamera/records/issue253/README.md)의 독립 CLI 요청·응답·영수증과 당시 보조 스크립트를 보존한다. 제품 생성기 기능이나 재사용 가능한 평가 실행기를 제공하지 않는다.

runs/cost-review, runs/grading, runs/grading-d1-consistency는 실제 독립 Codex CLI / Terra / high 실행 원자료다. 사람 평가나 사람 승인으로 계산하지 않는다. .gitattributes에서 원본 바이트를 보존한다.

runs/historical-scripts/*.py.txt는 작업 중 작성한 보조 스크립트의 참고 사본이다. 재실행 시 덮어쓰기·이전 결과 혼합·시간 제한 예외 기록·실제 checkout 검증·본문 분리 문제가 감사에서 확인되어 실행 가능한 예제로 제공하지 않는다. 파일 확장자를 바꿔 그대로 재실행하지 않는다. 이 제한과 원자료 감사는 [절차 감사](../../../../docs/libcamera/records/issue253/procedure-audit.md)에 있다. 현재 기록은 당시 실제 명령·입력 SHA·CLI 영수증·단계 장부로 추적하며, 이 사본이 안전한 재실행 도구라는 의미는 아니다.

새 비교는 기존 lock·결과를 보존한 별도 저장 위치에서 실제 소스 SHA·문서 SHA·manifest를 확인한다. 과업은 한 번에 하나씩 공개하고 시작 화면·첫 근거·실제 제출 경계를 고정해야 한다. 기존 실패·사람 CSV·자동 원자료를 덮어쓰거나 저장 응답을 새 시행으로 바꾸지 않는다. 실제 사람에게는 [고정 과업](../../../../docs/libcamera/records/issue253/protocol.md)과 자료만 전달하며 정답표를 미리 보여 주지 않는다.
