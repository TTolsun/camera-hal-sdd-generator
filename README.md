# camera-hal-sdd-generator

사내에 전달하려면 [검증된 GitHub 릴리스](https://github.com/TTolsun/camera-hal-sdd-generator/releases/tag/inhouse-2026-10-27-r2) 링크를 공유하세요. 메일에 ZIP을 첨부할 필요 없이 반입 파일·시작 프롬프트·체크섬·검증 기록을 각각 받을 수 있습니다. [시작 안내](docs/inhouse/package.md)에 실행 순서, 품질 합격 기준과 복구 절차를 모았습니다.

[2026-10-27 릴리스 노트](docs/inhouse/release-2026-10-27.md)에서 최신 병합 기능, 개정 2의 변경점과 사내 적용 조건을 확인하세요.

**사내 Camera HAL에 처음 적용한다면 [1단계: 준비물](docs/inhouse/01-prepare.md)을 여세요.** 전체 문서 지도는 [docs/README.md](docs/README.md)에 있습니다.

**모델 호출은 기본 Hermes CLI를 경유합니다.** OpenCode 또는 Claude Code로 바꾸려면 [CLI 선택 안내](docs/inhouse/cli-agents.md)의 `agent.runner`를 설정합니다. 모델·제공자는 선택한 CLI 설정을 사용하며 직접 모델 API로 자동 전환하지 않습니다.

C++ Camera HAL 소스에서 검토용 설계 문서(SDD)를 만들고, 새 커밋이 올라올 때마다 바뀐 부분만 다시 만드는 생성기입니다.

```
compile DB ──▶ 사실 추출(Clang) ──▶ 영향 분석 ──▶ 문서 생성 ──▶ 사이트 검증 ──▶ 게시
                                      │
                                      └─ 문서가 다루지 않는 변경 → 자동 분류 / LLM 판정 / 사람 판단
```

## 지금 할 수 있는 것

| 할 일 | 상태 |
|---|---|
| 클래스·함수·호출 흐름을 소스에서 추출하고, 인용이 소스와 맞는지 검사 | 공개 libcamera(파이프라인 10개, IPA 7개, TU 299개)에서 동작 |
| 커밋마다 영향 받은 문서만 갱신하고, 실패하면 같은 커밋부터 재개 | 공개 libcamera에서 동작 |
| 문서가 다루지 않는 변경을 사람·LLM에게 넘기는 관문 | 공개 libcamera에서 동작 |
| NDK-build·legacy HAL3 소스 | 재현 시험(`tests/test_ndk_hal3.py`)만 통과. **사내 HAL에서는 아직 실행하지 않았습니다.** |

자동 검사의 `ok`·`mapped`, LLM 판정은 사람의 승인이 아닙니다. 승인은 `sdd accept` 기록만 인정합니다. 설명 문장의 의미가 맞는지는 사람이 확인해야 합니다.

## 저장소 역할

| 저장소 | 관리 대상 |
|---|---|
| `camera-hal-sdd-generator` (이 저장소) | 추출, 영향·범위 검사, 문서·그림 생성, 사이트 검증 |
| [libcamera-sdd](https://github.com/TTolsun/libcamera-sdd) | 공개 libcamera로 만든 검증용 문서와 [게시 사이트](https://ttolsun.github.io/libcamera-sdd/) |

사내 소스와 그로부터 만든 facts·원고·프롬프트·로그는 공개 저장소에 올리지 않습니다. 작업 기준은 [AGENTS.md](AGENTS.md)에 있습니다.

## 개발

```bash
uv sync --extra dev
```

```bash
uv run pytest -q
```

CI는 Windows·Ubuntu와 Python 3.11·3.14에서 회귀 테스트를 실행합니다. 코드 구조는 [책임 분리](docs/concepts/code-structure.md), 사이트 디자인은 [DESIGN.md](DESIGN.md)를 따릅니다.

저장소는 MIT 라이선스입니다. 외부 의존: libclang Apache-2.0(LLVM 예외), clang-uml Apache-2.0, Mermaid·PyYAML·pymdown-extensions·mkdocs-material MIT, Markdown BSD-3-Clause.
