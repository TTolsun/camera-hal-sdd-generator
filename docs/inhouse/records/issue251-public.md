# #251 사내 파일럿의 공개 준비 기록

**실제 사내 파일럿은 미완료이며 적용 가능 여부는 판단 보류입니다.** 2026-11-05 사용자가 사내 입력과 승인된 실행 환경이 아직 준비되지 않았다고 확인했습니다. 아래는 공개 mini HAL의 실행 결과와 공통 안내·검증 도구 보완입니다. 실제 제품·빌드·실기기·사람 승인·내부 게시의 증거로 사용하지 않습니다.

## 기존 기능과 이번 보완

착수 기준은 생성기 `bc58d09a35e2169bc1d23d972721dd97eaa68ebb`입니다. 이슈 #251 본문과 댓글(0개), AGENTS.md·DESIGN.md·사이트·독자 품질·집필 규칙을 읽었습니다. 기존 추출, 변경 영향 분석, CLI 체크포인트, 승인 장부, 게시 대조와 실패한 커밋부터의 재개 기능을 재사용합니다. #241–#243의 공유 실행 계약을 별도로 만들지 않습니다.

| 확인한 공백 | 반영한 내용 |
|---|---|
| 사전 예상과 실제 실행 결과를 연결할 자리가 부족했습니다. | [파일럿 안내](../pilot.md)와 기존 `handoff.md`에 입력·기준, 독립 근거 대조, 실제 변경의 예상/실제 영향, 승인·게시 해시와 판단 보류를 연결했습니다. |
| 실제 CLI 시험이 올바른 Mermaid 조건을 실패로 처리했습니다. | `tools/evaluate_visuals.py`가 `>`의 Mermaid 숫자 이스케이프 `#62;`와 줄바꿈을 처리하게 했습니다. 성공·실패 양쪽의 완료 연결, 간선별 레이블, 정확한 조건 값도 대조합니다. |

공통 생성·렌더링·번역 코드, 공개 libcamera 설정·원고·스타일은 변경하지 않았습니다. 생성 HTML을 직접 수정하지 않았으며 CLI 사용법과 `impact.json` schema 1을 유지합니다.

## 실제 공개 CLI 실행

생성에는 `tools/evaluate_visuals.py --runner codex --model gpt-6.1-terra --cli-arg=-c --cli-arg='model_reasoning_effort="high"' --with-prose`를 새 출력 경로에서 실행했습니다. 별도 근거 검토도 `kind: cli`, `runner: codex`, `model: gpt-6.1-terra`, `args: [-c, 'model_reasoning_effort="high"']`를 별도 설정·호출로 실행했습니다. 전역 기본값을 바꾸지 않았습니다.

| 시험 | 실제 결과와 원본 |
|---|---|
| 최초 생성·소스 변경 | [공개 시험 report.json](../../../examples/libcamera/validation/issue251/runs/mini-hal/report.json): 원고 2회·그림 2회, 실제 CLI 총 4회가 완료됐습니다. 원래 `ret == 0`에서 변경 후 `ret >= 0`으로 결과 전송 조건이 바뀌었고, 두 경우 모두 `onFrameDone`이 if 밖에 있습니다. 입력 지문과 원응답·영수증을 보존했습니다. |
| 사이트 반복·오래된 입력 차단 | 같은 원고의 사이트 반복 manifest가 같았습니다. facts만 다음 커밋으로 바꾸면 이전 원고의 export가 실패하고 기존 사이트가 보존됐습니다. 새 원고 생성 후 verify-site는 링크 오류 0과 manifest 일치를 확인했습니다. 이 시험의 facts는 공개 소스 발췌를 수집한 것이며 제품 compile DB의 추출 시험이 아닙니다. |
| 최초 검증 도구 실패 | [최초 실패 기록](../../../examples/libcamera/validation/issue251/runs/initial-render-check-failure/report.json)을 보존했습니다. 변경 후 조건이 `#62;`로 출력됐지만 HTML 디코딩만 하던 시험이 assertion에서 멈췄습니다. 실패를 수정 전 성공으로 바꾸지 않았습니다. |
| 독립 검토 | [1차](../../../examples/libcamera/validation/issue251/runs/independent-review/result.json)에서 성공 경로의 완료 연결·간선 검사 공백, [2차](../../../examples/libcamera/validation/issue251/runs/independent-review-final/result.json)에서 조건 접두사 오탐을 지적했습니다. 수정 후 [3차](../../../examples/libcamera/validation/issue251/runs/independent-review-final-2/result.json)는 `pass`, 지적 0개입니다. 이는 제공된 소스·산출물·수정 코드의 정적 대조이며 실행·사람 승인을 대신하지 않습니다. |
| 지정 CLI 실패·재개 | [실행 로그와 실패 전 해시](../../../examples/libcamera/validation/issue251/runs/cli-failure-retry/failure-report.json): 분리된 공개 사본에서 같은 Codex에 의도적으로 잘못된 인자를 전달했습니다. 비정상 종료 뒤 기존 원고·사이트의 파일별 해시가 같았습니다. 인자를 복구하고 같은 모델·CLI의 신규 실제 호출 1회로 생성과 사이트 검사를 재개했습니다. 사람이 승인한 장부는 만들지 않았습니다. |
| 전체 생성 반복의 한계 | [반복 진단](../../../examples/libcamera/validation/issue251/runs/cli-failure-retry/repeat-diagnosis.json): 이 작은 시험은 `cli_checkpoint: false` 기본값으로 매번 새 원고 호출을 수행했습니다. 전체 generate → export-site 반복의 본문·manifest는 같지 않았습니다. 사이트만의 반복 성공으로 전체 생성 동일성을 통과 처리하지 않습니다. 사내에서는 승인된 재사용 정책을 고정하고 다시 시험해야 합니다. 공통 재사용 정책의 심화 검증은 #242의 범위입니다. |

