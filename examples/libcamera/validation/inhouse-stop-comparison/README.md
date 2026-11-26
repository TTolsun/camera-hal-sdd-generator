# 공개 libcamera로 사내 템플릿의 첫 문서와 보완 문서 비교하기

Vendor 담당자가 촬영을 정지할 때 정상 완료와 취소를 판별하고 요청·버퍼를 언제 다시 쓸 수 있는지 설명하는 예제입니다. 공개 사이트의 소스 인용과 같은 커밋의 Git 체크아웃 및 추출된 facts가 필요합니다. 예제 기준은 `adfa719f8ed67d18fd8a0739fc088a1f8b9e7252`입니다.

| 입력 | 적용 방법 |
| --- | --- |
| `first-run.yaml` | 사내 첫 실행 안내에 따라 작은 문서를 구성합니다. Vendor 연동 가이드의 완료·소유권 질문과 제목을 가져와 일반적인 인터페이스 계약 및 공통 구현 발췌를 연결합니다. |
| `focused.yaml` | 같은 두 주제의 질문을 촬영 정지 시 독자가 해야 하는 판단으로 구체화하고, 필요한 상태·콜백·장치 큐·버퍼 재등록 및 fence 근거를 보강합니다. |
| `visuals.yaml` | 두 조건 모두 사내 템플릿의 요청 제출·결과 통지와 요청·버퍼 수명 그림을 생성합니다. |

`prepare.py`는 사내 템플릿에서 설정을 복사합니다. 두 조건은 같은 소스·facts, 집필 규칙과 표준 프롬프트(`standard`), 그림 정의, Codex CLI `gpt-6.1-terra` / `high`를 사용합니다. 두 설정은 섹션 입력 파일만 서로 다릅니다. 문서는 첫 실행에 맞춰 두 주제로 제한합니다. 전체 Vendor 연동 가이드에서는 해당 독자 프로필의 필수 질문을 모두 충족해야 합니다.

## 재현

생성기 루트에서 실행하세요. 예시에서 `LIBCAMERA_CHECKOUT`, `MATCHING_FACTS_DIR`는 각각 고정 커밋의 Git 체크아웃과 같은 커밋의 `facts.json`이 있는 디렉터리로 바꾸세요. `prepare.py`가 두 커밋의 일치를 확인합니다. 새로 추출할 경우 [공개 실험실 절차](../../../../docs/libcamera/home-lab.md)를 따라 Meson 컴파일 DB와 생성 헤더를 준비하고, `--compdb`로 그 DB를 지정하세요. 기존 facts를 사용하는 비교는 구조 재추출이나 장치 시험을 수행하는 절차와 구분합니다.

```text
uv run python examples/libcamera/validation/inhouse-stop-comparison/prepare.py --source LIBCAMERA_CHECKOUT --facts-dir MATCHING_FACTS_DIR --commit adfa719f8ed67d18fd8a0739fc088a1f8b9e7252 --out build/inhouse-stop-comparison
uv run sdd --config build/inhouse-stop-comparison/first-run/sdd.yaml generate --sections vendor-contract --plan-only
uv run sdd --config build/inhouse-stop-comparison/focused/sdd.yaml generate --sections vendor-contract --plan-only
uv run python -m sdd.evaluate_reader --config build/inhouse-stop-comparison/first-run/sdd.yaml --section vendor-contract --out build/inhouse-stop-comparison/first-run-result
uv run python -m sdd.evaluate_reader --config build/inhouse-stop-comparison/focused/sdd.yaml --section vendor-contract --out build/inhouse-stop-comparison/focused-result
```

계획에서 소스 SHA, 질문별 근거와 새 호출 예정 단위, CLI 모델·추론 인자를 확인하세요. 두 결과는 각자의 `manuscripts/`, `build/prompts/`, `evaluation.json`에 남습니다. 각 결과의 CLI 완료 영수증과 자동 검사 상태를 읽은 뒤 원고를 열어 같은 독자 과제로 비교합니다.

처음 보는 독자에게는 조건 이름이나 기대하는 상태값을 알려 주지 않고 다음 질문을 그대로 줍니다.

> 정지 처리 중 완료 통지를 받았습니다. 프레임을 사용해도 됩니까? 버퍼를 다시 쓰기 전에 무엇을 확인하겠습니까? 문서만으로 결정할 수 있는 경우와 부족한 경우를 나누세요. 결론마다 실제로 읽은 짧은 문장과 소제목을 인용하고, 찾을 때 거친 절과 모호했던 문장을 적으세요.

평가자는 인용한 코드가 뒷받침하는 답과 실기기 또는 애플리케이션에서 추가 확인할 조건을 기록합니다. 원고와 그림을 각각 확인하고, 그림이 서술에 없는 보장을 추가하는지도 살펴봅니다. 자동 검사, 독립적인 근거 대조, 사람 승인은 각각 따로 기록합니다.

고정 소스로 수행한 첫 실행, 입력 한도 초과, 중간 원고의 오독과 최종 원고에 대한 판단은 [비교 결과](../../../../docs/libcamera/records/inhouse-stop-comparison/README.md)에 있습니다.
