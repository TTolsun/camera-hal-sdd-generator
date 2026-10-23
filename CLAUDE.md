# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Camera HAL 소스에서 검토용 설계 문서(SDD)를 생성하고, 코드 변경에 맞춰 증분 갱신하는 파이프라인입니다. Clang(compile DB)으로 구조와 근거 위치를 추출하고, 소스에 연결한 설계 설명과 facts로 문서를 구성합니다. 선택한 섹션에는 LLM으로 한국어 설명 초안을 작성할 수 있습니다. 최종 적용 대상은 사내 Camera HAL이며, 공개 libcamera는 검증용 테스트 대상입니다. 생성 문서의 디자인 계약은 `DESIGN.md`를 따릅니다.

프로젝트 목적과 작업 기준은 아래 문서를 그대로 따릅니다.

@AGENTS.md

## 변경 작업의 완료 기준

사용자의 상시 지시에 따라 생성기 작업과 공개 libcamera SDD 갱신을 함께 완료합니다. 생성기 리뷰·검증·병합 후 공개 입력으로 문서와 사이트를 갱신하고, `TTolsun/libcamera-sdd`의 PR 병합·Pages 배포·공개 URL 반영까지 확인합니다. 자세한 절차와 산출물 변경이 없는 경우의 처리는 [공개 libcamera SDD 동반 배포](docs/libcamera/workflow.md#공개-libcamera-sdd-동반-배포)를 따릅니다. 사내 소스와 파생물은 공개 저장소에 배포하지 않습니다.

## 사내 문서 자동화 구축 요청을 받았을 때

[사내 에이전트에게 맡기기](docs/inhouse/agent.md)의 지시문과 완료 기준을 따르고, [사내 운영 절차](docs/README.md) 1~4단계 순서로 실제 HAL 한 경로의 추출·설계 문서·변경 반영 검증부터 진행합니다. 사내 정보가 없을 때 공개 libcamera 결과만으로 사내 적용 완료를 선언하지 않습니다.

설계 질문과 소스에 연결한 설명은 프로젝트별 설정으로 작성합니다. `design_requirements`·`covers`·`evidence` 검사를 사용하고, 근거 변경 시 해시만 교체하지 말고 연결된 설명을 재검토합니다. Claude의 구축 작업과 생성기의 `agent.kind` 모델 호출 설정은 별개입니다. 생성물의 직접 수정과 자동 검사에 근거한 사람 승인 대행은 하지 않습니다.

## 자주 쓰는 명령

```bash
uv sync --extra dev                # 의존성 설치 (Python 3.11 이상)
uv run pytest -q                   # 전체 회귀 테스트
uv run pytest tests/test_impact.py -q                    # 파일 하나만 실행
uv run pytest tests/test_impact.py::test_이름 -q         # 테스트 하나만 실행
```

파이프라인 명령(`sdd extract`, `impact`, `generate`, `update`, `accept`, `export-site` 등)과 종료 코드·상태 파일은 [명령 참조](docs/reference/cli.md)에 있습니다. 설정 키는 [설정 참조](docs/reference/config.md)에 있습니다. 문서를 추가·수정할 때는 [문서 지도](docs/README.md)의 구조 원칙을 따릅니다.

다른 프로젝트 설정은 `uv run sdd --config examples/libcamera/sdd.yaml <명령>`처럼 지정합니다. `--config`는 지정한 파일을 그대로 읽으므로 한 디렉터리에 설정을 여럿 둘 수 있고, 로컬 덮어쓰기는 같은 이름의 `.local.yaml`에서 찾습니다. LLM 없이 흐름만 확인하려면 `sdd.local.yaml`(Git 제외)에 `agent: {kind: dry-run}`을 둡니다. 기본 `sdd.yaml`은 사내 HAL용 예시 경로이므로 실제 실행 전에 수정이 필요합니다.

## 아키텍처

파이프라인 단계: `extract`(facts.json 추출) → `impact`(Git diff로 재생성 대상 계산과 범위 누락 검사) → `generate`(LLM 설명 + Mermaid + 인용 검증) → `export-site`/`verify-site`(사이트 생성과 검증).

핵심 데이터 흐름과 책임 분리는 `docs/concepts/code-structure.md`에 있습니다. 요점은 다음과 같습니다.

- 구조 정보(클래스, 관계, 다이어그램)는 `facts.json`에서만 가져옵니다. `src/sdd/diagrams.py`가 Markdown 생성과 사이트 빌드가 공유하는 Mermaid 규칙이며, LLM에는 배치나 화살표 생성을 맡기지 않습니다.
- `impact.py`가 재생성 대상을 계산하고, `coverage.py`가 문서 범위 누락을 판정합니다. `coverage.py`는 Config·Git·파일에 접근하지 않고 주입받은 값만 사용합니다. `impact → coverage → impact` 순환 의존을 다시 만들지 않습니다.
- 클래스·함수 이름 비교는 생성·그림·영향 분석·범위 검사가 같은 함수(`matching.py`)를 사용합니다. C++ 이름은 대소문자를 구분하고, 경로 glob은 심볼 선택과 별도 규칙입니다.
- 영향 밖의 원고는 LLM을 부르지 않고 인용을 새 facts로 재검증한 뒤 이월합니다(`carryover.py`). 인용이 어긋난 원고는 이월하지 않고 재생성 대상으로 보고합니다.
- `manuscript.py` 린트가 문장 형태(종결어미, 대화체, 프롬프트 누설, 절대 경로)를 검사하고, `validate.py`가 인용 토큰이 facts의 위치 집합에 있는지 검사합니다. 두 검사 모두 문장의 의미가 참인지는 보장하지 않으며, `ok`/`mapped` 상태를 사람 검토 통과로 승격하지 않습니다.
- 사이트 빌드는 임시 디렉터리에서 검증한 뒤 배포 디렉터리에 반영하고, 직전 manifest가 소유한 파일만 정리합니다. 실패 시 기존 출력을 보존합니다.

설정 계층: `sdd.yaml` + `sdd.local.yaml`(로컬 덮어쓰기, Git 제외)이 소스·출력·LLM·검사 정책을 담고, `config/sections.yaml`이 문서 종류와 클래스 선택·변경 감시 규칙을, `config/scenarios.yaml`이 추적할 호출 진입점을 담습니다. `prompts/`, `templates/`, `style/`이 설명 지시문과 집필 규칙입니다.

## 테스트 기준

CI(`.github/workflows/tests.yml`)는 Ubuntu/Windows와 Python 3.11/3.14에서 `pytest`를 실행합니다. 수정 시 반복 실행의 동일성, 관계 추가·삭제 반영, 삭제·이름 변경·한글 경로 처리, 실패 시 기존 출력 보존을 회귀 테스트로 확인합니다. CSS/JS 변경은 데스크톱·모바일 화면과 검색·그림 조작을 브라우저에서 직접 확인합니다.
