# 현재 Pages에서 #248 독자 평가 진행하기

이 자료는 공개 Pages 빌드 `48c4f23e4b9c3246b3d365d07ddbf032944450cf5a133e3dcec1824b248055d3`에 해당합니다. 시작 전에 현재 공개 manifest의 build_id와 SHA-256을 [고정 기준](baseline.json)과 대조하세요. 평가 중 배포가 바뀌면 두 빌드의 응답을 섞지 마세요. 이 빌드를 다시 확인할 때는 공개 병합 커밋의 `docs/` 사본을 사용할 수 있습니다. [공개 manifest](https://ttolsun.github.io/libcamera-sdd/site-manifest.json) · [고정 공개 사본](https://github.com/TTolsun/libcamera-sdd/tree/be012aa897dd2562e55c842c996ef41cf45bd1a8/docs)

비작성자 3명 이상을 모집하고 신입 관점과 타팀 관점을 각각 한 명 이상 포함하세요. 각 참가자에게 [공통 안내](../final-automatic/participant-inputs/participant.md), [신입 카드](../final-automatic/participant-inputs/P01-tasks.md)·[타팀 카드](../final-automatic/participant-inputs/P02-tasks.md)·[비작성자 카드](../final-automatic/participant-inputs/P03-tasks.md) 중 배정된 카드, 자신의 빈 CSV 행, [공개 시작 URL](https://ttolsun.github.io/libcamera-sdd/)을 전달하세요. [채점 기준](../facilitator.md)과 [기본 과업 채점 기준](../rubric-163.md)은 진행자가 보관합니다. 기본 과업과 S·R·X는 [원래 절차](../protocol.md)를 적용합니다.

각 참가자는 기본 과업 두 개와 S·R·X를 수행합니다. 기본 과업은 6개 중 5개 이상 무도움 완료와 읽기 부담 역척도 중앙값 4 이상을 확인합니다. S는 참가자마다 문서를 닫은 뒤 자기 말로 설명하고 근거를 다시 찾는 과정을 관찰하세요. R은 5분간 문서를 닫고 무관한 일을 하는 동안의 중단과 시작 URL로 재진입하는 과정을 확인하세요. R의 `elapsed_seconds`에는 재진입 후 탐색 시간을 기록하고, 중단 시간은 `interruption_seconds`에 적으세요. X의 결과는 기본 과업과 별도로 기록합니다.

진행자는 각 과업 전후에 실제 `site-manifest.json`의 원본 바이트를 저장하고 CSV의 `manifest_before_path`와 `manifest_after_path`에 상대 경로를 기록하세요. 도움·중단·오답은 원래 분모에 남깁니다. 실제 읽기 부담, 흥미, 문장의 자연스러움과 이유를 받으세요. 응답 원본은 비공개 사본에 보관하고 공개에는 동의받은 익명 집계만 사용합니다. 자동 평가를 CSV에 옮기지 마세요.

저장소 루트에서 빈 [결과 양식](human-results.csv)을 검증할 수 있습니다. 현재 양식은 `pending`과 종료 코드 1을 반환합니다.

```powershell
python -m sdd.reader_study --protocol docs/libcamera/records/issue-248/current-pages/protocol.json --results docs/libcamera/records/issue-248/current-pages/human-results.csv
```
