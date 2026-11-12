# 사내 반입본 작업 기준

이 파일은 반입 ZIP의 루트 AGENTS.md로 배치됩니다.

- 질문별 시각화는 config/visuals.yaml의 generation: llm 계획과 실제 design_topics 근거를 연결합니다. 승인된 사내 LLM으로 초안을 생성하고 근거·조건·본문 검사를 통과한 결과만 원고에 배치합니다. 소스 변경 후 generate --from-impact 또는 update로 다시 생성합니다. 반입본에서도 tools/evaluate_visuals.py로 허용된 모델의 실제 호출·두 커밋 재생성 기록을 남기며 테스트 대역을 실제 모델 시험으로 보고하지 않습니다.

- START_HERE.md와 docs/inhouse/package.md에서 시작하고 skills/camera-hal-sdd/SKILL.md를 적용합니다.
- 설치·수정 전에 `python tools/verify_import.py`로 반입 무결성을 검사하고 source_commit을 기록합니다. START_PROMPT.txt와 START_PROMPT_HERMES.txt는 같은 안내에서 생성된 사본입니다. 선택한 CLI에 맞는 사본을 사용하며 다른 버전의 스킬·안내를 혼합하지 않습니다.
- 최종 대상은 사용자가 지정한 사내 Camera HAL입니다. 실제 제품 구성과 소스 검증 전에는 사내 적용 완료라고 하지 않습니다.
- 생성기와 사내 소스·설정·facts·원고·프롬프트·로그는 별도 위치에서 관리합니다. 사내 입력과 파생물을 공개 서비스나 저장소로 보내지 않습니다.
- 이 반입본에는 Git 원격이 없습니다. docs/libcamera/와 examples/libcamera/는 공개 시험 참고 자료입니다. 그 안의 공개 동기화·PR·GitHub Pages 배포·예약 지시를 사내 작업에 적용하지 않습니다.
- 설치된 에이전트와 생성기의 LLM 연결은 별개입니다. 두 실행 환경 모두 사내 소스를 처리하도록 허용되었는지 확인합니다. 사내 모델·코드 링크·자산·게시 대상은 실제 정책과 설정으로 정합니다.
- 생성기는 사용자가 선택한 CLI를 독립 실행합니다. `agent.kind: cli`와 `agent.runner`로 `hermes`, `opencode`, `claude`, `codex`를 선택합니다. 기존 사내 설정을 유지하며 새 환경의 승인된 실행기가 미정이면 호출 전에 확인합니다. 공개 기본 프로필을 사내에 강제하지 않습니다. 실행기를 바꿀 때는 `command`·`model`·`args`도 함께 교체합니다. 모델·제공자·추론 강도·인증은 선택한 CLI 설정 또는 명시적인 실행별 설정을 사용하고, 별도 검토는 사내에서 승인한 설정으로 실행합니다. CLI 누락·실패를 다른 CLI·직접 API·저장 응답·수동 원고로 대체해 성공으로 보고하지 않습니다. `docs/inhouse/cli-agents.md`의 선택·검증 절차를 따릅니다.
- 생성 Markdown·HTML을 직접 수정하지 않습니다. 계약은 설정에서, 표시 기능은 생성기에서 고쳐 다시 생성합니다. CLI와 impact.json schema 1을 유지합니다.
- facts·원고의 커밋 불일치, 노드 한도, 필수 질문·근거 해시 관문을 우회하지 않습니다. 자동 검사는 사람 승인이 아닙니다.
- 같은 설정을 동시에 실행하지 않으며 실패 상태·직전 정상 결과·승인 장부를 보존합니다. 복구는 docs/inhouse/troubleshooting.md를 따릅니다.
- 독자는 For Vendor(기술 채택·연동·구현 담당자)와 For Developer(신입·타팀 개발자)입니다. 제품 개요(vendor-overview), 연동 가이드(vendor), 지원 범위와 검증(vendor-assurance)을 나누고 주장마다 실제 근거를 연결합니다. docs/concepts/reader-quality.md의 첫 코드 탐색·요청 흐름·수정·디버깅 과제를 적용합니다.
- 메뉴는 독자 → 수행할 작업 → 문서 순서입니다. 두 독자 그룹은 group으로 유지하고 작업 소분류는 sections.yaml의 nav_section으로 지정합니다. 새 설정은 사내 템플릿을 따르고 기존 설정은 실제 문서 목적에 맞게 이전합니다. 수정 후 generate·export-site·verify-site로 재생성·검증하며 특정 공개 사이트의 HTML을 복사하지 않습니다.
- DESIGN.md와 style/README.md의 읽기·집필 계약을 따릅니다. 설정부터 계약 작성·검증까지 수행하고 handoff.md에 실제 완료·미완료와 재개 조건을 기록합니다.
- 독립 질문별로 그림의 필요성을 검토하고 그림 ID 또는 구체적인 생략 사유, 실제 검토한 소스 창과 미검토 범위를 기록합니다. docs/reference/visual-audit.md의 원고·최종 사이트 검사 경계를 유지하며 공개 검토 장부로 사내 항목을 승인하지 않습니다.
- 장시간 작업은 docs/concepts/site.md의 watch-progress 절차를 따릅니다. 사내 진행 장부에 기준 커밋·build_id·항목별 판정·남은 발행 단계·재개 명령을 보존하며 입력이 바뀐 항목은 다시 검토합니다. 완료 또는 명시적 중단 시 해당 실행의 종료 표식을 남깁니다.
- 게시·예약 설치는 사용자가 허용한 사내 대상과 범위에서만 수행합니다. 대상이 없으면 검증된 로컬 초안과 남은 게시 단계를 전달합니다.
