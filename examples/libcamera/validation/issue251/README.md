# #251 공개 준비 시험의 원본

**이 디렉터리는 공개 mini HAL의 시험 기록입니다. 실제 사내 제품의 입력이나 결과가 없습니다.** [판정·실패·미검증 범위](../../../../docs/inhouse/records/issue251-public.md)를 먼저 읽으세요.

`runs/mini-hal/`은 지정 Codex CLI의 실제 원고·그림 생성과 공개 소스 두 커밋의 산출물을 보관합니다. `initial-render-check-failure/`는 최초 시험 도구 실패, `independent-review*`는 별도 검토의 원본 입력·응답·영수증, `cli-failure-retry/`는 CLI 실패·재개·반복 진단입니다. 원래 실행 경로와 시각을 유지하며 생성·검토·사람 승인 상태를 합치지 않습니다.

`runs/issue251-extra.py`와 `runs/issue251-repeat.py`는 당시 작업 공간 경로를 사용하는 공개 시험 스크립트입니다. 보관 자료를 운영 설정으로 실행하지 않습니다. 새 재현은 생성기의 `tools/evaluate_visuals.py`를 새 출력 경로에서 실행하고 별도 검토 설정을 사용하세요. 원본 영수증은 `project/build/prompts/calls/`와 검토 폴더의 `prompts/calls/`에서 확인합니다. 상대 stdout 경로를 유지하도록 대응 `cli/` 기록도 함께 보관했습니다.

사내 자료는 이 디렉터리에 추가하지 않습니다. 다음 단계는 [사내 파일럿 안내](../../../../docs/inhouse/pilot.md)입니다.
