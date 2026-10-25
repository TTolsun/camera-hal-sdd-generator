# 두 개요의 로컬 Qwen 생성과 소스 변경 시험

**Vendor 개요와 Developer 시스템 개요를 생성할 때 `agent.kind: ollama`로 실행하세요.** 공개 libcamera 예제의 두 섹션은 `vendor-overview`와 `overview`입니다. 설명은 로컬 Qwen이 쓰고, 생성기는 질문·소스 선택·인용·그림·검증을 담당합니다.

## 생성 경로

1. 공식 소스의 커밋과 빌드 설정에 맞는 facts를 추출합니다. Linux 빌드가 필요한 Windows 환경은 [WSL 어댑터](../../examples/libcamera/extract_wsl.py)를 `update.extract_cmd`에 연결할 수 있습니다.
2. 두 개요를 명시적으로 생성합니다. 이 명령은 기존 설명을 그대로 이월하지 않고 선택한 섹션의 모든 질문에 모델을 호출합니다.

   ```powershell
   python -m sdd.cli --config <실행 설정>/sdd.yaml generate --sections vendor-overview
   python -m sdd.cli --config <실행 설정>/sdd.yaml generate --sections overview
   ```

3. 소스에 새 커밋이 생기면 같은 설정으로 갱신합니다. checkout, 실제 추출, 변경 영향 분석, 영향을 받은 주제의 모델 호출, 근거 검증 순서로 진행합니다. 질문과 근거가 같은 주제는 원래 작성자를 기록한 채 유지합니다.

   ```powershell
   python -m sdd.cli --config <실행 설정>/sdd.yaml update --to <새 커밋>
   ```

4. 새 문장의 영어 번역과 사이트를 생성하고 검사합니다. 생성된 HTML이나 모델의 설명 문장을 직접 고쳐서 검사에 통과시키지 않습니다.

   ```powershell
   python -m sdd.site_localization --config <실행 설정>/sdd.yaml --out <프로젝트>/english.json --translate
   python -m sdd.cli --config <실행 설정>/sdd.yaml export-site --out <게시 저장소>/docs
   python -m sdd.cli --config <실행 설정>/sdd.yaml verify-site --out <게시 저장소>/docs
   ```

두 개요는 책임·조건별로 질문을 나눕니다. 예를 들어 스트림 설정의 사전 검증, `setStream()` 연결 책임, 실패 반환값을 각각 묻습니다. 질문 설정에 설명 정답을 넣지 않습니다. C++의 `->`와 템플릿 표기는 모델 출력 스키마에서 허용하며, 코드 밖의 HTML은 별도로 거부합니다.

## 소스 변경 시험의 구분

이 시험은 공식 upstream에 새 변경이 생겼다고 가정하지 않습니다. 별도 복제본에서 `PipelineHandler` 생성자의 `maxQueuedRequestsDevice` 기본값을 `32 → 16 → 32`로 바꾸는 두 시험 커밋을 만듭니다. 마지막 커밋의 전체 소스 트리가 공식 커밋과 같은지 비교합니다. 시험 커밋은 upstream 이력이나 배포할 공식 소스로 취급하지 않습니다.

각 시험 커밋에 `sdd update`를 실행해 다음을 검사합니다.

- 두 개요가 변경 영향 목록에 들어가고 `queue-limit` 주제의 답변이 실제 모델 호출로 바뀌어야 합니다.
- 설명에 들어가는 숫자가 해당 소스의 값과 같고 이전 숫자가 남지 않아야 합니다.
- 변경되지 않은 주제의 답변과 원래 작성자가 유지돼야 합니다.
- 완료 커밋, 추출 결과, 원고, 요청·응답 해시를 서로 대조할 수 있어야 합니다.

배포 원고는 공식 소스 값인 `32`를 설명해야 합니다. 복원한 원고를 공식 커밋의 facts·발췌와 다시 검증해 이월한 뒤 게시합니다. 시험용 `16` 설명은 재현 증빙에만 보관합니다.

## 공개 기록 확인

공개 SDD 저장소의 `qwen-overviews/`에는 단계별 원고와 `proof.json`을 보관합니다. 아래 검증기는 모델 응답과 원고를 비교할 때 코드 식별자의 백틱 서식 차이만 허용합니다. 인용문은 실제 요청에 포함된 발췌와 비교합니다.

```powershell
python examples/libcamera/verify_overview_replay.py <공개 SDD 복제본>/qwen-overviews
```

이 검사는 기록의 연결과 시험 결과를 확인합니다. 임의의 코드 변경에서도 모델이 정확한 설명을 만든다는 보장이나 사람 승인이 아닙니다. 사내 HAL과 실기기 검증도 포함하지 않습니다. 공개 정기 예약은 설치하지 않습니다.

다음 단계: [공개 Vendor 개요](https://ttolsun.github.io/libcamera-sdd/vendor-overview.html)에서 설명과 코드 근거를 대조하세요.
