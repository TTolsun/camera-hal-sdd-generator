# 공개 libcamera 검증 문서

**사내 운영에는 이 폴더가 필요하지 않습니다.** 공개 libcamera로 생성기를 검증하고 [게시 사이트](https://ttolsun.github.io/libcamera-sdd/)를 갱신하는 절차와 그 기록입니다.

## 절차

| 문서 | 내용 |
|---|---|
| [작업과 함께 공개 문서 갱신하기](workflow.md) | upstream 동기화, 누락 보완, 동반 배포 절차 |
| [가정용 검증 환경](home-lab.md) | 환경 구성과 두 커밋 검증 방법 |
| [WSL 실행 기록](wsl-run.md) | 실제 WSL 빌드·추출·배포 기록 |

## 검증 기록

기록은 그 날짜의 결과입니다. 이후 동작은 현재 코드와 [개념 문서](../README.md)를 기준으로 봅니다.

| 기록 | 주제 |
|---|---|
| [두 커밋 변경 반영](records/revision-validation.md) | 2026-09-21 A/B 커밋 부분 통과 |
| [범위 검사](records/coverage-validation.md) | 2026-09-21 범위 누락 검출 |
| [설계 근거 재검증](records/design-validation.md) | 설계 내용 보강과 증분 생성 |
| [IPU3 LSC 보강](records/lsc-followup.md) | LSC 문서와 남은 범위 |
| [요청 처리 가이드](records/request-guide-validation.md) | 요청 제출·완료·정지 문서 |
| [카메라 모델 문서 검토](records/camera-model-review.md) | 문서 충분성 판정 |
| [생성 모델 비교](records/model-comparison.md) | 4B·9B 같은 입력 비교 |
| [생성기 품질 개선](records/generator-quality-validation.md) | 2026-09-26 재생성 |
| [문서 수명주기](records/document-lifecycle-validation.md) | 증가·중복·Feature 검사 연결 |
