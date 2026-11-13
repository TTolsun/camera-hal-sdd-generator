# #248의 현재 Pages 확인과 독자 평가 자료

2026년 11월 14일에 공개 Pages build `48c4f23e4b9c3246b3d365d07ddbf032944450cf5a133e3dcec1824b248055d3`에서 #248의 남은 문서·탐색 항목을 확인했습니다. 새 [진행자 안내](../libcamera/records/issue-248/current-pages/instructions.md)와 [빈 결과 양식](../libcamera/records/issue-248/current-pages/human-results.csv)은 이 빌드에 고정했습니다. 실제 사람 응답은 0명·0과업이며 #248은 기존 ‘계획 없음’ 상태입니다. [이슈 #248](https://github.com/TTolsun/camera-hal-sdd-generator/issues/248)

## 재사용한 근거와 추가 확인

- **기본 여섯 경로.** 현재 manifest가 #163 확인 때와 바이트 단위로 일치합니다. 홈, 벤더 개요·검증·연동, 시스템 개요, 요청 제출 시나리오의 한영·두 화면 폭 검사 24건을 재사용했습니다. 그 검사에는 홈의 읽기 순서, 연동의 완료 스레드 근거, 시나리오의 예약 대상과 추적 한계, 전체 그림 식별자 검색이 포함됩니다. [#163의 고정 기본 과업](../libcamera/records/goal-162-163/reader-protocol.md) · [현재 manifest](https://ttolsun.github.io/libcamera-sdd/site-manifest.json)
- **기존 자동 독해.** 첫 세 역할 시험은 기본 6/6, 자기 설명 S 2/3, 복귀 R 1/3, 새 조건 X 3/3이었습니다. 별도의 후속 시험에서는 S와 R이 각각 기준에 부합했습니다. 후속 원본 묶음의 파일 해시 712개를 확인했습니다. 첫 시험의 미충족과 후속 시험의 분모는 원래 기록에 남아 있습니다. [첫 시험](../libcamera/records/issue-248/failure-repair/README.md) · [후속 S·R 판정](https://github.com/TTolsun/libcamera-sdd/blob/06a62a4309e04c79d101f2cb2ddcdde4dd291297/publication/issue248/failure-repair/focused-summary.json)
- **현재 빌드에 적용할 범위.** 후속 시험이 사용한 여덟 절을 공개 PR #103과 현재 배포본의 한영 16개 절에서 비교했습니다. 복귀 메모가 있는 진단 절의 본문·링크·그림은 양쪽 언어에서 일치했습니다. `camera.cpp`, `request.cpp`, `pipeline_handler.cpp`의 Git 파일 바이트도 같습니다. 나머지 일곱 절에서는 설명, 링크 또는 그림이 바뀌었으므로 원래 판정을 당시 빌드에 귀속했습니다. 현재 빌드에서 수행한 #297의 독립 읽기 Q1·Q2는 접수와 완료의 차이, 버퍼와 요청 완료의 구분, 완료 누락의 조사 위치와 분기를 뒷받침합니다. 해당 절의 시각화는 같은 빌드에 연결된 #215의 감사 판정을 재사용했습니다. #248의 중단 관측과 실제 독자의 응답은 별도로 측정해야 합니다. [이전 절 대조](https://github.com/TTolsun/libcamera-sdd/blob/06a62a4309e04c79d101f2cb2ddcdde4dd291297/publication/issue248/failure-repair/reader-section-equivalence.json) · [현재 빌드의 #297 독립 읽기](../libcamera/records/issue297/split-reader.md) · [시각화 판정](issue215.md)
- **현재 Pages 복귀 경로.** 한영 1280px·390px Chrome에서 홈에서 요청 수명 문서를 거쳐 진단 메모와 준비 대기 절로 이동했습니다. 메모의 제보·관측·해석과 임시 가정·미확인·다음 분기·근거 위치 항목 여섯 개, 접수·버퍼 완료·요청 완료 절, `camera.cpp:1308`과 `pipeline_handler.cpp:547`의 발췌와 고정 원문 링크를 확인했습니다. 그림 렌더링과 가로 넘침도 확인했습니다. 이 점검에서 문서를 수정할 결함은 확인되지 않았습니다. [요청 수명](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#제출에서-완료까지) · [조사 메모](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서)

## 발행과 실제 사람 평가 상태

생성기 #285와 공개 SDD #103으로 완료 책임 연결·조사 메모가 반영됐습니다. 현재 실제 Pages의 manifest SHA-256 `c67448d2360d59a6e861c6f80ff62089d9acf8d6b2014e3bdd376e2c682c4055`가 공개 병합 사본과 일치합니다. 같은 manifest에 기록된 산출물 487개의 #163 실측 해시를 재사용했습니다. 이번 변경은 생성기 저장소의 평가 자료와 검증 기록에 해당하므로 현재 Pages 배포를 확인했습니다. [생성기 PR #285](https://github.com/TTolsun/camera-hal-sdd-generator/pull/285) · [공개 SDD PR #103](https://github.com/TTolsun/libcamera-sdd/pull/103) · [현재 Pages 배포](https://github.com/TTolsun/libcamera-sdd/actions/runs/43296145459)

현재 양식의 15개 행은 기본 과업 6개와 S·R·X 각 3개를 배정하며, 응답과 점수는 모두 비어 있습니다. `sdd.reader_study`가 `pending`을 반환하는 것을 확인했습니다. 무도움 성공 수, 부담 점수 중앙값, 실제 자기 설명·복귀·새 조건 적용, 흥미와 자연스러움 및 응답 이유는 미측정입니다. [현재 프로토콜](../libcamera/records/issue-248/current-pages/protocol.json) · [평가 자료 사용법](../libcamera/records/issue-248/current-pages/instructions.md)
