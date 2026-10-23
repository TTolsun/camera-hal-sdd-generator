# CI 연동 예시

**`gerrit-hook.sh`는 Gerrit change 하나마다 영향 받은 문서를 만들어 문서 저장소에 change로 올리는 예시입니다.** 커밋을 차례로 따라가는 운영(`sdd update`, `sdd automate`)은 [3단계: 문서 갱신 시스템](../docs/inhouse/03-update-system.md)을 따릅니다.

스크립트가 하는 일:

1. HAL 소스를 해당 patchset으로 체크아웃하고 `origin/<branch>`와의 merge-base를 구합니다.
2. `sdd compdb`로 compile DB를 갱신합니다.
3. `sdd run --base <merge-base>`로 영향 섹션만 다시 생성합니다.
4. 원고를 문서 저장소의 로컬 clone(`DOCS_DIR`)에 복사하고, 그 clone에서 commit해 change로 push합니다. 사람이 쓰는 페이지(`MANUAL_PAGES`)는 문서 저장소 것을 유지합니다. topic을 HAL change 번호로 맞춰 함께 리뷰되게 합니다.

환경 변수(`GERRIT_*`, `DOCS_DIR`, `DOCS_REMOTE`, `MANUAL_PAGES`, `SDD_AGENT_API_KEY`)는 스크립트 머리말에 있습니다.

전체 재생성은 빌드 구성·문서 정의·집필 규칙이 바뀔 때만 합니다. 기준을 다시 잡는 방법은 [3단계](../docs/inhouse/03-update-system.md#지켜야-할-것)에 있습니다.
