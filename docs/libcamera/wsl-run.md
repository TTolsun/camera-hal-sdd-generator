# libcamera WSL2 실행 및 공개 배포 기록

**[공개 웹 문서](https://ttolsun.github.io/libcamera-sdd/)에서 첫 생성 결과를 확인할 수 있습니다. 세 페이지 중 한 페이지는 인용 형식 검토가 필요합니다.**

| 지금 확인할 내용 | 위치 |
|---|---|
| 생성된 문서를 읽습니다. | [GitHub Pages](https://ttolsun.github.io/libcamera-sdd/) |
| 문서와 실행 기록을 확인합니다. | [TTolsun/libcamera-sdd](https://github.com/TTolsun/libcamera-sdd) |
| 분석한 원본 코드를 확인합니다. | [분석 커밋](https://github.com/TTolsun/libcamera-sdd/tree/279d355ef8f7a4f98bb0a3004c0f788387814506) |
| 환경을 다시 구성합니다. | [가정용 검증 절차](home-lab.md) |

## 실행 환경

2026-09-20에 기존 Windows PC의 Ubuntu WSL2를 사용했습니다. 별도 Ubuntu 설치나 듀얼 부팅은 하지 않았습니다. Ubuntu 공식 패키지에서 C++ 빌드 의존성을 설치하고, WSL용 Python 가상환경을 새로 구성했습니다.

| 항목 | 실제 값 |
|---|---|
| Linux | Ubuntu 26.04 LTS, WSL2 |
| libcamera | `279d355ef8f7a4f98bb0a3004c0f788387814506` |
| 분석 소스 | `/home/baboess/work/libcamera` |
| Linux 생성기 사본 | `/home/baboess/work/camera-hal-sdd-generator` |
| 컴파일러 | Clang 21.1.8 |
| Meson / Ninja | 1.10.1 / 1.13.2 |
| Python / pip libclang | 3.14.4 / 18.1.1 |
| uv | 0.12.17, 별도 `~/work/sdd-tools` 가상환경 |
| 서술 모델 | Windows Ollama의 `qwen3.5:4b` |
| 모델 식별자 | `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd` |

빌드는 다음 옵션으로 성공했습니다. 시스템에 libcamera를 설치하는 `ninja install`은 실행하지 않았습니다.

```bash
CC=clang CXX=clang++ meson setup build \
  -Dpipelines=ipu3,rkisp1,uvcvideo -Dipas=ipu3,rkisp1 \
  -Dgstreamer=enabled -Dcam=disabled -Dqcam=disabled \
  -Ddocumentation=disabled -Dpycamera=disabled -Dtest=false
ninja -C build -j 6
```

WSL의 `localhost:11434`에서는 Windows Ollama에 연결되지 않았습니다. 따라서 Linux에서 사실을 추출하고, facts를 Windows 작업 폴더로 복사한 뒤 기존 Windows Ollama로 서술을 생성했습니다. Ollama의 외부 수신 설정이나 방화벽은 변경하지 않았습니다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| libcamera 빌드 | IPU3·RKISP1·UVC와 GStreamer 빌드에 성공했습니다. |
| 분석 범위 | compile DB의 171개 translation unit을 처리했습니다. |
| Clang 파싱 오류 | 0건이었습니다. |
| 최종 facts | 클래스 1,005개, 자유 함수 429개, 플래그 7개를 확보했습니다. |
| 호출 그래프 | 함수 정의 2,850개를 추적했습니다. 시나리오 진입점은 아직 설정하지 않았습니다. |
| 핵심 클래스 | Camera·CameraManager·Request·PipelineHandler를 모두 확인했습니다. |
| 근거 위치 | 331개 파일의 인용 4,825개가 실제 파일의 줄 범위 안에 존재했습니다. |
| 변경 영향 | 직전 커밋과 비교한 변경 파일 5개에 대해 세 페이지를 선택했습니다. Meson 변경이 포함되어 보수적으로 전체를 선택했습니다. |
| 변경 없음 | 같은 SHA를 비교하면 변경 파일과 영향 섹션이 모두 비었습니다. |
| 공개 배포 | GitHub Pages가 HTTP 200을 반환하고 이번 소스 SHA와 문서 제목을 포함하는 것을 확인했습니다. |

위 검사는 정적 사실 추출과 문서 생성의 첫 실행 결과입니다. 두 소스 버전에서 각각 전체 facts를 만들고 문서의 의미 변화를 비교하는 검증, 실기기 촬영, GStreamer 재생은 수행하지 않았습니다.

### 페이지별 상태

| 문서 | 자동 인용 검사 | 추가 검토 |
|---|---|---|
| 카메라와 요청 모델 | `needs-review` | 모델이 인용을 백틱 대신 대괄호로 출력했습니다. |
| Pipeline Handler | `ok` | 지시문을 설명하는 불필요한 문장과 동작 설명을 검토해야 합니다. |
| IPA 관리와 구현 진입점 | `ok` | 문장 중 잘못 생성된 단어와 내부 동작 설명을 검토해야 합니다. |

자동 검증 상태를 실제 출력 그대로 게시했습니다. 인용 검사 통과는 서술의 정확성이나 사람의 승인을 뜻하지 않습니다. 문서의 `simple_compdb` 표시는 현재 생성기의 메타데이터 한계이며, 이번 입력은 Meson이 만든 compile DB를 보정한 파일입니다.

## 실행 중 발견해 보완한 문제

1. pip libclang이 `stddef.h`를 찾지 못했습니다. [prepare_compdb.py](../../examples/libcamera/prepare_compdb.py)가 실제 Clang의 resource 디렉터리를 지정하도록 했습니다.
2. 상대 include 경로 때문에 Camera 등의 헤더 선언이 사실 추출에서 빠졌습니다. 같은 스크립트가 include 경로를 절대 경로로 변환하도록 했습니다. Meson의 원본 compile DB는 보존합니다.
3. 파싱 오류 0건만으로는 누락을 발견할 수 없었습니다. [verify_facts.py](../../examples/libcamera/verify_facts.py)를 추가해 핵심 클래스, 페이지별 사실 선택, 소스 SHA, 인용 위치를 확인하게 했습니다. 이 검사가 초기 불완전한 facts를 거절하고 보완된 facts를 통과시키는 것을 확인했습니다.
4. IPA 전체를 한 페이지에 넣으면 입력 한도를 초과했습니다. 관리자·모듈·프록시와 IPU3/RKISP1 구현의 주요 클래스 다섯 개로 첫 페이지의 범위를 제한했습니다.

초기의 불완전한 출력은 로컬 `examples/libcamera/build/initial-incomplete/`에 보관했습니다. 게시된 결과는 보완된 facts로 다시 생성한 `build/verified-sdd/`에서 가져왔습니다. 이 경로의 `verified`는 입력 사실의 존재·위치 검증을 의미하며, 서술의 사람 검토 완료를 뜻하지 않습니다.

## 전용 GitHub 저장소 구성

문서를 만드는 기술은 `camera-hal-sdd-generator`에서 관리합니다. Clang 분석, 영향 분석, LLM 호출, 인용 검증과 libcamera용 설정·보정 스크립트가 여기에 속합니다. `libcamera-sdd`는 upstream 이력 보관과 생성 결과의 검토·배포를 담당하며 생성 엔진을 복제하지 않습니다.

| 위치 | 역할 |
|---|---|
| `TTolsun/libcamera-sdd`의 `upstream/master` | 원본 libcamera 이력을 보관합니다. 최초 동기화 SHA는 위 분석 커밋과 같습니다. |
| 같은 저장소의 `main` | 문서 Markdown, HTML, `run.json`을 보관합니다. |
| `main/docs` | GitHub Pages의 게시 경로입니다. 문서 브랜치를 갱신하면 Pages가 반영합니다. |
| 현재 생성기 저장소의 `build/publication/libcamera-sdd` | 새 전용 저장소의 로컬 Git checkout입니다. |

사용자가 공개 배포를 선택한 뒤 저장소와 Pages를 공개했습니다. libcamera upstream으로 변경을 보내지는 않았습니다.

문서 화면은 [사이트 구성](../concepts/site.md)에 따라 여러 페이지로 개편했습니다. libcamera 공식 문서의 탐색 구조와 OMM의 읽기 중심 디자인·그림 확대 규칙을 적용했으며, 원본 Markdown과 인용 검사 상태는 보존합니다. OMM 이력 관리 실행기는 추가하지 않았습니다.

**upstream 자동 fetch, 커밋 큐, 자동 문서 갱신과 PR 생성은 아직 연결하지 않았습니다.** 이번 작업은 WSL2 실제 빌드·생성, 원본 이력의 최초 동기화, 검토용 웹 문서 공개까지 완료한 기록입니다. 문서 생성은 로컬 모델을 사용하므로 후속 자동화에서도 집의 실행기 또는 모델이 설치된 실행 환경을 연결해야 합니다.

다음 단계: [공개 웹 문서](https://ttolsun.github.io/libcamera-sdd/)에서 검토가 필요한 페이지를 확인합니다.
