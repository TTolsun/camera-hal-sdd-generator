"""A3·A4: 이동 안내 표의 문구는 대상 페이지에서 만들고, 제목을 찾지 못한 slug를 링크 글자로 쓰지 않는다."""
import pytest

from sdd import routes
from sdd.facts.model import KnowledgeModel
from sdd.page_writer import PageWriter

TITLES = {"vendor-overview.md": "libcamera 제품 개요", "vendor-integration.md": "연동 가이드"}
LEADS = {"vendor-overview.md": "제공 기능과 공통 설계의 강점을 확인하고 도입할 범위를 판단하세요.",
         "vendor-integration.md": "연동 순서와 구현 책임을 확인하고 설정·요청·정지 계약을 적용하세요."}


def writer(tmp_cfg):
    return PageWriter(tmp_cfg, KnowledgeModel(), TITLES, LEADS)


def render(tmp_cfg, rows, body="## 본문\n\n내용입니다."):
    return writer(tmp_cfg)._render(
        title="지원 범위", lead="확인하세요.", body=body, routes=rows, evidence="    - 근거",
        next_link=("연동 가이드", "vendor-integration.md"), status="ok", omitted=[], extra={},
        page_path=tmp_cfg.sdd_dir / "vendor-assurance.md")


def test_A4_대상_제목을_찾지_못하면_slug를_링크_글자로_쓰지_않고_실패한다(tmp_cfg):
    with pytest.raises(ValueError, match="vendor-missing.md"):
        render(tmp_cfg, [("개요를 확인합니다.", "vendor-missing.md")])


def test_A4_제목이_있으면_섹션_제목이_링크_글자가_된다(tmp_cfg):
    page = render(tmp_cfg, [("개요를 확인합니다.", "vendor-overview.md")])
    assert "[libcamera 제품 개요](vendor-overview.md)" in page and "[vendor-overview]" not in page


def test_A3_q를_생략하면_대상_페이지의_lead가_문구가_된다(tmp_cfg):
    page = render(tmp_cfg, [("", "vendor-overview.md"), ("", "vendor-integration.md")])
    assert f"| {LEADS['vendor-overview.md']} | [libcamera 제품 개요](vendor-overview.md) |" in page
    assert f"| {LEADS['vendor-integration.md']} | [연동 가이드](vendor-integration.md) |" in page


def test_A3_lead가_없는_대상은_문구를_지어내지_않고_실패한다(tmp_cfg):
    leadless = PageWriter(tmp_cfg, KnowledgeModel(), TITLES, {})
    with pytest.raises(ValueError, match="lead"):
        leadless._render(title="t", lead="l", body="## 본문\n\n내용", routes=[("", "vendor-overview.md")],
                         evidence="    - 근거", next_link=("n", "vendor-integration.md"), status="ok", omitted=[],
                         extra={}, page_path=tmp_cfg.sdd_dir / "x.md")


@pytest.mark.parametrize("q", ["연동 가이드에서 필요한 내용을 확인합니다.", "연동 가이드 문서로 이동합니다.", "연동 가이드를 확인합니다"])
def test_A3_대상_제목만_반복하는_q는_설정_검사에서_경고한다(q):
    sections = [{"id": "vendor-overview", "routes": [{"q": q, "to": "vendor-integration.md"}]}]
    warned = routes.warnings(sections, TITLES)
    assert len(warned) == 1 and "연동 가이드" in warned[0] and "lead" in warned[0]


def test_A3_독자가_얻을_내용을_적은_q와_q_생략은_경고하지_않는다():
    sections = [{"id": "a", "routes": [{"q": "연동 순서와 구현 책임을 확인합니다.", "to": "vendor-integration.md"},
                                       {"to": "vendor-overview.md"}]}]
    assert routes.warnings(sections, TITLES) == []