원본 입력·출력과 실행 스크립트는 [공개 증거 디렉터리](../../../examples/libcamera/validation/issue251/README.md)에 있습니다. 처음과 최종 시험 사이의 조건 검사 보강은 최종 소스와 보존한 두 커밋의 실제 산출물을 다시 대조했습니다. 새 LLM 생성으로 표시하지 않습니다. 자동 회귀는 Mermaid 조건·두 완료 경로·간선 오류·접두사 오탐, 문서 링크와 사내 템플릿을 포함해 469개가 통과했습니다. 테스트 대역은 실제 CLI 호출과 구분합니다.

최신 main 통합 후 관련 회귀 480개가 통과했습니다. 보존한 CLI 기록 19개는 요청·응답 해시뿐 아니라 실행 인자·완료 이벤트·native stdout 해시도 재검증했습니다. 원본 파일 275개의 커밋 바이트가 작업 공간의 기록과 같음을 Git archive로 대조했습니다. 해당 커밋 `b043a37`의 반입 ZIP은 파일 777개의 무결성을 통과했습니다. 이 반입 시험은 설치·사내 실행 시험이 아닙니다. 느린 로컬 전체 회귀는 중단하고 PR #256의 전체 CI와 구분해 확인합니다.

## 공개 libcamera와 배포 범위

공식 `https://gitlab.freedesktop.org/camera/libcamera.git` master와 공개 `upstream/master`를 조회해 모두 `be7e83e91348250c015aad6d6f59f1468555bae8`임을 확인했습니다. 추가 동기화 커밋은 필요하지 않았습니다. 공개 main `178aa978890a22df5e984bc5efe18a1a3756aa1b`의 사이트는 62개 HTML·링크 오류 0·manifest 일치를 로컬에서 확인했습니다.

이번 수정은 안내·시험 도구·회귀에 한정되므로 공개 SDD 산출물을 바꿀 입력이 없습니다. 빈 배포 커밋은 만들지 않습니다. 기존 Pages 배포 실행 `41889103128`은 별도 #82 변경의 deploy 단계가 상태 응답을 받지 못해 시간 초과했습니다. 실패한 job 재시도도 deployment 취소 상태로 실패해 기존 `main:/docs`의 새 Pages 빌드를 요청했습니다.

그동안 #242 공개 반영으로 main이 `58a99216fa3c5115f9d5cbefb188d030dde2d21c`로 전진했습니다. 해당 사본을 fast-forward로 갱신하고 [새 Pages 실행](https://github.com/TTolsun/libcamera-sdd/actions/runs/41894771264)의 성공을 확인했습니다. `verify-site`는 HTML 62개·링크 오류 0·manifest 일치를, `verify-publication`은 [실제 공개 URL](https://ttolsun.github.io/libcamera-sdd/)의 전체 산출물 328개 일치를 확인했습니다. build_id는 `b5da5d8c424ca64f03fde9b9d730d143de5e4bcd3e25fba3aab05168c9ee9b05`입니다. 다른 이슈의 공개 반영을 #251의 문서 보완으로 계산하지 않으며, 공개 전체 누락 보완이나 #215 완료를 주장하지 않습니다.

## 미충족 조건과 재개 입력

| #251 완료 조건 | 상태와 필요한 입력 |
|---|---|
| 실제 사내 범위·사전 기준 | 미완료입니다. 내부에서 제품·변형·요청 경로, 기준 SHA, DB 생성 명령·헤더·매크로·TU, 질문별 합격 기준을 고정해야 합니다. |
| 실제 최초 실행·독립 검토·사람 검토·내부 게시 | 미완료입니다. 승인된 내부 작업 위치, 생성·검토 CLI 프로필, 코드 링크·자산·게시 대상과 사람 검토자가 필요합니다. |
| 동일 입력·실제 변경·실패 재개 | 사내에서는 미실행입니다. 실제 변경 전후 SHA와 예상 영향, 영향 밖 문서·승인 보존, 분리된 실패 시험 공간과 원본 증거가 필요합니다. |
| 적용 가능성 판단 | 판단 보류입니다. 입력 부재를 적용 불가로 바꾸지 않았습니다. 미검증 장치·빌드·실기기 범위를 내부 기록에 남겨야 합니다. |

이 페이지의 항목은 실행 결과·한계·재개 입력을 비교하는 표이므로 별도 그림을 생략했습니다. 실제 단계·승인·게시 관계는 [파일럿 안내의 그림](../pilot.md#실행과-증거-연결)을 따릅니다.

다음 단계: 승인된 내부 작업 위치에서 [파일럿 절차](../pilot.md)의 사전 입력을 고정하세요. 내부 자료를 공개 이슈·채팅으로 보내지 않습니다.
