# libcamera 설계 문서

Linux 카메라마다 장치 제어 방식이 다릅니다. libcamera는 공통 API를 제공해 앱이 같은 방식으로 촬영을 요청할 수 있게 하고, 장치별 제어는 Pipeline Handler에 맡깁니다. 이 문서는 연동과 코드 수정에 필요한 계약을 해당 커밋의 소스로 연결합니다.

## 어디서 시작할까요?

<div class="reader-start">
<section>
<h3 id="for-vendor">For Vendor</h3>
<a href="#vendor가-먼저-확인할-내용">우리 장치에서 무엇을 검증해야 하는가?</a>
</section>
<section>
<h3 id="for-developer">For Developer</h3>
<a href="#처음-읽는-개발자의-순서">취소 상태를 어느 코드에서 확인하는가?</a>
</section>
</div>

<!-- sdd:overview-visual -->

## 장치에서 확인할 항목 {#vendor가-먼저-확인할-내용}

대상 장치에서 정상 촬영과 미완료 요청이 있는 상태에서의 정지를 각각 시험하세요. 제출 회차별로 완료 콜백 횟수, 요청 상태, 각 버퍼의 상태를 기록해 취소와 성공한 프레임을 구분하는지 확인하세요. [정지 뒤 완료 알림의 계약과 근거](request-lifecycle.md#정지와-연결-해제를-구분하기)를 확인하세요.

[공통 API의 도입 이점](vendor-overview.md#장치-구현자가-공통-계층에서-얻는-것)과 [하드웨어·빌드 조건](vendor-overview.md#지원하는-하드웨어와-빌드-선택)을 대조한 뒤 [연동 가이드](vendor-integration.md)에서 장치별 구현 책임을 확인하세요. [지원 범위와 검증](vendor-assurance.md)은 고객 보드의 첫 촬영, 구성 제약과 성능 근거를 다룹니다.

## 취소 상태를 확인할 코드 {#처음-읽는-개발자의-순서}

앱에서 `Camera::requestCompleted`에 연결한 콜백을 열고 `Request::status()`를 읽어 `RequestCancelled`를 처리하는 분기를 찾으세요. 영상을 사용하기 전에 각 `FrameBuffer::metadata().status`가 `FrameSuccess`인지 확인하세요. [정지 뒤 완료 알림의 상태 판정과 코드](request-lifecycle.md#정지와-연결-해제를-구분하기)를 따라가세요.

[시스템 개요](overview.md#탐색과-파이프라인-선택)에서 CameraManager의 탐색 진입점과 각 구성 요소의 역할을 확인할 수 있습니다. 콜백이나 요청 처리 코드를 수정하기 전에는 [요청 제출과 완료](overview.md#요청-제출과-완료), [세션 상태와 자원](overview.md#캡처-세션의-상태와-자원), [스레드 경계](overview.md#스레드-경계와-동기화)를 확인하세요.

## 지금 필요한 문서

| 하려는 일 | 시작할 문서 |
|---|---|
| 이 프로젝트가 무엇을 받아 무엇을 내놓는지 이해합니다. | [이 프로젝트가 하는 일](team-overview.md) |
| 카메라를 직접 실행해 보고 설계 이유를 읽습니다. | [실행해 보고 설계 이유 읽기](onboarding.md) |
| 구성 실패의 원인을 좁힙니다. | [구성 실패를 좁히는 순서](request-diagnosis.md#구성-실패를-좁히는-순서) |
| 파이프라인의 구성·완료·정지를 구현합니다. | [Pipeline Handler](pipeline-handler.md) |
| 모듈 선택과 알고리즘 인터페이스를 수정합니다. | [IPA 관리와 구현 진입점](ipa.md) |
| 객체 수명과 상태 전이를 확인합니다. | [카메라와 요청 모델](camera-model.md) |

## 기준 설명 찾기

요청·버퍼의 소유권과 재사용 규칙은 **[요청 객체와 버퍼 수명](camera-requests.md)**, 장치 큐와 완료 순서의 구현 규칙은 **[Pipeline 요청 제출과 완료](pipeline-requests.md)**에서 관리합니다. 진단 문서는 이 계약을 연결하여 증상별 확인 순서를 안내합니다.

알고리즘을 따라가려면 [IPU3 LSC의 설정과 프레임 처리](ipu3-lsc-flow.md)를 여세요. 카메라별 튜닝과 커널 지원 조건은 [RKISP1 카메라별 왜곡 보정](rkisp1-dewarp.md)에서 확인합니다.

## 문서를 읽는 방법

절 전체 근거에서 **발췌**를 누르면 문서 안에서 원문이 펼쳐집니다. **전체 소스**를 누르면 분석한 커밋의 파일과 줄로 이동합니다. 용어는 [용어집](glossary.md)에서 확인하세요.

그림을 누르면 확대와 요소 검색을 사용할 수 있습니다. 관계 그림과 정적 호출 추적은 실제 실행 순서를 보장하지 않습니다. 전체 클래스는 [구성 요소 색인](component-index.md), 주요 호출과 추적 경계는 [핵심 시나리오](scenarios/index.md)에 있습니다.

??? note "검증 범위와 문서 상태"
    "자동 검사 통과"는 인용한 코드 위치와 문장 형식을 기계로 확인했다는 뜻이며, 사람의 내용 승인이 아닙니다. 문서 상단에 검토 상태를, 아래 생성 근거에 분석 커밋과 자동 검사 결과를 표시합니다. 코드 발췌와 대조한 설명도 내용이 맞는지 사람이 검토해야 합니다.

    이 사이트는 공개 libcamera의 정적 분석 결과입니다. 실제 기기의 촬영·성능·오류 복구와 사내 HAL은 검증하지 않았습니다. 설계 선택의 이유와 성능 예산은 코드에 근거가 있을 때만 설명할 수 있습니다.

    [모델 비교 기록](https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/docs/libcamera/records/model-comparison.md)의 4B·9B 초안은 내용 오류가 남아 채택하지 않았습니다.

??? note "생성과 배포"
    [생성기](https://github.com/TTolsun/camera-hal-sdd-generator)가 추출·검증·화면 구성을 담당하고, [공개 문서 저장소](https://github.com/TTolsun/libcamera-sdd)가 공개 입력의 이력과 산출물을 보관합니다. 공개 환경에는 정기 예약을 설치하지 않습니다.

    원래 라이브러리 사용법은 [libcamera 공식 문서](https://docs.libcamera.org/master/)에서 확인하세요.
