# 로컬 Qwen의 실제 소스 변경 갱신 검증

**공개 libcamera의 실제 커밋 변경을 `sdd update`로 처리하고, 새 설명이 로컬 Qwen의 HTTP 응답에서 만들어지는지 확인합니다.** 소스가 같은 문서는 이전 작성자를 유지합니다. 모든 기존 문서를 이번에 Qwen으로 다시 썼다는 뜻은 아닙니다.

## 재현 조건

- 변경 전: `7278a59eba64358bbf3d51f557506dd5b0bce5c4`
- 변경 후: `2c4b67c0792f88f69bcdf9cbf73e81b3d8cf4b6f`
- 대상: `src/libcamera/egl.cpp`의 `eGL::createDMABufTexture2D()`
- 실제 소스 차이: `GL_RG` 분기의 `DRM_FORMAT_RG88`이 `DRM_FORMAT_GR88`로 바뀌었습니다.
- 모델: Windows 로컬 Ollama의 `qwen3.5:9b`, `think: false`, 컨텍스트 16384, 출력 상한 6000, temperature 0.1.
- 빌드·추출: 전용 WSL libcamera Meson 전체 빌드, 정규화한 compile DB 300개 번역 단위, libclang 구조·호출 분석.

공식 upstream에 새 커밋이 없어 기존의 실제 부모→자식 변경을 재실행했습니다. 기존 IPA 문서에 없던 DMA-BUF 형식·실패 설명도 추가했습니다. 질문과 소스 선택만 설정하고, 설명 문장은 Qwen이 작성했습니다.

## 실제 실행 결과

2026-10-24의 실행에서 `sdd update`가 실제 변경 커밋 한 개를 완료했고 실패 기록은 없었습니다. 변경 전후 각각 300개 번역 단위를 새로 추출했으며 파싱 오류는 0개였습니다. 최종 facts에는 클래스 1,513개와 시나리오 6개가 포함됐습니다.

변경 전 EGL 설명에 사용된 Qwen HTTP 호출은 5회, 변경 후 자동 갱신에 사용된 호출도 5회였습니다. 변경 후 답변은 `GL_RG`를 `DRM_FORMAT_GR88`에 연결했습니다. 새 문단 9개는 실제 응답과 대조했고, IPA의 나머지 7개 주제는 근거·질문이 같아 이전 답변과 작성자를 유지했습니다. 2026-10-25 재실행은 새 커밋이 없어 생성 없이 종료했습니다.

모델 digest는 `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`, Ollama 버전은 `0.40.10`입니다. 긴 템플릿 질문에서 틀린 분기 설명을 만든 초기 시험 응답은 배포 원고에 넣지 않았습니다.

## 실행 경로

1. 변경 전 커밋에서 실제 빌드와 추출을 수행합니다. 기존 원고의 근거를 재검증하고 새 EGL 질문의 답변을 Qwen으로 생성합니다. 변경 전 원고와 사용된 HTTP 호출 기록을 보존합니다.
2. Windows의 갱신 설정에 `agent.kind: ollama`와 로컬 주소를 지정합니다. Linux에서 빌드해야 한다면 `update.extract_cmd`를 [WSL 추출 어댑터](../../examples/libcamera/extract_wsl.py)에 연결합니다. 이 명령은 요청된 커밋을 실제로 빌드·추출하고 임시 facts를 반환합니다. Ollama의 네트워크 공개 범위를 넓힐 필요가 없습니다.
3. 준비한 설정으로 다음 명령을 실행합니다. `sdd update`는 checkout → 실제 추출 → 변경 영향 분석 → 필요한 주제의 LLM 생성 → 원고 검증·이월을 수행합니다.

   ```powershell
   python -m sdd.cli --config <실행 설정>/sdd.yaml update --to 2c4b67c0792f88f69bcdf9cbf73e81b3d8cf4b6f
   ```

4. 영어판의 새 문장을 같은 에이전트로 번역하고 사이트를 빌드합니다. 승인 정책은 [사이트 구성](../concepts/site.md)을 따릅니다.

   ```powershell
   python -m sdd.site_localization --config <실행 설정>/sdd.yaml --out <프로젝트>/english.json --translate
   python -m sdd.cli --config <실행 설정>/sdd.yaml export-site --out <문서 저장소>/docs
   python -m sdd.cli --config <실행 설정>/sdd.yaml verify-site --out <문서 저장소>/docs
   ```

## 확인할 기록

`update-state.json`은 처리 완료 커밋을, `impact.json`은 실제 변경 파일과 영향을 받은 문서를 기록합니다. `build/prompts/calls/`에는 호출별 요청·응답과 SHA-256, Ollama의 모델·토큰 수·완료 정보를 남깁니다. API 인증 헤더와 모델의 내부 추론은 기록하지 않습니다.

원고의 `generated_design`에는 이번에 생성한 주제와 이월한 주제, 각 주제의 원래 작성자를 기록합니다. 새 설명을 실제 HTTP 응답과 대조할 때 허용하는 자동 변환은 코드 식별자의 서식 처리뿐입니다. 응답 파일을 Codex가 작성해 주입하지 않습니다.

공개 재현 기록은 [libcamera SDD 저장소](https://github.com/TTolsun/libcamera-sdd)의 `qwen-update-proof.json`과 `qwen-replay/`에 보관합니다. 변경 전후 원고·소스 diff·호출 원문을 함께 대조하세요.

## 검증 범위

정적 소스 근거, 원고와 응답의 연결, 실패 시 보존, 증분 갱신 경로를 검사합니다. 소형 모델은 긴 함수·템플릿의 분기를 잘못 설명할 수 있으므로 작은 질문으로 나누고 결과를 소스와 대조해야 합니다. 형식 검사나 인용 일치만으로 의미 정확성을 승인하지 않습니다. 한국어·영어 문서는 사람 검토 전이며 사내 HAL과 실제 카메라 실행은 이 공개 검증에 포함되지 않습니다.

다음 단계: [공개 IPA 문서](https://ttolsun.github.io/libcamera-sdd/ipa.html)에서 설명과 소스 발췌를 확인하세요.
