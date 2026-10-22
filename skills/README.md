# 에이전트 스킬

사내 LLM 에이전트가 생성기를 운영할 때 따르는 절차를 [Agent Skills](https://agentskills.io) 형식(`SKILL.md`)으로 둡니다.

| 스킬 | 용도 |
|---|---|
| [camera-hal-sdd](camera-hal-sdd/SKILL.md) | NDK-build·legacy HAL3 HAL에서 SDD를 추출·생성·검증하고 증분 갱신합니다. |

## 설치

스킬 디렉터리(`camera-hal-sdd/`)를 에이전트의 스킬 경로에 복사합니다.

- Claude Code: 사내 설정 저장소의 `.claude/skills/camera-hal-sdd/`
- Hermes 등 다른 에이전트: 사내에서 쓰는 버전의 스킬 경로. 이 저장소는 특정 버전의 경로를 검증하지 않았습니다.

스킬은 터미널에서 `uv run sdd ...`를 실행할 수 있는 에이전트를 전제로 합니다. `sdd automate`가 부르는 Hermes 검토 단계는 파일 수정·터미널 도구를 막은 별도 실행이므로, 이 스킬과 같은 도구 권한을 주지 않습니다([예약 게시 절차](../docs/scheduled-publication.md)).

## 참고한 스킬

공개 스킬 세 개를 읽고 필요한 원칙만 옮겼습니다. 설치하거나 내용을 복사하지 않았습니다.

| 스킬 | 가져온 것 | 가져오지 않은 것 |
|---|---|---|
| [anthropics/skills · skill-creator](https://skills.sh/anthropics/skills/skill-creator) | 사용 상황을 description에 넓게 적기, 금지 규칙에 이유 붙이기, 입력·출력 예시, 본문 500줄 이하 | 평가 실행·description 최적화 절차 (사내 모델에서 따로 수행) |
| [addyosmani/agent-skills · documentation-and-adrs](https://skills.sh/addyosmani/agent-skills/documentation-and-adrs) | 코드가 아니라 결정과 이유를 기록하기, 기존 작성 방식을 먼저 따르기 | ADR 템플릿 (SDD 설정 형식이 이미 있음) |
| [riekelt/technical-writer · documenting-legacy-codebases](https://skills.sh/riekelt/technical-writer/documenting-legacy-codebases) | 근거 신뢰 순서, 이상한 동작은 실제대로 쓰고 결함 판정은 담당자에게 넘기기 | 산문에서 코드 위치를 빼는 규칙 (이 생성기는 `파일:줄` 인용으로 근거를 검사함), 다중 에이전트 진행 방식 |

## 수정할 때

- 스킬의 명령, 확인 문구, 종료 코드는 생성기 코드와 같아야 합니다. CLI 출력 문구를 바꾸면 스킬과 [NDK·HAL3 가이드](../docs/inhouse-ndk-hal3.md)도 함께 고칩니다.
- 사내 클래스명이나 경로는 넣지 않습니다. 이 저장소는 공개 저장소이며, 사내 값은 사내 설정에 둡니다.
