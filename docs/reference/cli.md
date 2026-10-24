# sdd 명령 참조

**모든 명령은 생성기 저장소 루트에서 `uv run sdd --config <설정>/sdd.yaml <명령>`으로 실행합니다.** 아래 표에서는 앞부분을 줄여 `sdd <명령>`으로 적습니다. 옵션 전체는 `sdd <명령> --help`로 봅니다.

## 설치된 가상 환경에서 실행

보조 Python 스크립트에서 설정·facts·원고를 읽거나 쓸 때는 `encoding='utf-8'`을 지정합니다. Windows의 기본 코드 페이지로 UTF-8 파일을 읽지 않습니다.

`uv`를 쓰지 않는 환경에서는 설치된 가상 환경의 `sdd` 실행 파일을 사용합니다. 실행 파일을 PATH에 추가하지 않았다면 같은 환경의 Python으로 CLI 모듈을 실행할 수 있습니다.

```bash
<가상환경의 Python> -m sdd.cli --config <설정>/sdd.yaml doctor
```

`python -m sdd`는 지원하지 않습니다. CLI를 별도 스크립트에서 호출해야 한다면 `from sdd.cli import main` 뒤에 `raise SystemExit(main())`으로 반환값을 종료 코드에 전달합니다. `main()`만 호출하면 검사 실패를 프로세스의 성공 코드 0으로 잘못 기록할 수 있습니다. 실행 도우미를 만들었다면 성공 명령뿐 아니라 의도적으로 실패하는 검사도 실행해 0이 아닌 종료 코드가 전달되는지 확인하세요.

## 자주 쓰는 명령

| 명령 | 하는 일 | 종료 코드 |
|---|---|---|
| `sdd doctor` | 도구·compile DB·모델 연결을 점검합니다. | 0 정상, 1 문제 있음 |
| `sdd extract` | compile DB로 `facts.json`을 만듭니다. 파싱 오류나 진입점 누락이 있으면 기존 facts를 지키고 멈춥니다. | 0, 실패 시 1 |
| `sdd generate` | 원고를 만듭니다. `--sections a,b`로 일부만, `--from-impact`로 영향 받은 섹션만 만듭니다. | 0, `--from-impact`인데 `impact.json`이 없으면 2 |
| `sdd export-site` / `sdd verify-site` | 정적 사이트를 만들고, 링크와 산출물 해시를 검사합니다. | 0, 실패 시 1 |
| `sdd update --to <ref>` | 기준 커밋 이후 커밋을 하나씩 갱신합니다. [종료 코드 표](#update-종료-코드)를 봅니다. | 0·1·2·3 |
| `sdd accept` | 사람 검토 승인을 장부에 기록합니다. 인자 없이 실행하면 상태만 봅니다. | 0 |
| `sdd automate` | 예약 갱신·Hermes 검토·게시·배포 확인을 재개 가능한 작업으로 실행합니다. `--cron`은 crontab 항목만 출력합니다. | 0, 실패 시 0이 아닌 값 |

## 그 밖의 명령

| 명령 | 하는 일 |
|---|---|
| `sdd compdb` | compile DB를 확보합니다. `--normalize --normalize-input <원본> --clang <clang> --out <파일>`로 다른 빌드 시스템의 DB를 정규화합니다. |
| `sdd impact --base <ref> --base-facts <파일>` | 두 커밋의 영향 섹션과 범위 검토 항목을 계산합니다. `--fail-on-coverage-gap`이면 미결 항목이 있을 때 2로 끝납니다. |
| `sdd run --base <ref>` | extract → impact → generate를 한 번에 합니다. `update`와 달리 커밋을 하나씩 나누지 않습니다. |
| `sdd audit-docs` | 문서 분량·증가·중복·Feature 범위를 검사합니다. 문제가 있으면 2. |
| `sdd improve` | 새 커밋이 없을 때 기존 문서의 누락 한 항목을 점검·보완합니다. 보류되면 2. |
| `sdd verify-publication --url <주소> --site <로컬 사이트>` | 실제 게시 URL의 manifest와 산출물 해시가 로컬 사이트와 같을 때까지 확인합니다. `--site`를 생략하면 `SDD_SITE_DIR`을 씁니다(`sdd automate`가 설정합니다). 예: `sdd verify-publication --url https://docs.internal/hal/ --site build/site --timeout 600`. |
| `sdd fetch-mermaid` | Mermaid 배포본을 사내·오프라인 자산으로 준비합니다. `--tarball`로 반입한 파일을 씁니다. |
| `sdd export-html` | 문서 전체를 HTML 파일 하나로 만듭니다. |

## update 종료 코드

| 코드 | 뜻 | 다음 행동 |
|---|---|---|
| 0 | 새 커밋을 모두 처리했습니다. | 사이트를 만들고 게시합니다. |
| 1 | 한 커밋의 처리가 실패했습니다. 완료로 기록하지 않습니다. | 원인을 고치고 같은 명령을 다시 실행합니다. 같은 커밋부터 재시도합니다. |
| 2 | 승인되지 않은 범위 검토 항목이 있습니다. | [사람이 할 일](../inhouse/04-review.md#범위-검토-항목-종료-코드-2)을 따릅니다. |
| 3 | `needs-review` 원고가 있습니다. | [사람이 할 일](../inhouse/04-review.md#needs-review-원고-종료-코드-3)을 따릅니다. |

## build에 생기는 파일

설정 디렉터리의 `build/`와 `sdd_dir`에 생깁니다. 이 중 **굵게 표시한 파일은 실행 사이에 지워서는 안 되는 상태**입니다.

| 파일 | 내용 |
|---|---|
| **`build/facts/facts.json`** | 추출한 사실. `meta.source_commit`이 기준 커밋입니다. |
| **`build/update-state.json`** | 마지막으로 처리한 커밋과 실패 기록. |
| `build/facts-<SHA>.json` | 처리 중인 커밋의 비교 기준 사본. 성공하면 지워집니다. |
| `build/impact.json`, `build/impact-review.md` | 영향 섹션, 범위 검토 항목, 자동 분류, LLM 판정. |
| **`build/coverage-triage.json`** | LLM 판정 기록. 사람 승인이 아닙니다. |
| `build/design-review.json` | 설계 질문별 `documented`·`limited`·`missing` 상태. |
| **`build/document-baseline.json`**, `build/document-health.{json,md}` | 문서 분량 검사의 비교 기준과 결과. |
| `build/compdb/compile_commands.json` | ndk-build 원본 DB를 정규화한 사본. |
| `build/prompts/` | 모델에 보낸 프롬프트와 응답. |
| `build/site/` | 정적 사이트. |
| **`build/automation-state.json`**, `build/hermes/`, `build/idle-review*` | `sdd automate`의 게시 단계·Hermes·누락 보완 기록. |
| **`<sdd_dir>/approvals.json`** | 사람 승인 장부. 원고와 함께 버전 관리합니다. |

다음 단계: 처음 적용한다면 [준비물](../inhouse/01-prepare.md)부터 읽습니다.
