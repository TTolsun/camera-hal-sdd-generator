# CI 연동 예시

**`gerrit-hook.sh`는 Gerrit change 하나마다 영향 받은 문서를 만들어 문서 저장소에 change로 올리는 예시입니다.** 커밋을 차례로 따라가는 운영(`sdd update`, `sdd automate`)은 [3단계: 문서 갱신 시스템](../docs/inhouse/03-update-system.md)을 따릅니다.

스크립트가 하는 일:

1. HAL 소스를 해당 patchset으로 체크아웃하고 `origin/<branch>`와의 merge-base를 구합니다.
2. `sdd compdb`로 compile DB를 갱신합니다.
3. `sdd run --base <merge-base>`로 영향 섹션만 다시 생성합니다.
4. 원고를 문서 저장소의 로컬 clone(`DOCS_DIR`)에 복사하고, 그 clone에서 commit해 change로 push합니다. 사람이 쓰는 페이지(`MANUAL_PAGES`)는 문서 저장소 것을 유지합니다. topic을 HAL change 번호로 맞춰 함께 리뷰되게 합니다.

환경 변수(`GERRIT_*`, `DOCS_DIR`, `DOCS_REMOTE`, `MANUAL_PAGES`, `SDD_AGENT_API_KEY`)는 스크립트 머리말에 있습니다.

전체 재생성은 빌드 구성·문서 정의·집필 규칙이 바뀔 때만 합니다. 기준을 다시 잡는 방법은 [3단계](../docs/inhouse/03-update-system.md#지켜야-할-것)에 있습니다.

## GitHub 검증 경로

작업 브랜치는 PR에서 검증합니다. 같은 커밋의 브랜치 push에서는 전체 CI를 중복 실행하지 않습니다. main push, 태그 push와 수동 실행은 유지합니다. 같은 PR에 새 커밋이 올라오면 이전 PR 실행을 자동 취소하며, 다른 PR·main·수동 실행은 취소하지 않습니다. 취소된 실행은 통과로 간주하지 않습니다.

| 변경과 이벤트 | 검증 |
| --- | --- |
| 일반 Markdown 문서만 바꾼 PR 또는 main push | 링크·앵커, 안내 메시지, 사내 이관 패키지, 독자 평가 자료와 경로 판정 시험 |
| 코드·설정·정책·실행 입력·알 수 없는 파일 변경 | 첫 병합 전 통합 시험과 전체 회귀 시험 |
| 태그 push·수동 실행, 불완전한 Git 이력 또는 판정 불확실 | 전체 회귀 경로 |

문서 경로는 루트 `README.md`, 이 파일, `docs/`·`docs/concepts/`·`docs/reference/`·`docs/records/`·`docs/libcamera/` 바로 아래의 일반 `.md` 파일만 허용합니다. `site.md`, `reader-quality.md`, `publication-inputs.md`는 생성·발행 정책이므로 전체 경로입니다. `AGENTS.md`, `DESIGN.md`, 집필 규칙, 프롬프트, 템플릿, 사내 안내, 예제 설정과 중첩된 실행 증거도 전체 경로입니다. 이름 변경은 삭제·추가 양쪽을 검사하며, 실행 권한·심볼릭 링크·서브모듈도 전체 경로로 보냅니다.

`ci/scope.py`는 PR에서 실제 시험할 merge commit의 양쪽 부모를 확인하고 base와 전체 merge tree를 비교합니다. 마지막 커밋이나 파일 목록 API의 일부 결과만으로 판정하지 않습니다. main push는 before와 after 전체를 비교합니다. 판정 작업 자체가 실패하면 기존 네 OS·Python 검사도 실패합니다. 문서 경로에서도 네 검사 이름을 유지하므로 경로 필터 때문에 필수 검사가 Pending으로 남지 않습니다.

각 실행은 선택한 커밋·변경 경로·판정 이유를 `ci-scope-<run>-<attempt>` 산출물에, 각 시험 결과를 `ci-tests-<os>-<python>-<run>-<attempt>` JUnit 산출물에 보존합니다. 기존 기록을 덮어쓰지 않으며 기존 저장소 보존 정책을 따릅니다. 취소 시점까지 업로드된 기록은 남고, 아직 실행하지 못한 시험은 완료했다고 보고하지 않습니다. 경량 경로는 문서의 근거 대조나 사람 승인을 대신하지 않습니다.
