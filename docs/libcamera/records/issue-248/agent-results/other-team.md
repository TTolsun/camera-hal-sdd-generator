# 타팀 관점 자동 독자 시험

이 기록은 실제 타팀 구성원의 시험이 아니라 자동 에이전트의 문서 탐색과 편집 의견이다. 사람의 부담·흥미·자연스러움·망각에 점수를 매기지 않았다. 작성 이력, 정답표, 프로젝트 소스를 읽지 않았으며 공개 배포 사본의 HTML과 그 안의 발췌만 과업 근거로 사용했다. 한국어 기록에는 fluent-korean 스킬을 적용했다.

## 환경과 식별

- 시작 주소는 <https://ttolsun.github.io/libcamera-sdd/>이다. 2026-11-04 18:41 UTC에 web 도구로 열었지만 `not accessible via this tool` 오류가 발생했다.
- 이후 허용된 `build/issue248/public/docs/`의 HTML을 텍스트로 추출했다. 화면, 브라우저 메뉴, 검색, 그림 확대 동작은 시험하지 않았다. 아래의 방문 경로는 HTML 문서/앵커 조회 순서이며 클릭 기록이 아니다.
- 지정 배포 커밋은 `f7f82444a5d93fcd49b7fd388e52e55582d4f2fa`이다. 이 에이전트가 원격 커밋을 직접 검증하지는 못했다.
- 식별용으로 별도 허용된 `site-manifest.json`에서 build_id `10b23c926b880b542f12e88ef22352f75b5cb7271cdb52f3bb5020eb4e0e4a93`를 확인했다. manifest의 엔진 해시 목록은 답변 근거로 사용하지 않았다. 식별 확인은 첫 HTML 조회 이후에 이뤄졌으므로 엄밀한 시험 시작 전 확인은 아니다.
- 18:43 UTC 이전 첫 기록에서 전체 HTML 62개의 상대 경로와 바이트를 정렬하여 합친 SHA-256은 `e249a6dc06e65f5d96f2a6693848121f0c437cfb27e269df00fde349bc01aa0e`였다.
- 과업별 사람 소요 시간은 미측정이다. 도구 호출 시각과 전체 경과 시간만 관측 가능하며, T1/T2는 같은 추출 호출에서 읽어 개별 시간을 분리하지 않았다. 각 과업의 10분 상한을 넘기지 않는 짧은 조회로 수행했다.

## T1: 공통 계층과 장치 구현

실제 답: libcamera 프레임워크는 공통 Camera API와 장치 제어의 틀을 제공한다. 커널 드라이버는 하드웨어를 직접 제어하고 V4L2 계열 저수준 인터페이스를 노출한다. 장치별 PipelineHandler는 필요한 미디어 장치를 매칭·확보하고 Camera를 생성하며 libcamera에 등록한다. 공통 계층에는 준비와 대기 큐 관리가 있지만, 마지막 버퍼가 끝난 뒤에도 장치 구현이 `completeRequest()`를 명시적으로 호출해야 한다. 애플리케이션/상위 프레임워크는 libcamera 프로젝트의 범위 밖이며, 공통 API가 있다는 사실만으로 모든 하드웨어나 기능 지원이 보장되지는 않는다. 문서는 전용/범용 지원 플랫폼과 pipelines 빌드 선택을 구분한다.

근거:

