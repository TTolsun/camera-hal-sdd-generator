# 비작성자 자동 독자 시험

## 시험 조건

- 시험자는 자동 에이전트이며 사람이 아닙니다. 작성 이력, 정답표, 프로젝트 소스를 읽지 않았습니다. 공개 배포 HTML과 그 안의 발췌만 과업 근거로 사용했습니다.
- 시작 주소는 https://ttolsun.github.io/libcamera-sdd/ 입니다. 웹 도구의 open이 inaccessible로 실패하여 허용된 고정 사본 `build/issue248/public/docs/`의 HTML을 읽었습니다. 화면·브라우저 조작, 그림 확대·검색 동작은 평가하지 않았습니다.
- 지정 배포 커밋은 `f7f82444a5d93fcd49b7fd388e52e55582d4f2fa`입니다. 사본 manifest의 build_id는 `10b23c926b880b542f12e88ef22352f75b5cb7271cdb52f3bb5020eb4e0e4a93`로 일치했습니다. 루트 에이전트가 실제 Pages manifest와 사본의 바이트 동일성을 확인했다고 전달했습니다. 이 시험자는 원격 manifest를 직접 확인하지 못했습니다.
- 2026-11-04 18:41:56 UTC에 시작 주소 조회를 시작했습니다. 개별 과업 전용 타이머를 두지 않아 과업별 순수 소요 시간은 미측정입니다. 아래 시간은 도구 조회 사이의 관측 시각이며 사람의 과업 시간이나 회상 시간으로 사용할 수 없습니다. 각 과업의 10분 상한을 넘기지 않는 범위에서 진행했습니다.
- 사람의 부담·흥미·자연스러움·망각은 측정할 수 없습니다. 점수나 사람 독자 합격 판정은 만들지 않습니다.

## B1: 마지막 버퍼 완료와 요청 완료

실제 답: `completeBuffer()`는 해당 버퍼의 완료를 애플리케이션에 알리고 요청 내부의 버퍼 추적 정보를 갱신합니다. 마지막 버퍼를 완료해도 요청 완료가 자동으로 이어지지 않습니다. 파이프라인 핸들러가 `completeRequest()`를 명시적으로 호출해야 합니다. 두 호출은 파이프라인 핸들러가 CameraManager 스레드에서 수행해야 합니다. `completeRequest()`는 완료된 요청을 제출 순서로 반환하며, 호출 뒤 파이프라인 핸들러는 해당 요청에 접근해서는 안 됩니다.

근거:

