# libcamera 두 커밋 변경 반영 검증

**2026-09-21 검증 결과는 부분 통과입니다. 구조 추출과 Mermaid 갱신은 확인했지만, 문서 범위 누락과 설명의 의미 오류가 있어 무인 게시 기준을 충족하지 못했습니다.** 최종 적용 대상인 사내 Camera HAL을 검증한 결과는 아닙니다.

## 비교 대상과 조건

| 항목 | A: 변경 전 | B: 변경 후 |
|---|---|---|
| 커밋 | `0a881d263755d97d912c5fb5302c8de095cd5148` | `279d355ef8f7a4f98bb0a3004c0f788387814506` |
| 변경 | LSC 추가 직전입니다. | IPU3 Lens Shading Correction 알고리즘을 추가합니다. |
| 전체 빌드 | 성공했습니다. | 성공했습니다. |
| Translation unit | 170개입니다. | 171개입니다. |
| Clang 파싱 오류 | 0건입니다. | 0건입니다. |
| 클래스 / 자유 함수 | 1,004개 / 427개입니다. | 1,005개 / 429개입니다. |
| 검증한 인용 / 파일 | 4,810개 / 329개입니다. | 4,825개 / 331개입니다. |
| 빌드·추출·위치 검증 소요 | 약 347초입니다. | 약 350초입니다. |

기존 소스 작업본을 바꾸지 않고 Linux worktree 두 개에서 같은 Clang/Meson 옵션으로 각각 새로 빌드했습니다. IPU3·RKISP1·UVC, IPU3/RKISP1 IPA와 GStreamer를 활성화했습니다. compile DB를 각각 보정하고 전체 facts를 각각 추출했습니다. 두 실행은 병렬로 진행했습니다.

문서 생성에는 동일한 Windows 로컬 Ollama `qwen3.5:4b`, temperature 0, 16,384 토큰 컨텍스트를 사용했습니다. 모델 digest는 [검증 기록](../../../examples/libcamera/validation/20260921/result.json)에 남겼습니다. 기존 원고가 없는 별도 디렉터리에서 각 커밋의 네 페이지를 생성했으며, 사실 입력 생략은 없었습니다. 생성기의 기준 커밋은 `bec652f`이고 이 검증을 위한 실행 스크립트를 추가했습니다.

## 코드와 그림의 대조

원본 변경 파일은 다섯 개입니다. `algorithms/lsc.cpp`, `algorithms/lsc.h`, `algorithms/meson.build`, `ipa_context.cpp`, `ipa_context.h`가 모두 `src/ipa/ipu3/` 아래에 있습니다.

| 검사 대상 | A | B | 판정 |
|---|---|---|---|
| `ipu3::algorithms::Lsc` 클래스 | 없습니다. | 있습니다. | 통과했습니다. |
| `Lsc` → `ipu3::Algorithm` 상속 | 없습니다. | 있습니다. | 통과했습니다. |
| `Lsc` → `ipa::LscAlgorithm` 필드 참조 | 없습니다. | 있습니다. | 통과했습니다. |
| `ipu3::IPAActiveState` → `ipa::lsc::ActiveState` 필드 참조 | 없습니다. | 있습니다. | 통과했습니다. |
| `ipu3::IPAFrameContext` → `ipa::lsc::FrameContext` 필드 참조 | 없습니다. | 있습니다. | 통과했습니다. |

이름이 있는 클래스의 순증은 `Lsc` 한 개입니다. 익명 구조체는 추출 식별자에 파일 경로와 줄 번호가 들어가므로, 비교할 때 worktree 루트를 정규화해도 줄 이동이 별도의 추가·삭제로 보일 수 있습니다. 이를 실제 클래스 추가로 집계하지 않았습니다.

검증용 섹션은 공통 LSC 타입, IPU3 상태 타입과 `Lsc`를 명시적으로 선택했습니다. [변경 전 Mermaid](../../../examples/libcamera/validation/20260921/before.mmd)에는 노드 7개와 관계 2개가 있고, [변경 후 Mermaid](../../../examples/libcamera/validation/20260921/after.mmd)에는 노드 9개와 관계 6개가 있습니다. 추가된 두 노드는 `Lsc`와 직접 기반 클래스이며, 추가된 네 관계는 위 표와 일치합니다. 브라우저에서도 두 그림이 실제 SVG로 렌더링되는 것을 확인했습니다.

## 기존 문서 범위의 한계

기존 카메라·Pipeline Handler·IPA 세 페이지는 모두 변경 영향 대상으로 선택됐습니다. Meson 파일을 공통 watch 대상으로 지정했기 때문입니다. 그러나 이 페이지들의 클래스 선택에는 새 `Lsc`와 관련 상태가 없어 Mermaid는 세 페이지 모두 동일했습니다.

