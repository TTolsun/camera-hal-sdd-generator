# 공개 libcamera 항목별 시각화 확인

`generation-profile.yaml`과 `independent-review-profile.yaml`은 독립 Codex CLI의 `gpt-6.1-terra`와 `high`를 사용합니다. 검토 실행은 생성·번역과 별도 영수증으로 기록합니다. 개별 항목의 입력 지문과 현재 소스가 일치할 때 이전 판정을 재사용합니다.

`official-cam-visuals.yaml`에는 기존 가상 캡처 문서에 적용할 그림 세 개의 변경만 있습니다. 기존 `official-cam-validation` 설정에서 `initial-submission`을 같은 ID의 정의로 교체하고 `observed-kernel-boundaries`와 `virtual-dmabuf-attachment`를 해당 질문에 추가합니다. 공개 실행 기록과 나머지 그림은 원래 소스와 영수증을 유지합니다.

시각화 검사는 [항목별 시각화 검사](../../../../docs/reference/visual-audit.md)의 절차를 따릅니다. 공개 사이트 발행에는 최종 조립된 한영 항목의 검토 장부와 이전 공개 항목 보존 기준을 함께 사용합니다.
