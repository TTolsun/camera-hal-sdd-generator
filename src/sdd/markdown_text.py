"""Shared Markdown anchors; no generation or rendering dependencies."""
import re

def slugify(text: str) -> str:
    """pymdownx.slugs.slugify(case=lower) 와 같은 규칙. 한글 제목도 앵커가 된다."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", text)