카메라와 Pipeline Handler의 모델 설명도 동일했습니다. IPA 설명은 달라졌지만 첫 모델 입력은 A/B가 동일했고 그림도 같았습니다. 따라서 IPA 문장 차이는 이번 코드 변경을 반영했다는 증거로 사용할 수 없습니다.

검증용 네 번째 섹션을 추가하면 관련 구조가 그림에 반영됩니다. 이는 공통 생성기가 변화를 표현할 수 있음을 확인한 것이며, 기존 운영 문서 설정의 누락을 해소했다고 판정한 것은 아닙니다.

## 설명과 자동 검사의 한계

원래 생성기는 여덟 페이지의 인용 검사 결과를 모두 `ok`로 표시했습니다. 각 사이트는 안내 페이지를 포함해 5페이지이며 내부 링크와 출력 해시 검사도 통과했습니다. 이 결과와 별개로 아래 내용은 미통과입니다.

- A의 검증용 설명은 LSC의 IPU3 상태 연결을 이미 존재하는 것처럼 설명합니다. A의 `ipa_context.h`에는 해당 LSC 필드가 없습니다. 또한 실제 `libcamera::ipa::LscAlgorithm`을 다른 네임스페이스의 이름으로 서술합니다.
- B의 설명은 `IPAActiveState`와 `IPAFrameContext`가 모두 상위 클래스를 상속한다고 설명합니다. `IPAActiveState`에는 기반 클래스가 없으므로 잘못된 일반화입니다.
- A에는 `libcamera::ipa::lsc.h:27`, `libcamera::ipa::lsc.h:31`이라는 잘못된 인용 경로가 있습니다. 정상 경로는 `src/ipa/libipa/lsc.h`입니다. 기존 정규식은 잘못된 토큰을 무시했고 다른 정상 인용이 있어 전체 검사를 통과시켰습니다.

마지막 인용 검출 문제는 실패하는 회귀 테스트로 재현한 뒤 수정했습니다. 수정된 검사기로 원래 A 원고를 다시 검사하면 잘못된 두 경로를 검출하고 실패합니다. 원래 생성 원고와 당시 상태는 검증 증거로 보존했으며, 수정된 검사 결과를 별도 기록했습니다. **모델을 다시 호출해 실패 사례를 대체하지 않았습니다.** 수정 후 전체 로컬 테스트 33개가 통과했습니다.

이 수정은 경로 검출 누락을 막습니다. 잘못된 클래스 관계 설명, 인용이 있어도 근거와 맞지 않는 주장, 인용 없는 문장을 모두 검증하는 기능은 아닙니다. 자동 인용 검사를 사람의 기술 내용 승인으로 취급하면 안 됩니다.

## 재실행 방법

Linux 빌드·추출 환경에서 아래를 실행합니다. 두 커밋이 존재하는 libcamera 저장소, Linux 생성기 Python 환경, 매번 새로운 workdir를 지정하세요. 결과를 Windows로 옮기려면 `--export-to /mnt/c/.../build/revision-validation/<run>`을 추가합니다.

```bash
python examples/libcamera/validate_revisions.py \
  --source /path/to/libcamera \
  --base 0a881d263755d97d912c5fb5302c8de095cd5148 \
  --head 279d355ef8f7a4f98bb0a3004c0f788387814506 \
  --workdir /path/to/new-validation-run --jobs 3 \
  --export-to /path/to/exported-results
```

Windows 생성기 환경에서는 `sdd.local.yaml`의 로컬 Ollama 설정을 사용합니다.

```powershell
uv run python examples/libcamera/narrate_revisions.py --root build/revision-validation/<run>
uv run python examples/libcamera/compare_revision_outputs.py --base-dir build/revision-validation/<run>/a --head-dir build/revision-validation/<run>/b --out build/revision-validation/<run>/comparison.json
```

전체 facts·빌드 로그·프롬프트·HTML·원고는 로컬 `build/revision-validation/20260921/`에 보관했습니다. 작은 비교 기록과 Mermaid만 저장소에 포함했습니다. 검증 과정에서 공개 Pages를 새 원고로 교체하거나 upstream 브랜치를 갱신하지 않았습니다.

후속 작업에서 문서 범위 검사, 관계 근거 입력, 주제별 소스 발췌와 지문 검사를 추가했습니다. 같은 커밋 쌍으로 수행한 결과와 남은 한계는 [설계 근거 재검증](design-validation.md)에 기록합니다. 위 최초 실행 결과는 실패 사례를 포함하여 그대로 보존합니다.