- [연동 가이드: 요청을 장치에 전달하고 반환하기](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#요청을-장치에-전달하고-반환하기)
- 같은 페이지 발췌 [L551](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#source-2c79d29bf7fe6699), [L553](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#source-7b871a70bfc9aa8f), [L556](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#source-e1c3bfd748ad8a33), [L558](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#source-699c5b0f43c595cf)
- [구현 뒤 확인할 계약과 실행 한계](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#구현-뒤-확인할-계약과-실행-한계)와 [L582 발췌](https://ttolsun.github.io/libcamera-sdd/vendor-integration.html#source-72e48606b2a92dcc)

실제 경로: 시작 주소 웹 조회 실패 → 사본 index.html → 메뉴의 연동 가이드에 해당하는 vendor-integration.html → ‘요청을 장치에 전달하고 반환하기’ → ‘구현 뒤 확인할 계약과 실행 한계’. HTML을 파싱했으며 링크 클릭으로 방문한 것은 아닙니다. 이 단계에서는 발췌 앵커를 확인했지만 발췌 원문은 아직 열지 않았습니다. 답의 문장 근거는 본문에서 찾았습니다. 개별 소요 시간은 미측정이며, 18:42:55~18:43:38 UTC 사이에 답을 확보했습니다.

막힌 점과 자동 편집 의견: 본문은 마지막 버퍼와 요청 완료의 차이를 직접 설명합니다. 다만 `completeRequest()`의 호출 스레드는 뒤의 별도 절에 있어 두 절을 합쳐야 답이 완성됩니다. 이 항목에는 완료 차이를 직접 보여주는 그림이 없고 페이지의 클래스 관계 그림은 호출 순서가 아님을 명시합니다. 버퍼 완료와 명시적 요청 완료를 연결한 작은 그림 또는 두 절 사이의 직접 링크가 있으면 이 과업에 필요한 정보를 한곳에서 확인할 수 있습니다. 화면 가독성은 미평가입니다.

## B2: 전달 대상, 예약 표시, 정적 추적의 한계

실제 답: `Camera::queueRequest()`는 `PipelineHandler::queueRequest()`를 `invokeMethod()`의 메서드 인자로 전달합니다. 본문에 `ConnectionTypeQueued`가 명시되어 있습니다. 예약 표시는 인자로 넘긴 메서드 대상을 뜻하며 그 표시 하나만으로 비동기를 보증하지 않습니다. 실제 연결 방식과 동기화 계약을 확인해야 합니다. 호출 기록 번호나 화살표는 실행 순서가 아니며, 조건 분기·반복 횟수·실제 실행 스레드는 호출 목록만으로 확정할 수 없습니다. 가상 호출은 실제 객체에 따라 선택됩니다. 미해결 호출 0개, 예약 호출 1개라는 통계도 모든 실행 경로를 포괄했다는 뜻이 아닙니다.

근거:

- [큐로 전달된 요청의 준비와 실패](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#큐로-전달된-요청의-준비와-실패)
- [주요 확인 지점](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#주요-확인-지점)
- [주요 호출 관계](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#주요-호출-관계)
- [추적 범위와 경계](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#추적-범위와-경계)
- [전체 추적 기록](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#전체-추적-기록)

실제 경로: index.html의 요청 제출 메뉴를 확인 → 사본 scenarios/queue_request.html → 본문 첫 두 절 → 주요 확인 지점 → 주요 호출 관계의 설명 → 추적 범위와 경계 → 전체 추적 기록의 안내와 80번 대상 행. 일부 첫 출력이 잘려 같은 페이지를 관련 절로 다시 추출했습니다. 18:43:38 UTC에 관련 절을 모두 확인했습니다. 개별 소요 시간은 미측정입니다.

막힌 점과 자동 편집 의견: 예약 표시에 대한 한계는 본문에서 분명하게 설명합니다. ‘설계 질문과 검증 범위’에는 ‘세 문단 이내로 작성하세요’, ‘같은 결과나 반환값을 다시 풀어 쓰지 마세요’, ‘소스 한 줄마다 문단을 만들지 마세요’ 등 집필 지시가 독자에게 그대로 노출되어 있습니다. 질문보다 작성 지시가 길어 고정 과업의 위치를 찾는 데 불필요한 텍스트입니다. 독자 질문으로 바꾸고 작성 지시는 공개 본문에서 제외할 필요가 있습니다. 80개 추적 기록에 로그 호출이 많이 포함되지만 주요 확인 지점 두 행과 경계 설명으로 기본 답은 찾을 수 있습니다. 그림은 아직 렌더링하지 않아 시각적 평가는 미측정입니다.

## S: 문서를 다시 보지 않은 설명

아래 설명은 B1·B2 조회 이후 추가 HTML 조회 없이 작성했습니다. 이전 도구 결과가 대화 문맥에 남아 있으므로 인간의 무참조 기억 시험이나 망각 측정은 아닙니다.

제 말로 설명하면, 제출 함수가 성공했다는 것은 요청 검사를 지나 파이프라인에 처리할 요청을 넘겼다는 뜻입니다. 장치가 이미 프레임을 만들었거나 앱이 완료 알림을 받았다는 뜻은 아닙니다. 버퍼가 각각 완료되는 단계와 요청 전체를 완료시키는 단계가 따로 있고, 마지막 버퍼가 끝나더라도 파이프라인이 요청 완료를 명시적으로 처리해야 합니다. 그러므로 성공 반환 뒤 완료 알림이 없다면 먼저 어느 단계까지 도달했는지 확인해야 하며, 성공 반환만으로 장치 고장이나 완료 처리 누락을 단정할 수 없습니다.

이 설명을 기록한 뒤 아래에 근거 재검색 결과를 덧붙입니다.

### S의 근거 재검색 결과

사본 index.html에서 ‘지금 필요한 문서’의 ‘요청을 연동하거나 완료 지연을 진단합니다’에 연결된 request-lifecycle.html을 선택하고, ‘제출에서 완료까지’, ‘접수 반환과 완료 알림’, ‘버퍼 완료와 명시적 요청 완료의 경계’를 읽었습니다. 이어 그 페이지가 안내하는 request-diagnosis.html의 ‘실패 위치별 확인 순서’와 관련 완료 절을 읽었습니다. 18:44:54 UTC에 이 재검색을 마쳤습니다.

- [제출에서 완료까지](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#제출에서-완료까지)
- [접수 반환과 완료 알림](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#접수-반환과-완료-알림)
- [버퍼 완료와 명시적 요청 완료의 경계](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html#버퍼-완료와-명시적-요청-완료의-경계)
- [실패 위치별 확인 순서](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서)

추가로 공개 HTML 안의 발췌를 실제로 읽었습니다. queue_request.html의 [L1308 발췌](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#source-3c1e4a3c695a8890)는 `invokeMethod` 뒤의 0 반환과 별도 `requestCompleted` 알림을 확인해 줍니다. [L1373 발췌](https://ttolsun.github.io/libcamera-sdd/scenarios/queue_request.html#source-997ecce495182b6b)는 `ConnectionTypeQueued` 인자를 확인해 줍니다. B1에 열거한 L551·553·556·558·582 발췌도 이때 실제로 읽었으며 본문의 호출자·스레드 설명과 일치했습니다. 외부 전체 소스 링크는 열지 않았습니다.

제 설명의 ‘장치 고장이나 완료 처리 누락을 단정할 수 없다’는 문장은 여러 대기·취소·완료 순서 분기가 남아 있다는 문서에 근거한 조사 판단입니다. 이번 시험에서는 실제 장치나 로그를 관찰하지 않았습니다. 설명을 다시 찾는 데 막힌 이유는 없었습니다. 그림 제목·요소·범위 설명은 과업에 맞게 세분되어 있었지만 그림을 렌더링하지 않았으므로 실제 시각적 이해 효과는 미측정입니다. 용어 Pending과 fence의 설명은 장치 처리 시작 및 요청 완료와 혼동하지 않도록 범위를 밝힙니다.

## R: 조회 중단 전에 작성한 자유 메모

지금의 증상은 과업으로 주어진 ‘제출 성공 반환, 완료 알림 없음’이다. 실제 장치를 실행해 확인한 값은 아니다. 제출 함수의 0은 처리 접수와 queued 호출 예약까지를 뜻한다. 장치 전달 성공·버퍼 완료·요청 완료는 아직 확인하지 않았다. 원래 호출 위치와 요청 식별자, 반환값을 기록한 뒤 같은 요청을 따라가야 한다.

확인한 문서 단계는 접수 검사 → waitingRequests_ 준비/큐 한도 → 취소 여부와 queueRequestDevice → 개별 completeBuffer → 명시적 completeRequest → 제출 큐 선두를 통한 앱 반환이다. 다음 행동은 waitingRequests_ 존재, queuedRequests_.size()와 maxQueuedRequestsDevice_ 비교, 선두 prepared_ 관측이다. 한도에 걸리거나 준비되지 않았다면 해당 분기에서 대기 원인을 조사한다. 통과했다면 cancelled_와 queueRequestDevice의 ret를 본다. 취소면 completeRequest, 장치 ret 오류면 cancelRequest 경로를 확인한다. 장치 전달 이후에는 각 버퍼의 bufferCompleted와 completeBuffer 반환값, 마지막 버퍼 뒤의 completeRequest 호출 여부를 확인한다. 모두 완료돼도 앱 반환이 없다면 queuedRequests_ 선두의 RequestPending 여부를 본다. 소프트웨어 큐 크기를 장치에 전달된 요청 수로 단정하지 않는다.

메모의 근거는 https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#실패-위치별-확인-순서 이다. 구체 발췌는 같은 페이지의 `#source-a637b7daf9acb7ac`(선두 prepared_), `#source-0bb6ebc961be6e80`(cancelled_), `#source-1e06e477d10056b7`(장치 ret), `#source-01ad7c6605c3296a`(버퍼·요청 완료와 제출 큐 순서)이다. 후속 조사 결과는 아직 없고 실제 값은 전부 미확인이다.

이 메모를 저장한 뒤 문서 조회를 중단한다. 자동 중단은 사람의 5분 주의 중단을 재현하지 않는다. 모델 문맥의 기억도 제거되지 않는다.

### R: 조회 재개와 상태 복원

18:45:46 UTC에 메모 저장 뒤 조회 중단을 표시했고, 5초의 자동 대기를 실행했습니다. 다음 도구 호출에서 문서 대신 위 메모만 다시 읽었으며 시각은 18:46:05 UTC였습니다. 18:46:21 UTC에는 시작 주소에 대응하는 사본 index.html로 돌아가 메뉴의 ‘구성과 요청 오류 조사’ 링크를 다시 확인했습니다. 이어 request-diagnosis.html의 메모에 적은 ‘실패 위치별 확인 순서’와 네 발췌 앵커를 다시 읽었습니다. 실제 경로는 `index.html → request-diagnosis.html#실패-위치별-확인-순서 → #source-a637b7daf9acb7ac → #source-0bb6ebc961be6e80 → #source-1e06e477d10056b7 → #source-01ad7c6605c3296a`였습니다. 링크 클릭이나 브라우저 뒤로 가기 동작은 수행하지 않았습니다.

메모에서 다시 찾은 상태는 ‘접수 성공만 주어졌고 후속 실행 값은 미확인’입니다. 다음 행동은 같은 요청 식별자로 큐 한도와 선두 prepared_를 관찰하는 것입니다. 메모의 각 앵커가 남아 있어서 준비 대기, 취소/장치 오류, 버퍼 완료, 요청 반환 순서의 분기를 다시 확인했습니다. 실제 로그가 없으므로 어느 분기를 택할지는 여전히 미확인입니다. 자동 절차의 약 19초 조회 중단 구간은 사람의 5분 주의 중단이나 기억 유지 측정이 아닙니다. 재개 소요 시간도 사람의 복귀 시간으로 사용할 수 없습니다.

막힌 점과 자동 편집 의견: 저장된 URL과 관측 대상 이름을 이용하면 근거를 다시 찾을 수 있었습니다. 진단 본문은 관측할 값과 분기를 직접 안내하지만, 한 절 안에 버퍼 연결 실패와 제출 성공 뒤 진단이 함께 있어 ‘성공했지만 완료 없음’의 메모와 대응시킬 때 관련 단락을 골라야 합니다. 완료 누락을 위한 단계·관측값·미확인점·다음 분기 표가 있으면 재개에 필요한 상태를 문서 쪽에서도 보존할 수 있습니다. 이는 자동 편집 제안이며 사람의 부담을 측정한 결론은 아닙니다.

## X: 두 버퍼 중 하나만 완료된 상황

실제 답: 같은 요청의 두 버퍼 가운데 하나가 실제로 완료 처리되고 다른 하나가 아직 미완료라면, 모든 버퍼가 완료됐다고 말할 수 없습니다. 문서 계약상 `completeBuffer()`는 모든 버퍼가 완료된 경우에만 true를 반환하므로 그 시점의 결과는 false입니다. 버퍼 하나의 완료만으로 요청 완료 또는 앱의 `requestCompleted` 발생을 단정할 수 없습니다. 마지막 버퍼가 완료돼도 별도 `completeRequest()` 의무가 남습니다.

다만 ‘하나만 완료됐다’가 실제 내부 상태가 아니라 ‘bufferCompleted 콜백 하나만 관찰했다’는 뜻이라면, 그것만으로 다른 버퍼의 내부 상태까지 확정할 수 없습니다. 발췌의 구현은 `bufferCompleted.emit(request, buffer)` 다음에 내부 `completeBuffer(buffer)`를 호출합니다. 따라서 콜백을 기록한 위치와 반환값을 함께 확인해야 합니다.

추가 조사는 다음과 같습니다.

- 두 관측이 같은 요청과 올바른 버퍼 식별자에 속하는지, 다른 버퍼의 완료·취소 및 completeBuffer 반환값이 무엇인지 확인합니다.
- 모든 버퍼가 끝난 뒤 파이프라인 핸들러가 CameraManager 스레드에서 completeRequest를 호출했는지 확인합니다. 한 버퍼가 남은 원인은 장치 오류라고 단정하지 않고 처리·취소 경로를 조사합니다.
- 모든 버퍼 완료와 명시적 요청 완료를 확인했는데 앱 반환이 없다면, 제출 큐 선두가 RequestPending 상태인지 확인합니다. 앞 요청이 아직 Pending이면 뒤에서 완료된 요청의 앱 반환도 대기할 수 있습니다.

근거는 [버퍼 완료와 명시적 요청 완료의 경계](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#버퍼-완료와-명시적-요청-완료의-경계), [제출 큐의 선두 상태와 반환 순서](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#제출-큐의-선두-상태와-반환-순서), 실제로 다시 읽은 [L547~620 발췌](https://ttolsun.github.io/libcamera-sdd/request-diagnosis.html#source-01ad7c6605c3296a)입니다. 실제 경로는 R의 마지막 발췌에서 계속 답을 작성했으며 추가 페이지 이동은 없었습니다. X의 순수 소요 시간은 미측정입니다. 사례는 가정이며 실제 두 버퍼 실행을 수행하지 않았습니다. 막힌 점은 없었고, 그림의 true/false 요소와 본문이 같은 조건을 설명합니다. 렌더링이나 시각적 효과는 미평가입니다.

## 자동 편집 의견과 시험 한계

1. queue_request.html의 공개 ‘설계 질문과 검증 범위’에 긴 집필 지시가 노출됩니다. 독자가 답할 질문만 남기고 작성 지시는 제외하는 편집이 필요합니다.
2. vendor-integration.html에서는 마지막 버퍼와 요청 완료의 차이, completeRequest의 스레드 계약이 두 절에 나뉩니다. 관련 상세 링크나 완료 경계 그림을 본문에서 직접 연결하면 B1의 답을 한 경로로 모을 수 있습니다. 다른 페이지에 있는 그림 수로 이 항목의 설명을 대신하지 않았습니다.
3. 완료 누락 진단은 관측값·조건을 충분히 제공하지만, 사용자가 기록을 재개할 수 있는 짧은 상태표가 있으면 R의 메모와 문서 항목을 대조하기 쉽습니다. 현재 절에는 버퍼 등록 실패와 제출 후 완료 조사가 함께 들어 있습니다.

이 결과는 자동 에이전트가 공개 텍스트에서 근거를 찾고 적용한 기록입니다. 사람의 독해 성공, 부담 감소, 흥미, 자연스러움, 망각 또는 UI 접근성의 검증을 대신하지 않습니다. 자동 점수는 만들지 않았습니다. 도구 조회 실패와 출력 잘림, Python 출력 인코딩 오류가 있었고 관련 HTML을 다시 읽어 보완했습니다. 브라우저 동작과 공개 화면은 확인하지 못했습니다. 프로젝트 코드나 생성 원고는 변경하지 않았으며 이 결과 파일만 작성했습니다.

## 종료 시 식별 확인

사본 manifest의 종료 build_id도 `10b23c926b880b542f12e88ef22352f75b5cb7271cdb52f3bb5020eb4e0e4a93`로 일치했습니다. 18:43:38 UTC 조회 때 확보한 index.html, vendor-integration.html, scenarios/queue_request.html, request-lifecycle.html, request-diagnosis.html의 SHA-256은 종료 확인에서도 모두 같았습니다. 최초 웹 접근 시점에는 HTML에 build_id가 없어 식별하지 못했고, 사본 manifest 사용 허가를 받은 뒤 위 시각에 확인했습니다. 읽지 않은 pipeline-requests.html의 해시도 함께 확인했지만 내용 근거로 사용하지 않았습니다. 다른 build의 문서를 섞지 않았습니다. 지정 배포 커밋과 사본의 연결은 제공된 고정 조건에 의존하며 이 시험자가 Git 이력을 조회해 검증한 것은 아닙니다.
