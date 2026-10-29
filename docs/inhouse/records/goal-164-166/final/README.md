# 최종 범위·표시 보완 증거

공개 libcamera 시험 자료만 포함합니다. 실제 사내 제품 검증과 실제 사람의 과업 수행 결과는 포함하지 않습니다. 앞선 실패 기록은 [이전 기록](../followup/README.md)에 그대로 남아 있습니다.

## 고객 가치와 계층 역할의 중복

생성기 [PR #180](https://github.com/TTolsun/camera-hal-sdd-generator/pull/180)은 정의·이점 질문과 네 계층의 역할 질문이 같은 이점을 반복하지 않도록 공개 예제의 질문 범위를 정리했습니다. 필수 C++ API·언어 바인딩·V4L2·adaptation·프로젝트 밖 애플리케이션 경계는 유지했습니다. 검증 정책 해시나 검증기를 완화하지 않았습니다.

`value-scope-cli.zip`에는 source `212c689fcf2450bbfbaab25c7472895ac277b5d6`의 독립적인 전후 모델 검토 각 1회, 실제 생성·근거 대조 2회와 원본 요청·응답·영수증·입력·원고가 있습니다. 전후 같은 검토 질문은 `avoidable-duplicate`에서 `distinct-required`로 바뀌었습니다. 이것은 실제 사람 평가가 아닙니다. 실제 선택 CLI는 Codex CLI `gpt-6.1-terra`, `-c model_reasoning_effort="high"`입니다.

전체 28개 원고를 복사한 독립 시험 공간에서 `generate --sections vendor-overview`는 정상 종료와 전체 문서 건강 검사를 통과했습니다. 새 호출 2회·49.998초였고 vendor-overview 한 파일만 바뀌었습니다. 기존 vendor 단위 11개는 진짜 영수증을 재검증해 재사용했습니다. 공유 배포 공간에는 쓰지 않았으며, 이후 공개 생성 배치가 같은 질문 변경을 적용했습니다. ZIP의 각 항목 해시와 원본 크기는 `archive-index.json`에 있습니다.

`fictional-current-revalidation.json`은 앞서 생성한 명시적인 가상 A/B 시험 원고와 원본 CLI 영수증 4개를 현재 코드로 다시 검사한 결과입니다. 신규 생성 호출은 0회이며, A의 제공 확인과 B의 미확인, 양쪽의 측정 미확인을 구별합니다. 실제 제품 지원 주장으로 사용하지 않습니다.

## 절 끝의 근거와 읽기 흐름

생성기 [PR #182](https://github.com/TTolsun/camera-hal-sdd-generator/pull/182)은 H3–H6 소제목 앞에 근거 목록을 끼우지 않고 부모 H2 절 끝에서 합칩니다. 병합 커밋은 `970cb1f9d6ddedcf6981195bbb03d26c915f0778`입니다. Ubuntu·Windows / Python 3.11·3.14의 필수 CI와 로컬 471개 검사가 통과했습니다. 리뷰 스레드는 0개이며 Sourcery는 할당량 때문에 실행되지 않았으므로 독립 자동 코드 리뷰 통과라고 하지 않습니다.

`render-only-h2/proof.json`은 과거 e117 원고·번역의 렌더링 분리 시험입니다. 문서 생성·렌더링 모델 호출 0회, 원고 해시 불변, 번역 누락 0, 한영 HTML 60개와 내부 링크 오류 0입니다. 필요한 안내 번역 한 항목은 이미 공개된 PR #58의 동일 문자열을 출처와 함께 재사용했습니다. 준비 중 역사적 CLI 경로와 writer identity 때문에 두 번 중단됐고 실제 모델은 실행되지 않았습니다. 그 실패를 새 번역 성공으로 계산하지 않습니다.

`render-only-h2/h2-preservation-proof.json`은 같은 원고·facts·번역에서 PR #182의 렌더러 전후만 비교합니다. 60페이지의 모든 소스 목적지·앵커·코드 블록 해시와 문단 감사 대응 386개가 유지됐습니다. 과거 공개 #55와 직접 비교한 별도 시도는 중간의 reading_cleanup이 클래스 색인 링크 3개를 바꿔 실패했습니다. 이 실패를 보존 통과로 바꾸지 않았으며 비교 경계를 명시했습니다.

`browser/h2-layout.json`은 실제 브라우저의 한영 × 1440px/390px 제품 개요 검사입니다. 문단 근거 0개, 절 목록 5개, 가로 넘침 0, 첫 H3 앞 요소는 설명 문단입니다. 키보드 Enter로 절 목록이 열리고 Space로 닫히며 초점은 summary에 남았습니다. `before-reading-flow.jpg`는 과거 공개 #55의 같은 e117 페이지이고 `h2-reading-flow.jpg`는 렌더링 후입니다. 두 화면의 뷰포트와 중간 공통 UI 변경은 동일하지 않으므로 픽셀 단위 비교라고 주장하지 않습니다.

`browser/print-user-confirmation.json`은 공개 #57 한영 페이지의 실제 Chrome 인쇄 미리보기에서 문단 행 없음·절 근거 남음을 사용자가 직접 확인한 기록입니다. 에이전트가 인쇄 UI를 조작하거나 스크린샷으로 확인했다는 뜻은 아닙니다. #163의 내용 독자 시험과 구분합니다.

## 공개 통합 배포

공개 [PR #56](https://github.com/TTolsun/libcamera-sdd/pull/56)의 source212 통합 배포와 실제 공개 산출물 검사는 진행 중입니다. 이 기록의 사적 e117 렌더링을 source212 공개 배포 완료로 대체하지 않습니다. 최종 URL·build_id와 이슈별 완료 대조는 배포 후 기록합니다.
