# 문서 지도

사내에 전달하려면 [반입 패키지 시작 안내](inhouse/package.md)를 여세요. 시작 프롬프트, 실행 순서, 품질 합격 기준과 복구 절차를 한 곳에 모았습니다.

**아래 표에서 내 역할의 줄만 읽으세요.** 다른 줄의 문서는 읽지 않아도 됩니다.

| 나는 | 읽는 순서 |
|---|---|
| **사내 운영자** (HAL에 적용하고 갱신한다) | [사내 설정 템플릿](../examples/inhouse-template/)을 복사한 뒤 [1. 준비물](inhouse/01-prepare.md) → [2. 첫 실행](inhouse/02-first-run.md) → [3. 갱신 시스템](inhouse/03-update-system.md) → [4. 사람 검토](inhouse/04-review.md). 막히면 [문제 해결](inhouse/troubleshooting.md) |
| **사내 에이전트를 쓰는 사람** | [에이전트에게 맡기기](inhouse/agent.md) → [소스에서 계약 작성하기](inhouse/contract-authoring.md) → [SDD 생성 스킬](../skills/camera-hal-sdd/SKILL.md) |
| **설정 키·명령을 찾는 사람** | [sdd.yaml](reference/config.md), [sections.yaml·scenarios.yaml](reference/sections.md), [glossary.yaml](reference/glossary.md), [명령·종료 코드·상태 파일](reference/cli.md) |
| **동작 원리가 궁금한 사람** | [범위 검사](concepts/coverage.md), [설계 근거](concepts/design-evidence.md), [독자별 품질](concepts/reader-quality.md), [문서 수명주기](concepts/document-lifecycle.md), [사이트](concepts/site.md), [sdd automate](concepts/automation.md) |
| **생성기를 고치는 사람** | [책임 분리](concepts/code-structure.md), [파이프라인 설계](concepts/pipeline-design.md), [디자인 계약](../DESIGN.md) |
| **공개 libcamera 검증을 보는 사람** | [libcamera 문서 모음](libcamera/README.md) |

## 문서 구조 원칙

문서도 코드처럼 SOLID 원칙으로 나눕니다. 새 내용을 쓸 때 이 원칙으로 자리를 정합니다.

| 원칙 | 문서에서의 뜻 | 이 저장소의 자리 |
|---|---|---|
| 단일 책임 | 문서 한 편은 한 가지 질문에만 답합니다. | `inhouse/` 절차, `reference/` 사실, `concepts/` 이유, `libcamera/` 검증 기록 |
| 개방·폐쇄 | 새 HAL·프로젝트는 설정과 예제 폴더로 추가하고 공통 문서를 고치지 않습니다. | `examples/<프로젝트>/`, 사내 설정 디렉터리 |
| 같은 계약 | 절차 문서는 모두 같은 모양입니다: 첫 줄은 할 일, 번호 단계와 확인 값, 마지막은 다음 단계. | `inhouse/*.md` |
| 독자별 입구 | 독자는 자기 줄의 문서만 읽으면 됩니다. | 위 표 |
| 참조는 한 곳 | 설정 키·명령·종료 코드는 `reference/`에만 쓰고, 다른 문서는 연결만 합니다. | `reference/*.md` |

새 내용이 기존 문서와 겹치면 한 곳에만 쓰고 다른 곳에서는 링크합니다. 문서 사이 링크는 `tests/test_docs_links.py`가 검사합니다.
