#!/usr/bin/env bash
# Gerrit patchset-created 훅 또는 Jenkins/GitLab CI job 에서 호출하는 예시.
#
# 전제:
#   - 이 저장소(camera-hal-sdd-generator)와 HAL 소스(hal-camera)가 나란히 checkout 되어 있다.
#   - NDK, clang-uml, uv 와 선택한 에이전트 CLI가 PATH 에 있다.
#   - docs 저장소는 sdd/ 디렉터리를 그대로 담는 별도 Gerrit 프로젝트다 (DOCS_REMOTE).
#
# 환경 변수 (Gerrit 훅이 넘겨주는 값에 맞춰 조정):
#   GERRIT_CHANGE_NUMBER, GERRIT_PATCHSET_REVISION, GERRIT_BRANCH
#   DOCS_DIR           docs 프로젝트의 로컬 clone (여기에 sdd/ 를 복사해서 commit 한다)
#   DOCS_REMOTE        (예: ssh://gerrit.internal:29418/camera/hal-docs)
#   MANUAL_PAGES       선택 사항. sections의 manual/index 출력 + index.md와 정확히 같아야 한다.
# 게시 보호와 최초 이전: docs/inhouse/gerrit-markdown-publication.md

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
HAL_DIR="${HAL_DIR:-$HERE/../hal-camera}"
REVISION="${GERRIT_PATCHSET_REVISION:-HEAD}"
BRANCH="${GERRIT_BRANCH:-main}"

cd "$HAL_DIR"
git fetch -q origin "$REVISION" 2>/dev/null || true
git checkout -q "$REVISION"
BASE="$(git merge-base HEAD "origin/$BRANCH")"

cd "$HERE"
uv sync --frozen 2>/dev/null || uv sync
uv run sdd compdb
uv run sdd run --base "$BASE"

# 생성된 sdd/ 를 docs 저장소(별도 Gerrit 프로젝트의 로컬 clone, DOCS_DIR)에 복사해서 change 로 올린다.
# 이 저장소(파이프라인 코드)의 HEAD 를 그대로 push 하지 않는다. docs 프로젝트에는 문서만 들어간다.
# Change-Id 는 docs clone 에 설치된 commit-msg 훅이 붙인다.
if [[ -n "${DOCS_DIR:-}" && -n "${DOCS_REMOTE:-}" ]]; then
  # Markdown 전용 소유권 검사와 사전 복사를 마친 뒤 반영한다. HTML site manifest와 혼용하지 않는다.
  uv run python -m sdd.markdown_publication \
    --config "$HERE/sdd.yaml" --docs-dir "$DOCS_DIR" \
    --remote "$DOCS_REMOTE" \
    --push-ref "refs/for/${BRANCH}%topic=hal-${GERRIT_CHANGE_NUMBER:-manual}" \
    --subject "docs: SDD 갱신 (HAL change ${GERRIT_CHANGE_NUMBER:-?} / ${REVISION:0:10})" \
    --body-file "$HERE/build/change_impact.md"
fi
