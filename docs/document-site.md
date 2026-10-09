# 설계 문서 사이트 구성

**문서 생성과 디자인 기술은 `camera-hal-sdd-generator`에서 관리하고, 출력만 문서 저장소에 배포합니다.**

`sdd export-site`는 기존 Markdown과 facts를 읽어 여러 페이지로 구성된 정적 사이트를 만듭니다. LLM을 다시 호출하지 않으며 원본 Markdown, 자동 인용 검사 결과, 생성 시각을 변경하지 않습니다.

`documentation.enabled: true`이면 [문서 수명주기 검사](document-lifecycle.md)를 먼저 수행합니다. 분량·중복·Feature 범위·폐기 계획에 문제가 있으면 기존 사이트를 보존한 채 중단합니다. 폐기 원고는 메뉴·검색에서 제외하며 기존 링크는 다시 검증합니다.

사람의 승인은 `sdd accept`가 원고 옆의 장부(`sdd/approvals.json`)에 기록합니다. 사이트는 각 페이지에 승인 상태(승인·승인 이후 본문 변경·사람 검토 전)를 표시하고, `site.require_approval: true`를 두면 승인되지 않은 문서가 있을 때 게시를 중단합니다. 승인은 본문 해시에 붙으므로 본문이 바뀌면 자동으로 재검토 대상이 되고, 근거 재검증만 거친 이월(본문 동일)에서는 유지됩니다.

```yaml
site:
  require_approval: true    # 미승인·본문 변경 문서가 있으면 export-site 를 중단한다
```

유지보수 기준은 [DESIGN.md](../DESIGN.md)입니다. 그림 생성은 `src/sdd/diagrams.py`, 페이지 배치는 `src/sdd/export_site.py`, 출력 검증·관리는 `src/sdd/site_build.py`, 공통 화면 자산은 `src/sdd/site_assets/`에서 관리합니다. 변경을 생성기에 반영하면 다음 빌드부터 모든 페이지에 적용됩니다.

## 반복 실행 계약

libcamera 설정은 `site.enabled: true`이므로 `sdd generate`와 `sdd run`이 문서와 Mermaid 원문을 만든 뒤 사이트 빌드·검증까지 이어서 수행합니다. 다른 프로젝트도 같은 옵션으로 연결합니다.

```powershell
# 현재 facts에서 문장과 Mermaid를 다시 생성하고 사이트까지 만듭니다.
uv run sdd --config examples/libcamera/sdd.yaml generate
# 문장은 유지하고 그림·화면·검색 목록만 최신 facts와 공통 규칙으로 다시 만듭니다.
uv run sdd --config examples/libcamera/sdd.yaml export-site
uv run sdd --config examples/libcamera/sdd.yaml verify-site
```

`site-manifest.json`에는 입력 facts·Markdown·섹션 설정과 생성 코드·출력 파일의 SHA-256을 남깁니다. 같은 입력으로 사이트를 두 번 만들면 같은 결과와 build ID가 나옵니다. 문장을 새로 생성하는 LLM 호출 자체의 결정성을 뜻하지 않습니다.

빌드는 먼저 임시 위치에서 내부 링크를 확인합니다. 검증 실패 시 기존 사이트에 반영하지 않습니다. 다음 빌드에서 사라진 페이지·그림은 직전 manifest에 기록된 생성 파일만 정리합니다. 사람이 수정한 생성 파일은 덮어쓰지 않고 오류를 냅니다. 원고나 공통 테마에서 수정한 뒤 다시 생성하세요.

새 출력 경로에 manifest가 관리하지 않는 파일이 이미 있거나, 필요한 디렉터리 자리에 파일이 있으면 반영 전에 중단합니다. 기존 사이트를 처음 가져올 때에도 해당 파일을 별도로 보존하고 빈 출력 디렉터리에서 빌드하세요.

설계 근거 검사가 활성화된 페이지의 이월에는 인용뿐 아니라 선택한 구조·주제·발췌의 지문도 같아야 합니다. 근거가 달라지면 재생성이 필요합니다. [설계 근거 검사](design-evidence.md)의 자동 검사 통과는 사람의 의미 검토나 실행 검증을 뜻하지 않습니다.

