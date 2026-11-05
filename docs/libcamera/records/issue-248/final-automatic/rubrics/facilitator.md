# 근거와 필수 의미를 대조하세요

참가자에게 과업 전에 이 파일을 주지 마세요. 기본 여섯 과업은 [#163 채점 기준의 고정 사본](rubric-163.md)을 그대로 사용합니다. 다음 주소는 고정 `baseline.json`의 배포 사본에서 확인했습니다. 답의 문구가 같을 필요는 없으며 주체·조건·시점과 근거가 맞아야 합니다.

| 추가 과업 | 필수 의미 | 기준 근거 |
|---|---|---|
| S | API 성공 반환은 입력 검사 후 호출 예약/접수의 결과이며 장치 처리 성공·요청 완료의 증명이 아닙니다. 별도 requestCompleted를 확인하며 버퍼 완료와 요청 전체 완료도 구분해야 합니다. | [접수 반환과 완료 알림](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#접수-반환과-완료-알림), [queueRequest 발췌](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#source-28d007de6ad1a8a5), [버퍼/요청 완료](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#버퍼-완료와-명시적-요청-완료의-경계) |
| R | 주어진 사실은 제출 성공/완료 미통지뿐입니다. 실행 관측과 조사 계획을 구분하고, 자신의 중단 전 상태·미확인값을 복원해야 합니다. 동일 요청 식별자로 실제 함수·값을 관찰하는 다음 행동과 조건별 다음 분기를 근거와 함께 찾아야 합니다. 대기/준비·장치 전달·완료·반환 순서 중 자신의 조사 상태에 맞는 분기를 찾으면 되며 모든 내부 함수를 암기할 필요는 없습니다. | [진단 순서](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서), [준비·전달](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#선두-요청을-전달하거나-반복을-멈추는-조건), [제출 큐 선두](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#제출-큐의-선두-상태와-반환-순서) |
| X | 하나의 완료 관측으로 다른 버퍼 상태·요청 완료·영상 성공을 단정하면 안 됩니다. 둘째 버퍼가 실제 미완료라면 모든 버퍼 완료 조건이 충족되지 않습니다. 모든 버퍼가 끝나도 명시적 completeRequest가 필요합니다. 같은 요청·버퍼의 상태/관측 위치, 요청 완료와 반환 조건을 추가로 확인해야 합니다. | [완료 발췌](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#source-01ad7c6605c3296a), [버퍼/요청 완료](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#버퍼-완료와-명시적-요청-완료의-경계) |

S는 문서를 실제로 닫은 뒤 자기 말로 설명했는지 관찰하세요. R은 5분 중단과 시작 주소 재진입을 관찰하고 메모 원문·전후 경로를 남기세요. 자동 에이전트의 문맥 유지나 짧은 도구 조회 중단은 사람의 조건을 충족하지 않습니다. 도움을 주면 도움 유무를 반드시 기록하며 실패·미응답을 삭제하지 않습니다.

채점자는 `correct`를 직접 판정합니다. 집계 도구는 의미 채점이나 사람 여부 인증을 수행하지 않습니다. 입력 선언의 진실성, 실제 시간·URL·메모, 비작성 여부는 진행자가 확인해야 합니다. 사람 평가 결과는 승인 장부와 별개입니다. 참여자별 과업 전후에 실제 사이트의 `site-manifest.json`을 원본 바이트로 저장하고, 결과 CSV를 기준으로 한 상대 경로를 `manifest_before_path`와 `manifest_after_path`에 적으세요. 도구는 캡처 파일의 SHA-256과 build_id가 고정 기준과 같은지 검사합니다. 캡처가 실제 평가 당시 해당 URL에서 수집됐는지는 진행자가 확인합니다.

빈 양식의 기본 열은 #163과 같습니다. `source_kind=human`에는 실제 사람만 기록하세요. 예/아니오는 `true`/`false`, 1~5점은 정수로 적습니다. 미측정 값은 비워 두고 이유를 기록합니다. 단계별 추가 과업도 각각 별도 행을 사용합니다. 원본은 비공개 사본에 작성하고 공개 동의 전에는 저장소에 커밋하지 않습니다.

다음 명령은 빈 양식에서 `pending`과 종료 코드 1을 반환해야 합니다. 사람 결과가 없다는 뜻이며 구현 실패가 아닙니다. 에이전트·혼합 build_id·다른 프로토콜·중복 배정 행은 오류로 거절합니다. 같은 기준의 후보 평가는 별도 프로토콜 사본에 후보 build_id와 기준본 연결을 먼저 고정하고 새 양식으로 시작하세요. 원래 기록을 덮어쓰지 마세요.

```powershell
python -m sdd.reader_study --protocol docs/libcamera/records/issue-248/protocol.json --results docs/libcamera/records/issue-248/human-results.csv
```

기본 과업의 부담·흥미·자연스러움을 별도로 집계하고 원문 이유를 비공개 보관하세요. 추가 X는 전이 과제로 따로 보고하며 같은 과업의 학습 효과와 구분합니다. 관측된 실패를 보완한 뒤 같은 성공 조건으로 재평가하세요.
