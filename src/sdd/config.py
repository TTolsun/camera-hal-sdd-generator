"""sdd.yaml (+ sdd.local.yaml) 로더.

상대 경로는 모두 sdd.yaml 이 있는 디렉터리를 기준으로 절대 경로로 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentConfig:
    kind: str = "dry-run"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434"
    max_input_chars: int = 18000
    temperature: float = 0.1
    timeout_sec: int = 300
    num_ctx: int = 0
    # true 이면 style/i-have-adhd.md 와 style/fluent-korean.md 전문도 system 프롬프트에 넣는다 (약 13k 자).
    # 소형 모델에서는 false 로 두고 style/README.md 의 번안 규칙만 넣는다.
    full_style_guides: bool = False
    # ollama 전용. thinking 모델(Qwen3 등)의 사고 생성을 끈다. 켜면 호출당 수 분이 더 걸린다.
    think: bool = False
    # 출력 토큰 상한. 소형 모델이 같은 문단을 반복하는 폭주를 막는다. 0 이면 지정하지 않는다.
    max_output_tokens: int = 1500
    # 인증 토큰을 읽을 환경 변수. 설정 파일로 바꿀 수 없고, 다른 엔드포인트로 갈 때만 코드가 바꾼다.
    api_key_env: str = "SDD_AGENT_API_KEY"


@dataclass
class Config:
    root: Path
    source_root: Path
    compile_commands: Path
    # 소스 루트 기준 glob. 여기에 걸리는 파일의 선언·호출·플래그는 사실에서 뺀다 (third_party 등).
    exclude: list[str]
    ndk_build: dict[str, Any]
    facts_dir: Path
    sdd_dir: Path
    diagrams_dir: Path
    clang_uml_bin: str
    agent: AgentConfig
    require_citations: bool
    max_retries: int
    # 패키지 = 선언 파일 경로의 앞 N 개 디렉터리. 1 이면 최상위 디렉터리 하나로 묶는다.
    # 소스가 src/ 와 include/ 아래로만 나뉘는 프로젝트는 2 이상이어야 패키지 표가 의미를 가진다.
    package_depth: int = 1
    raw: dict[str, Any] = field(default_factory=dict)
    # 자산 위치. 기본은 root 아래 config/, prompts/, templates/, style/. sdd.yaml 의 paths: 로 바꿀 수 있다
    # (examples/ 처럼 저장소의 자산을 다른 위치에서 재사용할 때).
    paths: dict[str, Path] = field(default_factory=dict)

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def facts_path(self) -> Path:
        return self.facts_dir / "facts.json"

    @property
    def config_dir(self) -> Path:
        return self.paths.get("config", self.root / "config")

    @property
    def sections_file(self) -> Path:
        return self.paths.get("sections_file", self.config_dir / "sections.yaml")

    @property
    def scenarios_file(self) -> Path:
        return self.paths.get("scenarios_file", self.config_dir / "scenarios.yaml")

    @property
    def clang_uml_file(self) -> Path:
        return self.paths.get("clang_uml_file", self.config_dir / "clang-uml.yaml")

    @property
    def prompts_dir(self) -> Path:
        return self.paths.get("prompts", self.root / "prompts")

    @property
    def templates_dir(self) -> Path:
        return self.paths.get("templates", self.root / "templates")

    @property
    def style_dir(self) -> Path:
        return self.paths.get("style", self.root / "style")

    def sections(self) -> list[dict[str, Any]]:
        data = _load_yaml(self.sections_file)
        return list(data.get("sections", []) or [])

    def scenarios(self) -> list[dict[str, Any]]:
        data = _load_yaml(self.scenarios_file)
        defaults = data.get("defaults", {}) or {}
        return [{**defaults, **sc} for sc in (data.get("scenarios", []) or [])]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def section_output(section: dict[str, Any]) -> str:
    """섹션이 만드는 페이지의 sdd 루트 기준 경로.

    생성과 사이트 구성이 같은 규칙을 써야 문서 목록의 링크와 메뉴 항목이 어긋나지 않는다.
    """
    kind = section.get("kind", "prose")
    return str(section.get("output") or ("scenarios/index.md" if kind == "per-scenario"
                                         else f"{section['id']}.md"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_root(start: Path | None = None) -> Path:
    """현재 디렉터리에서 위로 올라가며 sdd.yaml 을 찾는다."""
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "sdd.yaml").exists():
            return p
    raise FileNotFoundError("sdd.yaml 을 찾지 못했습니다. 저장소 루트에서 실행하세요.")


def load(path: Path | None = None) -> Config:
    root = path.parent.resolve() if path else find_root()
    # 지정한 파일을 그대로 읽는다. 이름을 버리고 sdd.yaml 만 읽으면, 한 디렉터리에 설정을 여럿 둔
    # 실행(두 커밋 비교 등)에서 지정하지 않은 설정이 조용히 돌고 그 사실이 로그에 드러나지 않는다.
    main = path.resolve() if path else root / "sdd.yaml"
    if not main.is_file():
        raise FileNotFoundError(f"설정 파일을 찾지 못했습니다: {main}")
    # 로컬 덮어쓰기는 같은 이름 옆에 둔다: sdd.yaml -> sdd.local.yaml, sdd.a.yaml -> sdd.a.local.yaml
    local = main.with_name(f"{main.stem}.local{main.suffix}")
    raw = _deep_merge(_load_yaml(main), _load_yaml(local))

    def rel(p: str | None, default: str) -> Path:
        return (root / (p or default)).resolve()

    src = raw.get("source", {}) or {}
    out = raw.get("output", {}) or {}
    tools = raw.get("tools", {}) or {}
    agent_raw = raw.get("agent", {}) or {}
    review = raw.get("review", {}) or {}

    ndk = dict(src.get("ndk_build", {}) or {})
    if ndk.get("project_dir"):
        ndk["project_dir"] = str(rel(ndk["project_dir"], "."))
    # PATH 의 이름(clang++)은 그대로 두고, 경로로 적은 NDK clang 만 설정 파일 기준으로 푼다.
    if ndk.get("clang") and any(sep in str(ndk["clang"]) for sep in "/\\"):
        ndk["clang"] = str(rel(ndk["clang"], "."))

    agent = AgentConfig(
        kind=str(agent_raw.get("kind", "dry-run")),
        model=str(agent_raw.get("model", "qwen3.5:4b")),
        base_url=str(agent_raw.get("base_url", "http://localhost:11434")).rstrip("/"),
        max_input_chars=int(agent_raw.get("max_input_chars", 18000)),
        temperature=float(agent_raw.get("temperature", 0.1)),
        timeout_sec=int(agent_raw.get("timeout_sec", 300)),
        num_ctx=int(agent_raw.get("num_ctx", 0)),
        full_style_guides=bool(agent_raw.get("full_style_guides", False)),
        think=bool(agent_raw.get("think", False)),
        max_output_tokens=int(agent_raw.get("max_output_tokens", 1500)),
    )

    return Config(
        root=root,
        source_root=rel(src.get("root"), "../hal-camera"),
        compile_commands=rel(src.get("compile_commands"), "../hal-camera/compile_commands.json"),
        exclude=[str(g) for g in (src.get("exclude", []) or [])],
        ndk_build=ndk,
        facts_dir=rel(out.get("facts_dir"), "build/facts"),
        sdd_dir=rel(out.get("sdd_dir"), "sdd"),
        diagrams_dir=rel(out.get("diagrams_dir"), "sdd/diagrams"),
        clang_uml_bin=str(tools.get("clang_uml", "clang-uml")),
        agent=agent,
        require_citations=bool(review.get("require_citations", True)),
        max_retries=int(review.get("max_retries", 1)),
        package_depth=max(1, int((raw.get("facts", {}) or {}).get("package_depth", 1))),
        raw=raw,
        paths={k: rel(str(v), ".") for k, v in (raw.get("paths", {}) or {}).items()},
    )
