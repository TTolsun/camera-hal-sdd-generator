"""Repository source-link formats shared by Markdown and diagram captions."""
from .config import SiteConfig

SOURCE_LINK_TEMPLATES = {
    "github": "{url}/blob/{commit}/{file}#L{line}",
    "gitiles": "{url}/+/{commit}/{file}#{line}",
}


def source_link_template(settings: SiteConfig | dict) -> str:
    """site 설정에서 인용 링크 템플릿을 정한다.

    `site.source_link_template` 이 있으면 그대로 쓰고, 없으면 `site.source_link` 가 가리키는
    호스트 형식(github 기본, gitiles)을 쓴다. 자리표시자가 어긋난 템플릿은 게시 시점에 조용히
    깨진 링크를 만들므로 여기서 즉시 실패시킨다.
    """
    if isinstance(settings, dict):
        settings = SiteConfig.from_mapping(settings)
    template = str(settings.source_link_template or "")
    if not template:
        host = str(settings.source_link)
        template = SOURCE_LINK_TEMPLATES.get(host, "")
        if not template:
            raise RuntimeError(f"site.source_link 값을 모릅니다: {host} "
                               f"(지원: {', '.join(sorted(SOURCE_LINK_TEMPLATES))}. "
                               "다른 호스트는 site.source_link_template 로 형식을 지정하세요)")
    try:
        template.format(url="u", commit="c", file="f", line=1)
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError("site.source_link_template 의 자리표시자는 {url} {commit} {file} {line} "
                           f"만 쓸 수 있습니다: {e}")
    return template
