"""Prompt policy independent of generation orchestration."""
import re
from .config import Config

_YAML_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)

def style_rules(readme_text: str) -> str:
    """style/README.md 에서 번호 붙은 규칙만 뽑는다.

    README 전체(출처 링크, brief.mjs 설명)를 넣으면 소형 모델이 그 문서를 그대로 되풀이하는 일이 있었다.
    번호 붙은 집필 규칙만 넣어 출처 설명의 재출력을 피하고 프롬프트를 짧게 유지한다."""
    rules = [l.strip() for l in readme_text.splitlines() if re.match(r"^\s*\d+\.\s", l)]
    return "개발자 가이드 집필 규칙:\n" + "\n".join(rules) if rules else readme_text.strip()

def compose_system_prompt(cfg: Config) -> str:
    """prompts/system.md + style/README.md 의 규칙 (+ 원문 두 개, 설정 시). omm-doc-workflow 의 brief.mjs 와 같은 방식."""
    parts = [(cfg.prompts_dir / "system.md").read_text(encoding="utf-8").strip()]
    readme = cfg.style_dir / "README.md"
    if readme.exists():
        parts.append(style_rules(readme.read_text(encoding="utf-8")))
    if cfg.agent.full_style_guides:
        for name in ("i-have-adhd.md", "fluent-korean.md"):
            p = cfg.style_dir / name
            if p.exists():
                parts.append(_YAML_FRONTMATTER.sub("", p.read_text(encoding="utf-8"), count=1).strip())
    return "\n\n---\n\n".join(parts)
