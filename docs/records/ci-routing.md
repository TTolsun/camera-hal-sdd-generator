# CI 실행 중복과 문서 검증 경로

## 결과를 보기 전에 정한 비교 범위

이번 비교는 생성기 저장소의 GitHub Actions 실행을 대상으로 합니다. 공개 SDD 원고 생성·번역·의미 검토 비용은 비교에 넣지 않습니다. 기존 실패·취소 기록과 독립 검토 기록은 보존합니다.

| 사례 | 확인할 동작 |
| --- | --- |
| 코드 변경 PR의 작업 브랜치 push | push 실행 없이 PR 실행 하나만 생성 |
| 같은 PR의 후속 커밋 | 이전 PR 실행 자동 취소, 후속 실행에서 전체 검증 |
| 코드 변경 PR과 main 병합 | 기존 네 OS·Python 검사에서 첫 병합 통합 시험과 전체 회귀 시험 통과 |
| 문서만 바꾼 별도 PR에 존재하지 않는 상대 링크 추가 | 문서 경로 선택, 기존 링크 검사 실패, 전체 회귀 단계 생략 |
| 위 링크 수정과 문서 PR 병합 | 문서 경로의 기존 네 검사 통과, main push 검증 유지 |

비교 기준은 이전 코드 변경 커밋 `825e261c8aaf25e924659b623b97e414fb68d899`입니다. 같은 커밋에 [push 실행](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41939974282)과 [PR 실행](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41940078637)이 각각 생성되었습니다. 각 실행의 네 행렬 검사는 첫 병합 전 29개 시험과 전체 회귀 시험을 수행했습니다.

실행 수는 동일 head와 이벤트로 확인합니다. 소요 시간은 workflow와 job의 시작·완료 시각을 보존해 비교하며, 병렬 job 시간을 단순 합산해 사용자가 기다린 시간으로 보고하지 않습니다. 큐 대기·캐시·러너 상태와 시험 수가 다르므로 단일 실행에서 일반적인 시간 절감률을 추정하지 않습니다. 자동 취소된 작업의 미실행 시험은 성공으로 계산하지 않습니다.

## 구현과 검토 범위

검증 경로와 기록의 계약은 [CI 안내](../../ci/README.md#github-검증-경로)에 있습니다. 실제 Git 이력으로 다중 커밋·이름 변경·삭제·350개 초과 파일·한글 경로·이력 누락을 시험합니다. 독립 Codex CLI `gpt-6.1-terra`와 reasoning effort `high` 검토에서 하위 폴더의 지침·설계 파일 허용 공백을 발견해, `AGENTS.md`·`CLAUDE.md`·`DESIGN.md`를 위치와 관계없이 전체 경로로 수정했습니다. 첫 검토 요청·응답·receipt는 삭제하지 않습니다.

후속 독립 검토에서는 job의 `always()`가 concurrency 취소 후에도 비용이 큰 행렬 실행을 유지할 수 있는 결함을 찾았습니다. job 조건은 `!cancelled()`로 바꾸고, 판정 작업 실패 후 네 검사를 실패시키는 동작은 유지했습니다. 산출물 업로드 단계는 `always()`로 남겼습니다. 두 검토의 원본 요청·응답·receipt를 모두 보존합니다.

## 첫 PR 실행과 후속 커밋의 기준

구현 커밋 `496e448412baccc4448edd7feab973d9e66ea73b`을 push한 후 [PR #276](https://github.com/TTolsun/camera-hal-sdd-generator/pull/276)을 열었습니다. [첫 실행](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41947203175)은 `pull_request` 하나이며 같은 브랜치 push 실행은 생성되지 않았습니다. scope가 성공했고 네 기존 행렬 job이 시작했습니다. 판정 산출물 `ci-scope-41947203175-1`도 시험 시작 전에 업로드되었습니다.

이 문단을 후속 커밋으로 push해 위 실행의 자동 취소를 확인합니다. 후속 커밋 자체는 문서 변경이지만 PR 전체에는 CI 코드가 있으므로 전체 검증을 받아야 합니다. 실제 취소와 후속 검증의 완료 여부는 아직 확인하지 않았습니다.
