# Gerrit 예제의 Markdown 게시

`ci/gerrit-hook.sh`는 선택한 에이전트 CLI로 생성을 마친 뒤 별도 docs clone의 `sdd/`에 Markdown을 게시합니다. 이 절차는 로컬 Git 저장소로 검증한 예제입니다. 실제 사내 HAL·Gerrit의 인증, `commit-msg` 훅과 리뷰 정책은 해당 환경에서 확인해야 합니다.

`DOCS_DIR`에는 HEAD 커밋이 있는 전용 clone의 루트를 지정하고 `DOCS_REMOTE`에는 docs 프로젝트 주소를 지정합니다. 같은 clone을 여러 작업이 동시에 사용하지 않도록 CI에서 직렬화하세요. 생성기 저장소나 HAL 소스를 docs 프로젝트로 push하지 않습니다.

해시는 파일 바이트를 비교합니다. CI clone은 줄바꿈을 자동 변환하지 않도록 구성하세요. Windows에서는 checkout 전에 `git config core.autocrlf false`를 설정하거나 저장소의 `.gitattributes`로 Markdown과 Mermaid의 LF 줄바꿈을 고정합니다.

수동 문서의 원본은 docs clone입니다. 설정의 `kind: manual`, `kind: index`에 지정한 출력 경로와 `index.md`를 보호합니다. 중첩 경로도 같은 규칙을 적용하며, 기존 파일은 생성 결과로 덮어쓰지 않습니다. docs clone에 아직 없는 수동 문서만 생성 디렉터리의 초기 파일로 채웁니다. `MANUAL_PAGES`를 생략하면 설정에서 목록을 계산합니다. 지정했다면 공백으로 구분한 경로 목록이 계산된 목록과 정확히 같아야 합니다. 공백이 있는 경로는 목록 안에서 따옴표로 감싸세요. 목록이 다르면 게시를 중단합니다.

`markdown-publication-manifest.json`은 이 게시기가 관리하는 `.md`와 `.mmd` 파일의 SHA-256을 기록합니다. 수동 문서와 `.gitkeep`은 관리 산출물에서 제외합니다. HTML 사이트의 `site-manifest.json`은 다른 형식이며, 이 절차의 소유권 근거가 될 수 없습니다. HTML 산출물이나 알 수 없는 생성 파일이 입력에 있으면 중단합니다.

`approvals.lock`은 실행 중 잠금 파일이므로 게시 입력에서 제외합니다. `approvals.json`은 docs clone의 기존 원본을 보존하며, 해당 파일이 없을 때만 입력 ledger의 바이트를 그대로 복사합니다. 이 파일은 생성 산출물 소유권 목록에 포함하지 않습니다. 게시기가 승인 상태를 만들거나 갱신하지 않으며, 근거 해시가 오래되었는지는 기존 승인 verifier가 판정합니다. 다른 JSON 입력은 계속 거부합니다.

반영 전에 생성 경로·이전 해시·Git 상태를 확인하고, 기존 문서와 생성 파일을 임시 디렉터리에 모두 복사합니다. 복사나 검증이 실패하면 기존 게시 디렉터리를 유지합니다. 반영이나 staging이 실패하면 이전 디렉터리로 되돌립니다. 복구 이름 변경도 실패했다면 오류에 표시한 `sdd-markdown-*/previous`를 남기므로, 그 사본을 보존하고 수동으로 복구하세요. 강제 종료·전원 손실까지 원자적으로 복구하는 저장 기능은 아닙니다.

이전 manifest가 소유한 파일만 삭제할 수 있습니다. manifest 해시와 다른 파일, 사라진 관리 파일, symlink·junction, 경로 이탈은 실패로 처리합니다. `sdd/`의 로컬 수정과 저장소 전체의 기존 staged 변경도 거부합니다. 게시 밖의 unstaged·untracked 파일은 보존하며 commit에 포함하지 않습니다. commit 직전에 staged 경로를 다시 검사하고, 실제 변경 경로만 명시하여 commit합니다. 변경이 없으면 commit과 push를 생략합니다.

최초 이전 시 기존 파일의 소유권을 추정하지 않습니다. manifest가 없는 경로의 기존 파일은 새 생성 파일과 바이트가 같을 때만 관리 대상으로 등록합니다. 내용이 다르면 기존 문서를 별도로 보관한 뒤 리뷰를 거쳐 생성 결과와 조정하고, 그 변경을 먼저 commit하세요. 파일을 지우거나 덮어쓰는 강제 이전 옵션은 없습니다. 수동 문서는 이 비교 대상에서 제외합니다.

push가 실패하면 새 로컬 commit을 남기고 실패를 보고합니다. 다음 실행에서 변경이 없다는 이유로 push 성공을 보고하지 않습니다. 해당 docs clone의 commit과 Gerrit change 상태를 확인한 뒤 같은 ref로 push를 재시도하세요. 정상 로그의 `unchanged; no commit or push`는 원격 게시 확인을 뜻하지 않습니다.

로컬 검증은 다음 명령으로 실행합니다. 이 검증은 임시 Git 저장소와 bare remote를 사용하며 실제 Gerrit 검증을 대신하지 않습니다.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_markdown_publication.py -q --basetemp build/test-gerrit
```