- [네 계층](https://ttolsun.github.io/libcamera-sdd/vendor-overview.html#카메라-스택의-네-계층)
- [장치별 구현의 경계](https://ttolsun.github.io/libcamera-sdd/vendor-overview.html#공통-camera와-장치별-구현의-경계)
- [지원 하드웨어와 빌드](https://ttolsun.github.io/libcamera-sdd/vendor-overview.html#지원하는-하드웨어와-빌드-선택)
- [버퍼와 요청 완료 경계](https://ttolsun.github.io/libcamera-sdd/vendor-overview.html#버퍼-완료와-명시적-요청-완료의-경계)

경로: index.html의 For Vendor 안내/메뉴 → vendor-overview.html → 네 계층 → 지원 하드웨어 → 공통 Camera 경계 → 공통 계층의 큐/완료 설명. 뒤로 돌아가지는 않았다. 답 찾기는 가능했으며 막힌 점은 화면 접근 실패다.

자동 편집 의견: 네 계층, 장치별 경계, 버퍼/요청 완료에 각각 대응하는 그림 원문과 근거 설명이 HTML에 있었다. 렌더링 품질은 미검증이다. 공통 계층의 책임을 찾는 과업에서 `prepared_`, `waitingRequests_`, `queuedRequests_` 등 내부 이름으로 급히 전환된다. 타팀 독자가 도입 판단만 할 때는 API 공통화와 장치별 의무를 먼저 한 문단으로 묶으면 세부 큐 설명을 선택해서 읽기 쉽겠다. 플랫폼 목록은 확인 가능하지만 개별 센서·화질·성능 지원 보장으로 확대해서 읽어서는 안 된다.

## T2: 내장 벤치마크 범위

실제 답: DebayerCpu 내장 벤치마크에 포함되는 것은 통계 수집과 디베이어링의 처리 시간이다. 프레임을 캡처하는 시간과 출력하는 시간은 제외된다. Software ISP를 쓰는 파이프라인에서 cam 또는 qcam으로 사용할 수 있다. 이 측정만으로 전체 캡처부터 출력까지의 성능을 주장할 수 없다.

근거: [성능 근거를 읽는 기준](https://ttolsun.github.io/libcamera-sdd/vendor-assurance.html#성능-근거를-읽는-기준), [같은 페이지의 공식 문서 발췌](https://ttolsun.github.io/libcamera-sdd/vendor-assurance.html#source-551d2b5944a36d19).

경로: vendor-overview.html 조회 이후 index.html에서 확인한 메뉴의 vendor-assurance.html → 성능 근거를 읽는 기준 → 해당 발췌. 첫 원시 HTML 추출이 너무 길어 출력이 잘렸고 인코딩도 깨졌다. UTF-8로 다시 추출하여 본문을 읽었으며 이는 문서 자체의 인코딩 결함이라는 증거가 아니다. 개별 소요 시간은 미측정이다.

자동 편집 의견: 포함/제외가 짧은 문장에 직접 적혀 있어 답을 찾을 수 있었다. 이 짧은 범위 설명에는 추가 그림이 필수라고 판단하지 않았다. `DebayerCpu`와 디베이어링은 낯선 타팀 독자에게 용어 확인이 필요할 수 있으나, 벤치마크 범위를 찾는 데에는 방해되지 않았다. 측정값이나 실제 실행 결과가 이 절에 있는 것처럼 읽지는 않았다.

## S: 성공 반환과 완료의 차이

18:43 UTC에 request-lifecycle.html과 request-diagnosis.html을 읽었다. 다음 문장은 그 이후 문서 조회를 추가로 하지 않은 상태에서 적은 자기 말 설명이다. 앞서 받은 텍스트가 에이전트의 문맥에 남아 있으므로 사람의 무자료 회상 성과로 해석할 수 없다.

성공 반환은 그 요청이 비동기 전달 경로에 접수되었다는 뜻이다. 카메라가 이미 촬영을 끝냈다는 뜻은 아니다. 그 뒤 준비 상태와 큐 제한을 통과하여 장치 처리로 가야 하며, 버퍼별 완료 이후에도 파이프라인 구현이 요청 완료를 따로 알려야 한다. 애플리케이션에는 별도의 완료 신호가 온다. 따라서 제출 함수가 0을 반환했는데 신호가 없다는 관측만으로 장치 고장이나 완료 콜백 누락 원인을 확정할 수 없다.

근거 재조회: 자기 말 설명을 기록한 뒤 index.html의 메뉴에서 다시 [요청 처리와 문제 진단](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#제출에서-완료까지)을 찾았다. [Camera::queueRequest 발췌](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#source-28d007de6ad1a8a5)에서 queued 호출 직후 `return 0;`과 별도 requestCompleted 계약을 확인했다. [ConnectionTypeQueued 발췌](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#source-0470759dc8387e9a)에서는 메시지 게시 경로와 Blocking 경로의 대기가 구분됐다. 외부 소스를 열지 않았다.

경로: index.html → request-lifecycle.html → request-diagnosis.html로 첫 설명을 읽었다. 자기 말 기록 후 index.html로 돌아감 → request-lifecycle.html의 제출에서 완료까지 → 같은 페이지 발췌 두 곳을 재조회했다. 도구로 읽기 시작한 18:43:08 UTC 이전부터 근거 재조회 완료 18:45:30 UTC까지 약 2분 22초 이내였으나 R 메모와 다른 작업을 포함하므로 S 순수 소요 시간은 미측정이다. 막힌 점은 브라우저 접근 실패와 사람 회상 측정 불가다.

자동 편집 의견: 접수/완료 차이는 첫 문장에서 찾을 수 있었다. 이후 같은 절에 여러 단계의 그림 원문이 연속으로 배치되어 있다. 각각 답하는 질문은 있지만 타팀 독자는 먼저 비동기 접수와 최종 알림을 구분한 뒤 조사 단계로 들어가는 짧은 연결이 있으면 우선순위를 정하기 쉽겠다. `queueRequest`와 `queueRequestDevice`, `bufferCompleted`와 `requestCompleted`를 혼동하지 않도록 함수의 소속과 알림 단위를 함께 읽어야 했다. 그림의 화면 가독성은 평가하지 않았다.

## R: 조회 중단 전 자유 메모

18:44 UTC 무렵에 작성한 메모이다. 실제 장치나 애플리케이션은 실행하지 않았으며 관측값은 과업이 준 `queueRequest 성공 반환 / 완료 알림 없음`뿐이다. 이하 항목은 실제 확인한 실행 결과가 아니라 문서에서 확인한 조사 단계이다.

현재 상태: 정상 접수와 완료가 다르다는 지점까지 확인했다. 아직 requestCompleted를 못 봤다. 먼저 원래 제출 반환값 0과 요청 식별을 보존한다. index → For Developer → 요청 처리와 문제 진단에서 비동기 접수와 requestCompleted를 다시 찾을 수 있다. 원인 조사는 구성과 요청 오류 조사 → 실패 위치별 확인 순서에서 이어간다.

다음 확인: waitingRequests_가 남는지, queuedRequests_.size()가 maxQueuedRequestsDevice_와 같은지, 선두 prepared_가 거짓인지 본다. 통과하면 cancelled_와 queueRequestDevice의 ret를 본다. 다음은 completeBuffer의 버퍼별 알림과 반환값, completeRequest의 명시 호출이다. 완료된 뒤에도 반환이 없으면 큐 선두의 RequestPending 때문에 뒤 요청이 막히는지 본다.

미확인점: 실제 요청 ID, 준비 여부, 큐 크기, 장치 전달 성공 여부, 버퍼 수와 완료 수, 취소 여부, completeRequest 호출 여부, 앞선 요청의 상태, 실제 신호 연결/실행 스레드는 모두 모른다. 가상 프로브의 콜백 관측은 이 상황의 실행 결과가 아니다. 다음 분기는 실행에서 처음 관측되지 않는 단계에 따라 고른다. 버퍼만 끝났다고 요청까지 끝났다고 쓰지 않는다.

근거 메모: request-lifecycle.html의 `제출에서-완료까지`, request-diagnosis.html의 `실패-위치별-확인-순서`. 버퍼 둘 중 하나만 끝난 경우는 completeBuffer가 모든 버퍼 완료 여부를 반환한다는 절에서 확인한다.

## R: 중단 후 재탐색

자유 메모를 파일에 쓴 시각은 18:44:24 UTC이다. 그 뒤 문서 조회를 멈추고 자기 메모만 다시 읽었으며 18:44:52 UTC에 index.html을 재조회했다. 중단은 약 28초이고 독립적인 방해 과업도 없었다. **자동 에이전트의 이 중단은 사람의 5분 주의 중단을 재현하지 않는다.** 기존 문서 텍스트가 문맥에 남아 있어 자기 메모만으로 재개했다는 절차를 사람의 망각·회복 측정으로 해석할 수 없다.

재개한 상태 설명: 제출은 성공했지만 완료 경로의 어느 단계까지 갔는지 모른다. 다음 행동은 진단 문서에서 큐 한도와 선두 준비 상태를 확인하는 조사 지점을 다시 찾는 것이다. 메모에 적은 이름으로 index.html의 `구성과 요청 오류 조사` 링크를 찾고 [실패 위치별 확인 순서](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서)를 조회했다. 이후 본문에서 큐 비교, 선두 prepared_, cancelled_, 장치 제출 ret, completeBuffer, completeRequest와 선두 RequestPending 분기를 다시 찾았다.

경로: 자기 메모 → index.html → request-diagnosis.html#실패-위치별-확인-순서 → 같은 절의 버퍼 완료 문장 → [페이지 안 발췌](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#source-01ad7c6605c3296a). 되돌아간 주소는 index.html이다. 메모 재읽기 18:44:40 UTC부터 근거 발췌 확인 18:45:30 UTC까지 약 50초의 도구 경과 시간이지만 S와 X 근거 확인도 포함한다. R 단독 소요 시간은 미측정이다.

찾은 조사 위치를 실제 관측값으로 바꾸지 않았다. 현재 관측은 여전히 주어진 성공 반환과 알림 부재뿐이며, 진단 실행은 하지 않았다. 막힌 이유는 실행 환경 부재와 화면 접근 실패다.

자동 편집 의견: URL/앵커와 다음 관측식을 함께 적은 메모에서는 조사 위치를 재발견할 수 있었다. 이는 문서의 재탐색 가능성을 부분적으로 보여 주지만 사람의 기억 부담을 증명하지 않는다. 한 절 안에 여러 조사 단계를 긴 문장으로 담고 있으므로 실제 조사 중단 시 독자가 `관측값 / 미확인 / 다음 분기`를 별도로 남길 수 있는 짧은 예가 있으면 도움이 되겠다. 요청 하나의 완료 문제와 앞선 요청이 반환을 막는 문제는 별도 그림 질문으로 나뉘어 있어 논리적 구분은 확인했다. 화면상 배치의 효과는 미검증이다.

## X: 버퍼 둘 중 하나만 완료된 경우

실제 답: 두 버퍼 중 정확히 하나만 완료되었고 다른 하나는 아직 완료되지 않았다는 상태가 확인됐다면 요청의 모든 버퍼가 완료됐다고 말할 수 없다. completeBuffer의 반환 계약상 그 상태에서는 모든 버퍼 완료를 뜻하는 true가 성립하지 않는다. 하나의 버퍼 완료는 요청 완료와 별개의 사건이다. 두 버퍼가 모두 끝나더라도 요청은 자동 완료되지 않고 completeRequest를 별도로 호출해야 한다.

관측이 단지 `버퍼 완료 알림을 하나만 봤다`는 수준이라면 두 번째 버퍼의 실제 미완료까지 단정하지 않는다. 두 알림이 같은 요청에 속하는지, 두 번째 버퍼의 추적 상태와 알림 관측 여부를 추가로 확인해야 한다. 두 번째가 실제 미완료이면 그 처리/취소 경로를 조사하고, 모두 완료되었다면 completeRequest 명시 호출 여부를 조사한다. 그 호출이 있어도 애플리케이션으로 돌아오지 않았다면 제출 큐 선두가 RequestPending으로 남아 뒤 요청 반환을 막는지 확인한다. 이 조건만으로 장치 고장, 스레드 문제, 콜백 연결 문제를 확정할 수 없다.

근거: [버퍼 완료와 명시적 요청 완료의 경계](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#버퍼-완료와-명시적-요청-완료의-경계), [completeBuffer/completeRequest의 페이지 내 발췌](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#source-01ad7c6605c3296a), [제출 큐의 선두 상태와 반환 순서](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#제출-큐의-선두-상태와-반환-순서).

경로: R에서 다시 찾은 request-diagnosis.html → 버퍼 완료 설명 → 페이지 내부 발췌 → 선두 상태 설명. 새로운 외부 문서나 전체 소스는 열지 않았다. 별도의 시간은 미측정이며 R/S 근거 재조회에 포함된다. 막힌 점은 실제 상태를 관측하지 못했다는 것이다.

자동 편집 의견: 버퍼 완료와 요청 완료의 구분, 그리고 앞선 요청 때문에 반환이 대기할 수 있다는 구분을 본문과 발췌로 확인할 수 있었다. `completeBuffer true`도 최종 애플리케이션 완료와 같지 않다는 경계를 계속 유지해야 했다. 해당 질문에 대응하는 그림 원문이 있지만 그림 자체가 이 구분을 화면에서 얼마나 잘 전달하는지는 확인하지 못했다.

## 종료 확인과 범위

18:45:49 UTC에 manifest build_id를 다시 확인했으며 지정값과 같았다. 전체 HTML 62개의 합성 SHA-256도 첫 기록의 `e249a6dc06e65f5d96f2a6693848121f0c437cfb27e269df00fde349bc01aa0e`와 같았다. 기록한 구간에서는 사본 변경이 검출되지 않았다. 원격 Pages의 build_id 전후 확인은 이 에이전트의 웹 접근 실패로 직접 수행하지 못했으며 루트 에이전트의 별도 검증과 구분한다.

전체 도구 시험 창은 18:41:14~18:45:49 UTC로 약 4분 35초였다. 최종 기록 작성 시간은 이 창에 포함되지 않는다. 자동 답 찾기와 근거 재탐색은 수행했으나 실제 타팀 독자 시험, 사람의 5분 중단, 브라우저 탐색·그림 확대·검색 시험은 완료했다고 주장하지 않는다. 코드나 공개 산출물은 변경하지 않았다.
