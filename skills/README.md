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

## 수정할 때

- 스킬의 명령, 확인 문구, 종료 코드는 생성기 코드와 같아야 합니다. CLI 출력 문구를 바꾸면 스킬과 [NDK·HAL3 가이드](../docs/inhouse-ndk-hal3.md)도 함께 고칩니다.
- 사내 클래스명이나 경로는 넣지 않습니다. 이 저장소는 공개 저장소이며, 사내 값은 사내 설정에 둡니다.
