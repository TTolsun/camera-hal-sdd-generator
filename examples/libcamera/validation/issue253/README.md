# #253 고정 비교와 부분 비용 재현

이 디렉터리의 스크립트는 평가 준비·자동 채점·부분 비용 기록을 재현하기 위한 공개 예제다. 제품 생성기 기능이나 사람 참가자 시험 실행기가 아니다. 결과와 한계는 [평가 기록](../../../../docs/libcamera/records/issue253/README.md)에 있다.

빈 별도 작업본과 Python 개발 의존성, Git, 독립 Codex CLI가 필요하다. build/issue253/source에 source293을 체크아웃하고, build/issue253/public에 공개 SDD 178aa978의 docs를 체크아웃한다. `python prepare.py`는 비교 입력 328개와 소스 해시를 검사하고 과업 패킷·빈 사람 CSV·lock을 만든다. 기존 기록을 덮어쓰므로 보존한 연구 원본 디렉터리에서 다시 실행하지 않는다.

서브에이전트에는 자신의 packet.json만 제공하고 거기에 선언된 자료 범위·순서를 지키게 한다. 각 역할의 results.json 8행을 실제 수행 뒤 저장한다. 결과를 미리 작성하거나 저장 응답을 새 시행으로 복원하지 않는다. 사람이 수행했다면 별도 human-results.csv를 사용하고 자동 결과를 그 파일에 넣지 않는다.

`measure_cost.py`는 사전에 선택한 실제 qcam 변경의 diff·정상 CLI impact를 측정한다. 기존 facts를 재사용하며 새로운 빌드나 Clang 추출을 하지 않는다. qcam 미추출 및 부모 facts 부재 때문에 needs-review가 남는 것을 성공으로 바꾸지 않는다. `review_cost.py`와 `grade.py`는 [별도 검토 프로필](../../../../docs/libcamera/records/issue253/review.yaml)의 독립 Terra High CLI를 실제 호출한다. 실패하면 미완료를 기록하고 다른 CLI·API·수동 답변으로 대신하지 않는다. `summarize.py`는 제출·채점 결과를 집계하며 사람 효과 판정을 만들지 않는다.

스크립트는 프로젝트 루트를 찾고 작업공간 안에 기록한다. 파일의 CLI 명령·입력·응답·영수증과 실패를 함께 보존한다. 최초 실행의 설정·UTF-8 준비 실패와 측정 이후의 수정도 원본 장부와 분리해야 한다. 사내 소스·제품 자료·사람 참가자 정보는 이 공개 경로에 넣지 않는다. 분석·사이트 원본과 impact schema 1은 변경하지 않는다.