`design_requirements`가 있는 페이지는 필수 질문별 설명·근거 연결도 검사합니다. `generate`는 선택된 섹션을 사전 검사하고 실패하면 원고를 덮어쓰지 않습니다. `export-site`에서도 다시 검사하므로 불완전한 계약을 현재 입력 지문만 맞춰 게시할 수 없습니다. `show_evidence`를 켜면 설명 아래에서 발췌 원문과 해시를 펼쳐 대조할 수 있습니다. 설정 예시는 [필수 설계 항목 검사](design-evidence.md#필수-설계-항목-검사)를 참고하세요.

사이트는 현재 facts와 원고의 커밋이 같아야 합니다. 새 커밋에서 일부 원고만 갱신해 나머지 원고가 이전 커밋에 남으면 게시를 중단합니다. `generate --from-impact`는 영향이 없던 원고의 `파일:줄` 인용을 새 facts로 재검증한 뒤 통과한 원고의 `source_commit`을 이월하므로(`carryover.py`, frontmatter에 `revalidated_from` 기록), 통상적인 증분 실행에서는 전체 재생성 없이 기준이 맞습니다. 인용이 어긋난 원고는 이월하지 않고 재생성 대상으로 보고하며, 그때는 해당 섹션을 다시 생성해야 게시할 수 있습니다.

Git push는 생성 명령에 포함하지 않습니다. 검증된 출력 디렉터리를 `libcamera-sdd/docs`로 지정해 만들고 해당 저장소에서 커밋·push하면 기존 Pages가 게시합니다. 생성기 CI는 push/PR마다 Windows·Linux, Python 3.11·3.14에서 회귀 검사를 실행하도록 구성했습니다. 원격 CI 통과 여부는 실제 실행 결과로 확인해야 합니다.

## 공개 libcamera SDD 동반 배포

사용자는 이 프로젝트의 변경 작업마다 공개 libcamera SDD도 함께 갱신하도록 상시 지시했습니다. 아래 절차는 에이전트의 작업 완료 기준이며, 필요한 공개 배포를 다시 요청받을 때까지 미루지 않습니다. 명시적으로 배포를 보류하라는 후속 지시가 있으면 그 지시를 따릅니다.

1. 생성기 변경을 리뷰하고 필요한 테스트와 CI를 확인한 뒤 PR을 main에 병합합니다.
2. 공개 libcamera의 분석 기준 커밋과 사용한 생성기 커밋을 고정합니다. 추출 동작이 바뀌면 facts를 다시 추출하고, 원고 내용·근거·집필 규칙이 바뀌면 원고도 재생성합니다. CSS 등 표시만 바뀌면 기존 원고를 검증하여 사이트를 다시 빌드할 수 있습니다. facts를 재사용한 경우에는 재추출했다고 기록하지 않습니다.
3. `TTolsun/libcamera-sdd`의 기존 변경사항과 지침을 확인합니다. 분석용 체크아웃을 보존하고 배포 작업본의 `docs/`에 생성기로 출력합니다. HTML과 배포용 CSS를 직접 수정하지 않습니다. CSS 원본은 `src/sdd/site_assets/reading.css`이며 `docs/assets/reading.css`는 그 복사본입니다.
4. 내부 링크·manifest 해시·반복 빌드를 검사합니다. 화면 변경은 데스크톱·모바일에서 확인하고, README·사이트 안내·`run.json`의 생성기 커밋과 검증 범위를 실제 결과에 맞춥니다. 공개 입력과 산출물만 포함하며 사람의 내용 승인 상태를 자동으로 바꾸지 않습니다.
5. 문서 저장소에 PR을 만들고 검증 후 main에 병합합니다. GitHub Pages 배포가 성공할 때까지 확인한 뒤, [공개 사이트](https://ttolsun.github.io/libcamera-sdd/)의 manifest와 HTML·CSS 해시를 해당 생성 결과와 대조합니다. 저장소와 Pages 설정은 배포 시점의 실제 구성을 확인합니다.
6. 완료 보고에는 생성기와 문서 저장소의 PR, 공개 URL과 배포 확인 결과를 남깁니다. 지침·테스트만 바뀌어 공개 산출물에 차이가 없으면 불필요한 배포 커밋을 만들지 않고 그 결과를 알립니다. 실패하거나 권한이 부족하면 원인과 미완료 단계를 명시하고 기존 공개 사이트를 보존합니다.

## 디자인 기준

[libcamera 공식 문서](https://docs.libcamera.org/master/)의 좌측 탐색 메뉴·중앙 본문·우측 목차를 참고했습니다. OMM 저장소의 `DESIGN.md`, `docs/design.md`, `assets/reading.css`, `templates/jekyll/_layouts/default.html`에서 읽기 중심 배치와 다이어그램 상호작용 규칙을 적용했습니다. 참고한 로컬 OMM 기준 커밋은 `12a704c603136308b87b26c4081bd6102d42395e`입니다.

별도의 Mermaid 이름을 가진 `SKILL.md`는 해당 저장소에서 찾지 못했습니다. 실제로 적용한 것은 위 디자인 문서와 템플릿의 규칙입니다. OMM 실행기를 설치하거나 OMM 저장소를 수정하지 않았습니다.

본문 너비는 최대 720px이며 글자 크기는 16px, 줄 간격은 1.8입니다. 흰 배경에 짙은 녹색을 제한적으로 사용합니다. 좁은 화면에서는 메뉴를 접고 목차를 본문 위에 표시합니다. 외부 글꼴은 내려받지 않습니다.

목차 페이지에 딸린 하위 문서는 왼쪽 메뉴에서 접었다 펼 수 있습니다. 읽고 있는 가지만 펴 두고 나머지는 접어서 목록을 짧게 유지합니다. `details`/`summary` 로 만들었으므로 스크립트 없이도 동작합니다.

데스크톱 메뉴는 `scrollbar-gutter: stable`로 스크롤바 자리를 미리 확보합니다. 하위 문서를 펼쳐 메뉴가 길어져도 다른 제목의 너비와 줄바꿈은 유지합니다. 검증할 때는 접힌 메뉴는 화면에 들어가고 펼친 메뉴에는 스크롤이 생기는 높이에서 두 상태의 제목 너비와 줄 수를 비교합니다. 모바일 메뉴에는 이 여백을 적용하지 않습니다.

검색은 실제 문서 제목과 모든 페이지의 절 제목을 대상으로 합니다. Ctrl/⌘+K로 열고 Escape로 닫습니다. 표와 코드 블록은 가로로 스크롤할 수 있습니다. 이전·다음 링크는 실제 문서 순서에서 생성합니다.

## 실행 방법

```powershell
uv run sdd --config examples/libcamera/sdd.yaml export-site
python -m http.server 8765 --bind 127.0.0.1 --directory examples/libcamera/build/site
```

브라우저에서 `http://127.0.0.1:8765/`를 엽니다. 검색과 Mermaid 모듈을 불러오려면 파일을 직접 여는 대신 HTTP 서버를 사용하세요.

설정은 `sdd.yaml`의 `site`에 둡니다.

```yaml
site:
  enabled: true
  title: libcamera 설계 문서
  intro: site-intro.md
  source_url: https://github.com/TTolsun/libcamera-sdd
```

`intro`는 설정 파일 기준의 안내 원고입니다. 생략하면 짧은 기본 안내를 만듭니다. 페이지는 `sections.yaml` 순서를 따르며 추가 MkDocs·시나리오 페이지를 뒤에 연결합니다. `source_url`은 선택 사항이며 해당 커밋이 실제로 존재하는 미러를 지정하세요.

인용 링크의 주소 형식은 코드 열람 호스트에 따라 설정합니다. 기본값은 GitHub/GHE의 `/blob/` 형식이고, Gerrit Gitiles는 `source_link: gitiles`로, 그 밖의 호스트는 템플릿으로 지정합니다. 커밋 40자리 확인과 경로 검증은 형식과 무관하게 적용됩니다.

```yaml
site:
  source_url: https://gerrit.example.com/plugins/gitiles/hal-camera
  source_link: gitiles                                   # github(기본) 또는 gitiles
  # source_link_template: "{url}/browse/{file}?at={commit}#{line}"   # 다른 호스트 형식
```

인용 링크는 facts에 기록된 정확한 파일·줄과 40자리 커밋이 일치할 때만 생성합니다. 원고와 facts의 커밋이 다르면 prose 페이지의 새 그림 생성을 거절합니다.

```powershell
uv run sdd --config examples/libcamera/sdd.yaml export-site --out build/publication/libcamera-sdd/docs
```

이 명령은 출력만 갱신하며 Git push를 수행하지 않습니다. 출력 디렉터리를 전용으로 사용하세요. 기존 `export-html`은 단일 파일 배포용으로 유지합니다.

## 한국어·영어 전환

`site.english_catalog`를 설정하면 기존 한국어 페이지와 같은 경로를 가진 `en/` 영어판을 함께 만듭니다. 상단 메뉴에서 한국어 또는 English를 선택하세요. 영어 메뉴·목차·본문·검색과 그림 조작 안내를 제공합니다. 절 식별자는 같으므로 자바스크립트가 켜져 있으면 전환할 때 읽던 절도 유지합니다. 자바스크립트 없이도 언어 메뉴와 문서 링크를 사용할 수 있습니다.

```yaml
site:
  english_catalog: english.json  # 설정 파일 기준 경로. 생략하면 기존 한국어 사이트만 만든다.
```

번역은 빌드 입력인 JSON 카탈로그에 보관합니다. 외부 번역 서비스나 LLM 연결은 필요하지 않습니다. 공통 기능은 `src/sdd/site_localization.py`에 있고, 공개 libcamera 번역은 `examples/libcamera/english.json`에 있습니다. 사내 문서에는 해당 프로젝트의 별도 카탈로그를 사용하세요.

원고를 바꾼 뒤에는 다음 순서로 번역을 갱신합니다.

1. 원고의 근거 검사를 통과시킨 뒤 검토용 카탈로그를 준비합니다.

   ```powershell
   python -m sdd.site_localization --config <설정>/sdd.yaml --out <설정>/english.json
   ```

2. 카탈로그 diff와 원문을 함께 검토합니다. 기존 문장과 정확히 같은 번역은 유지되고, 새 문장은 빈 값으로 남습니다. `strings`의 값을 영어로 작성하고 `{{0}}` 같은 자리표시자는 각각 한 번씩 보존하세요. 자리표시자는 코드·링크 등 인라인 요소이며 영어 어순에 맞게 옮길 수 있습니다. 원문의 조건·예외·근거를 빠뜨리지 마세요.
3. `export-site`와 `verify-site`를 실행합니다. 원문 페이지 집합과 SHA-256, 번역 누락, 자리표시자 보존 및 링크를 검사합니다. 실패하면 기존 배포는 보존합니다. 카탈로그 준비 명령은 지문을 갱신하므로, 단순히 실행했다는 이유로 문맥 검토를 생략해서는 안 됩니다.

코드·인용·소스 발췌와 한국어 Markdown 다운로드는 원문을 유지합니다. Mermaid는 같은 노드와 연결을 유지하며 생성기가 정한 관계 표시만 번역한 영어 원문을 제공합니다. 검색은 영어 제목과 절 제목을 대상으로 합니다. 영어판의 안내문은 번역이 사람 검토 전이며 원문에 표시된 승인은 번역 승인이 아님을 명시합니다. 카탈로그의 `review_status`를 수정해도 사람 승인으로 승격하지 않습니다.

현재 번역에는 별도의 사람 승인 장부가 없습니다. 따라서 `site.require_approval: true`이면 영어판 게시를 차단합니다. 원문 승인만으로 번역을 승인된 문서처럼 게시하지 않습니다.

페이지 지문에는 생성 시각·검토 상태·화면 문구도 포함됩니다. 이런 값이 바뀌어도 카탈로그를 검토하고 갱신해야 합니다. 기존 CLI와 `impact.json` schema 1은 바뀌지 않습니다. 다음 단계로 [반복 실행 계약](#반복-실행-계약)에 따라 사이트를 검증하세요.

## Mermaid 구성

시나리오 문서는 주요 확인 지점, 호출 관계도, 추적 경계, 전체 추적 기록으로 구성합니다. 호출 관계도는 평탄한 facts에서 실행 순서를 추정하지 않습니다. 같은 호출 지점의 가상 후보는 경계 표에 모으며, 예약 대상도 즉시 실행되는 호출과 구분합니다. 전체 기록은 25개씩 펼쳐 볼 수 있고, `hide`로 요약에서 뺀 호출과 같은 이름의 서로 다른 호출 지점도 보존합니다.

시나리오 섹션의 `narration` 기본값은 `facts`입니다. 호출과 경계의 개수 및 탐색 안내를 추출 근거로 구성하며 LLM을 호출하지 않습니다. `sections.yaml`의 해당 섹션에 `narration: llm`을 명시하면 추가 설명을 모델로 생성하고 문단별 입력 근거 검사를 적용합니다. 이 검사도 실행 순서나 소유권에 대한 일반적인 의미 검증은 아닙니다.

`scenarios.yaml`의 `focus`는 요약할 호출을 선택합니다. 생략하면 표시 가능한 호출에서 중복 관계를 제외한 앞의 6개를 고릅니다. 선택자는 대소문자를 구분하며 `names`는 필수 glob 목록, `src`와 `dst`는 선택 glob입니다. 일치하는 호출이나 근거 위치가 없으면 생성을 중단합니다. 설명을 임의로 추가하는 기능이 아니므로 `title`에는 탐색할 지점의 이름을 적습니다.

```yaml
scenarios:
  - id: capture
    from: CameraDevice::capture()
    focus:
      - title: 요청 제출 대상
        names: [submit]
        src: CameraDevice
        dst: RequestManager
```

관계도는 `diagrams.max_nodes` 한도를 적용하며, 초과하면 `focus`를 나누거나 한도를 명시적으로 바꿔야 합니다. 시나리오 facts 또는 표시 설정이 바뀌면 기존 원고의 지문 검사가 사이트 빌드와 증분 이월을 차단하므로 해당 시나리오를 다시 생성해야 합니다.

새 원고는 `generation_method`로 생성 방식을 기록합니다. 소스 발췌 해시에 연결한 설명, 추출 사실로 만든 구조 설명, LLM 설명, 혼합 문서, 결정적 표·목록과 dry-run을 구분합니다. 페이지 상단에는 생성 방식, 하단에는 검증 범위를 표시합니다. 생성 방식을 기록하지 않은 기존 원고는 설정을 보고 추측하지 않고 미기록으로 표시합니다. `export-site`는 메타데이터를 보충하지 않으므로 표시를 갱신하려면 `generate`로 다시 생성하세요.

`generate --from-impact`는 이번에 선택한 섹션에 LLM 설명이 있을 때만 변경 요약에도 모델을 사용합니다. 소스 계약·facts·표·목록으로 구성된 섹션만 갱신하면 `build/change_impact.md`도 영향 보고서로부터 작성하므로 LLM 연결이 필요하지 않습니다. dry-run에서도 이 요약 파일을 작성합니다.

prose 페이지에서 선택한 클래스와 직접 기반 클래스를 facts로부터 도식화합니다. 실제 추출한 상속과 필드 참조를 사용하며 이름만으로 호출 순서를 추측하지 않습니다. 표시할 노드가 한도를 넘으면 빌드가 실패하므로 섹션을 나누거나 명시적으로 한도를 조정하세요. 기존 Mermaid 코드 블록도 렌더링합니다.

자동 클래스 그림은 `diagrams.enabled: true` 또는 섹션의 `diagram.enabled: true`로 켭니다. 기본값은 꺼짐이며, 기존 프로젝트의 넓은 클래스 선택 범위 때문에 문서 생성이 실패하지 않도록 합니다. libcamera 예제는 명시적으로 켜져 있습니다. 그림을 끄거나 선택한 클래스가 없어지면 사이트 재빌드에서 이전 자동 그림과 `.mmd`를 제거합니다. 원고의 이동 링크를 유지하기 위해 해당 절 제목과 안내 문장은 남기며, 직접 작성한 Mermaid 블록은 보존합니다.

```yaml
diagrams:
  enabled: true
  max_nodes: 16
  direction: LR
  strip_namespace: 'libcamera::'
```

각 섹션의 `diagram`에 같은 키를 넣으면 해당 섹션만 재정의합니다. 지원 방향은 LR·TB·RL·BT입니다. 네임스페이스 생략은 표시 이름에만 적용하며 노드 식별에는 전체 이름을 사용합니다.

그림을 누르거나 키보드 Enter/Space를 누르면 확대 창이 열립니다. 요소 이름 검색, 실제 SVG 크기 변경, 화면에 맞춤, 100% 복귀를 지원합니다. Escape로 닫으면 원래 그림과 키보드 초점을 복원합니다. `.mmd` 원문도 내려받을 수 있습니다.

Mermaid는 OMM 템플릿과 같은 `11.12.0` 버전에 고정했고 `securityLevel: strict`로 실행합니다. 지정한 경로를 읽지 못하면 실패 안내와 원문을 표시합니다.

사내망·오프라인에서는 `sdd fetch-mermaid`로 ESM 배포본(본체와 chunk 모듈)을 준비하고, `site.mermaid_dir`를 지정해 사이트 산출물에 동봉합니다. 그러면 CDN 주소가 페이지에 남지 않고 그림이 사이트 자체 파일로 렌더링됩니다. 망이 분리된 환경에서는 `mermaid-<버전>.tgz`를 먼저 반입한 뒤 `--tarball`로 지정하고, 사내 npm 미러가 있으면 `--registry`를 씁니다.

```powershell
uv run sdd --config <설정>/sdd.yaml fetch-mermaid          # <설정 루트>/assets/mermaid 에 준비
uv run sdd --config <설정>/sdd.yaml fetch-mermaid --tarball mermaid-11.12.0.tgz   # 반입한 파일 사용
```

```yaml
site:
  mermaid_dir: assets/mermaid    # 설정 루트 기준. export-site 가 사이트의 assets/mermaid/ 로 복사한다
```

이미 사내 웹 서버에 Mermaid를 호스팅하고 있다면 `site.mermaid` 또는 `--mermaid`로 그 주소(또는 사이트 루트 기준 경로)만 지정해도 됩니다. 우선순위는 `--mermaid` > `site.mermaid` > `site.mermaid_dir` > 공개 CDN입니다.

## OMM 이력 관리 도입 여부

현재는 Git 원본 이력, facts의 `source_commit`, 문서의 생성 메타데이터, `impact`의 기준·대상 커밋으로 분석 입력과 영향을 추적합니다. OMM의 commit 수집도 Git 이력과 검토 체크포인트를 기반으로 하므로 지금 추가하면 이력 상태를 이중으로 관리하게 됩니다.

따라서 이번에는 디자인 규칙만 적용합니다. 향후 여러 저장소의 설계 의도·제약·검토 승인과 체크포인트를 공통 OMM 항목으로 연결해야 할 때 도입을 다시 판단합니다. 커밋 추적 자동화는 `sdd update`(순서 보장·재개·리뷰 관문), 승인 기록은 `sdd accept` 장부가 담당하며, 두 기능 모두 회귀 테스트로 동작을 확인했고, libcamera·사내 저장소에서의 실측은 남아 있습니다.

다음 단계: 게시 문서의 근거와 문장을 검토합니다.
