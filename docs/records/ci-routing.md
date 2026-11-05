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

## 병행 main 변경에 따른 추가 통합

첫 실행의 네 전체 회귀 단계는 후속 커밋으로 자동 취소됐습니다. scope와 네 시험 산출물은 모두 보존됐으며 취소된 시험을 성공으로 바꾸지 않았습니다. [후속 실행](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41947352000)은 네 환경의 첫 병합 전 통합 시험을 통과했습니다.

그 실행 중 병행 PR #274·#275가 main `1174e60fdb5b252e8c9266e8feb2be9b36cec04a`에 병합돼 독자 경로와 시각화 코드 등이 바뀌었습니다. 최신 main을 충돌 없이 통합했습니다. 이에 따른 재검증은 병행 변경과의 호환성을 확인하기 위한 것이며, 이번 CI 정책을 다시 고치기 위한 재작업은 아닙니다. 병행 PR의 코드·문서·원래 실행 증거를 그대로 보존합니다.

## 실제 결과와 남은 검증의 구분

[최종 통합 실행](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41948208886)은 후보 `0c846b74a6ee2662f52ddf4953e7d67f846a5c94`에서 scope와 기존 네 행렬 검사를 통과했습니다. 네 환경 모두 첫 병합 통합 29개를 통과했습니다. 전체 회귀는 Ubuntu 두 환경에서 각각 3,052개 통과, Windows 두 환경에서 각각 3,051개 통과·기존 플랫폼 차이 1개 생략입니다. [PR #276](https://github.com/TTolsun/camera-hal-sdd-generator/pull/276)은 `022400208ea6ac12d1815d2001c66b2288175c94`로 병합됐으며 후보와 병합 트리의 파일 차이는 없습니다.

| 관측 사례 | 전체 workflow 시간 | 검사·증거 |
| --- | ---: | --- |
| 이전 기준 push | 695초 | 네 전체 행렬, job 합계 1,679초 |
| 같은 이전 head의 PR | 624초 | 네 전체 행렬, job 합계 1,310초 |
| 새 코드 PR 최종 통합 | 838초 | scope 9초, 네 전체 행렬 유지 |
| 새 문서 PR 오류 주입 | 85초 | 네 링크 오류 차단, 통합·전체 단계 모두 생략 |

새 코드 후보 세 개와 문서 오류 후보에는 head별 `pull_request` 실행만 하나씩 생성됐습니다. 이전 기준의 push+PR 두 실행이 한 실행으로 줄었음을 확인했습니다. 첫 코드 실행의 네 전체 회귀는 후속 커밋으로 중단됐고, scope와 네 JUnit 산출물이 남았습니다. 문서 오류의 네 JUnit도 내려받아 의도한 링크 하나만 실패했음을 확인했습니다. [문서 오류의 환경별 시간과 수정](ci-docs-route-check.md)은 별도로 기록합니다.

예방한 비용은 같은 head의 push 전체 행렬과 오래된 PR의 남은 전체 시험, 일반 문서 변경의 전체 회귀 단계입니다. 코드 변경의 전체 CI 자체는 빨라졌다고 판단하지 않습니다. 위 코드 실행은 병행 main 변경과 러너 상태, 큐 대기까지 포함해 이전 기준보다 길었습니다. 삭제한 push 작업의 과거 1,679 job초를 이번에 정확히 절약한 시간으로 바꾸거나, 병렬 job 합계를 대기 시간으로 보고하지 않습니다. 독립 검토에서 고친 두 결함도 병합 전 수정했으므로, 수정하지 않았을 경우의 실제 재작업량은 측정하지 않았습니다.

코드 병합의 [main 검증](https://github.com/TTolsun/camera-hal-sdd-generator/actions/runs/41949965543)과 수정 문서의 최신 검사·최종 병합 기록은 [PR #278](https://github.com/TTolsun/camera-hal-sdd-generator/pull/278)에서 확인합니다. 문서 경로가 이 main 실행을 취소하지 않도록 실행별 concurrency 그룹을 사용합니다. 수동·태그의 전체 경로와 판정 실패의 검사 실패 동작은 회귀 시험에서 확인했으며, 실제 수동 실행이나 새 릴리스 태그를 만들어 추가 전체 CI를 돌리지는 않았습니다.

## 공개 산출물과 기록 보존

이번 변경은 통합한 main 대비 생성기 런타임·집필 규칙·프롬프트·공개 원고 입력을 바꾸지 않습니다. 공식 libcamera HEAD와 공개 `upstream/master`는 모두 `be7e83e91348250c015aad6d6f59f1468555bae8`였습니다. 기존 [공개 고정 표본](https://ttolsun.github.io/libcamera-sdd/validation/publication-preflight/camera-requests.html)은 `verify-publication`으로 manifest와 88개 산출물 해시가 일치함을 재확인했습니다. build ID는 `bae7adb7ba99cb951db2f6ad675dcd922f7c74cdccf411f9110c71becafa5d26`이며 CI·안내 변경 때문에 새 공개 배포 커밋을 만들 필요는 없습니다. 병행 PR의 독자 경로 코드 변경과 공개 반영은 그 PR의 범위이며, 이 고정 표본 확인을 최신 전체 책이나 사내 HAL 검증 완료로 확대하지 않습니다.

GitHub 실행과 실행별 scope·JUnit 산출물을 삭제하거나 덮어쓰지 않았습니다. 기존 저장소 보존 정책을 유지했습니다. 로컬 `build/ci-routing/`에도 raw run/job/artifact 메타데이터, 내려받은 산출물, 검증 로그와 세 독립 검토의 요청·응답·receipt를 보존했습니다. 독립 검토 원본 24개를 묶은 로컬 archive SHA-256은 `062623c442bf6da7cda2221bdb94096b2df2a0e2e61c3e4f89e38a46e0cd4eef`입니다. 실행 수·경로·단계 결과는 GitHub 기록으로 대조하고, 작은 정적 비교는 표로 제시했습니다.
