# 사내 반입본 작업 기준

이 파일은 반입 ZIP의 루트 AGENTS.md로 배치됩니다.

- 질문별 시각화는 config/visuals.yaml의 generation: llm 계획과 실제 design_topics 근거를 연결합니다. 승인된 사내 LLM으로 초안을 생성하고 근거·조건·본문 검사를 통과한 결과만 원고에 배치합니다. 소스 변경 후 generate --from-impact 또는 update로 다시 생성합니다. 반입본에서도 tools/evaluate_visuals.py로 허용된 모델의 실제 호출·두 커밋 재생성 기록을 남기며 테스트 대역을 실제 모델 시험으로 보고하지 않습니다.

- START_HERE.md와 docs/inhouse/package.md에서 시작하고 skills/camera-hal-sdd/SKILL.md를 적용합니다.
- 최종 대상은 사용자가 지정한 사내 Camera HAL입니다. 실제 제품 구성과 소스 검증 전에는 사내 적용 완료라고 하지 않습니다.
- 생성기와 사내 소스·설정·facts·원고·프롬프트·로그는 별도 위치에서 관리합니다. 사내 입력과 파생물을 공개 서비스나 저장소로 보내지 않습니다.
- 이 반입본에는 Git 원격이 없습니다. docs/libcamera/와 examples/libcamera/는 공개 시험 참고 자료입니다. 그 안의 공개 동기화·PR·GitHub Pages 배포·예약 지시를 사내 작업에 적용하지 않습니다.
- 설치된 에이전트와 생성기의 LLM 연결은 별개입니다. 두 실행 환경 모두 사내 소스를 처리하도록 허용되었는지 확인합니다. 사내 모델·코드 링크·자산·게시 대상은 실제 정책과 설정으로 정합니다.
- 생성기의 기본 모델 실행 경로는 Hermes CLI입니다. 사용자가 선택하면 `agent.runner`를 `opencode` 또는 `claude`로 바꿔 독립 실행합니다. 모델·제공자는 선택한 CLI 설정 또는 실행별 `model`·`args`를 사용합니다. CLI 누락·실패를 다른 CLI나 Ollama 직접 호출로 대체하지 않습니다. `docs/inhouse/cli-agents.md`의 실행·검증 구분을 따릅니다.
- 생성 Markdown·HTML을 직접 수정하지 않습니다. 계약은 설정에서, 표시 기능은 생성기에서 고쳐 다시 생성합니다. CLI와 impact.json schema 1을 유지합니다.
- facts·원고의 커밋 불일치, 노드 한도, 필수 질문·근거 해시 관문을 우회하지 않습니다. 자동 검사는 사람 승인이 아닙니다.
- 같은 설정을 동시에 실행하지 않으며 실패 상태·직전 정상 결과·승인 장부를 보존합니다. 복구는 docs/inhouse/troubleshooting.md를 따릅니다.
- 독자는 For Vendor(기술 채택·연동·구현 담당자)와 For Developer(신입·타팀 개발자)입니다. 제품 개요(vendor-overview), 연동 가이드(vendor), 지원 범위와 검증(vendor-assurance)을 나누고 주장마다 실제 근거를 연결합니다. docs/concepts/reader-quality.md의 첫 코드 탐색·요청 흐름·수정·디버깅 과제를 적용합니다.
- 메뉴는 독자 → 수행할 작업 → 문서 순서입니다. 두 독자 그룹은 group으로 유지하고 작업 소분류는 sections.yaml의 nav_section으로 지정합니다. 새 설정은 사내 템플릿을 따르고 기존 설정은 실제 문서 목적에 맞게 이전합니다. 수정 후 generate·export-site·verify-site로 재생성·검증하며 특정 공개 사이트의 HTML을 복사하지 않습니다.
- DESIGN.md와 style/README.md의 읽기·집필 계약을 따릅니다. 설정부터 계약 작성·검증까지 수행하고 handoff.md에 실제 완료·미완료와 재개 조건을 기록합니다.
- 게시·예약 설치는 사용자가 허용한 사내 대상과 범위에서만 수행합니다. 대상이 없으면 검증된 로컬 초안과 남은 게시 단계를 전달합니다.
