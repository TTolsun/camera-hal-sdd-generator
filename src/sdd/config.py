"""sdd.yaml (+ sdd.local.yaml) 로더.

상대 경로는 모두 sdd.yaml 이 있는 디렉터리를 기준으로 절대 경로로 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
import math


@dataclass(frozen=True)
class ReviewConfig:
    design_prompt: str = 'standard'
    design_grounding: bool = False
    design_revision: bool = False
    answer_cache: bool = False
    cli_checkpoint: bool = False
    max_calls: int = 0
    max_seconds: int = 0
    document_max_calls: int = 0
    document_max_seconds: int = 0
    reader_loop: dict[str, Any] = field(default_factory=dict)
    coverage_triage: dict[str, Any] = field(default_factory=dict)

    def prompt_mode(self, override=None):
        mode = self.design_prompt if override is None else override
        if mode not in ('standard', 'focused'):
            raise ValueError('review.design_prompt는 standard 또는 focused여야 합니다.')
        return mode

    def grounding(self, section):
        value = section.get('design_grounding', self.design_grounding)
        if type(value) is not bool:
            raise ValueError('review.design_grounding은 boolean이어야 합니다.')
        return value


    def triage_options(self):
        opts = self.coverage_triage or {}
        if not isinstance(opts, dict) or set(opts) - {'enabled', 'pass_gate', 'agent', 'max_diff_chars'}:
            raise ValueError(f"review.coverage_triage 는 {sorted({'enabled', 'pass_gate', 'agent', 'max_diff_chars'})} 만 지원합니다.")
        # "false" 같은 문자열은 파이썬에서 참이 되므로, 관문을 여는 값은 진짜 불리언만 받는다.
        for key in ("enabled", "pass_gate"):
            if key in opts and not isinstance(opts[key], bool):
                raise ValueError(f"review.coverage_triage.{key} 는 true 또는 false 여야 합니다: {opts[key]!r}")
        limit = opts.get("max_diff_chars", 6000)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"review.coverage_triage.max_diff_chars 는 양의 정수여야 합니다: {limit!r}")
        return opts


@dataclass(frozen=True)
class SiteConfig:
    enabled: bool = False
    title: str = 'Camera HAL SDD'
    source_url: str = ''
    source_link_template: str = ''
    source_link: str = 'github'
    nav_group: str = ''
    nav_groups: list[str] = field(default_factory=list)
    require_approval: bool = False
    intro: str | None = None
    overview_visual: dict | None = None
    english_catalog: str | None = None
    mermaid_dir: str | None = None
    mermaid: str = ''
    undefined_terms: str | None = None
    translation_batch_size: int = 1

    @classmethod
    def from_mapping(cls, values):
        return _settings(cls, values)

    def batch_size(self):
        value = self.translation_batch_size
        if type(value) is not int or not 1 <= value <= 16:
            raise ValueError('site.translation_batch_size must be an integer from 1 to 16.')
        return value


@dataclass(frozen=True)
class UpdateConfig:
    extract_cmd: list[str] | None = None
    compdb_cmd: list[str] | None = None

    def extraction_command(self):
        command = self.extract_cmd
        if command is not None and (not isinstance(command, list) or not command
                or any(not isinstance(v, str) or not v for v in command)):
            raise ValueError('update.extract_cmd는 비어 있지 않은 문자열 인자 목록이어야 합니다.')
        return command


@dataclass(frozen=True)
class VisualsConfig:
    file: str | None = None
    max_nodes: int = 12
    on_stale: str = 'error'


@dataclass(frozen=True)
class AutomationConfig:
    # Publication hooks, idle review rules and schedule are separate consumers.
    # Keep the exact supplied mapping for the existing resume identity.
    options: dict[str, Any]
    schedule: dict[str, Any]
    publish: dict[str, Any]
    hermes: dict[str, Any]
    idle_review: dict[str, Any]


    def publication_options(self):
        opts = self.options
        if not isinstance(opts, dict):
            raise ValueError("automation 설정은 객체여야 합니다.")
        pub = opts.get("publish", {})
        if not isinstance(pub, dict) or not isinstance(opts.get("hermes", {}), dict):
            raise ValueError("publish와 hermes 설정은 객체여야 합니다.")
        if not isinstance(opts.get("idle_review", {}), dict):
            raise ValueError("idle_review 설정은 객체여야 합니다.")
        if opts.get("idle_review", {}).get("enabled") and not opts.get("hermes", {}).get("enabled"):
            raise ValueError("누락 점검에는 automation.hermes.enabled가 필요합니다.")
        if int(pub.get("timeout_sec", 900)) <= 0:
            raise ValueError("publish.timeout_sec은 양수여야 합니다.")
        for key in ("repo", "directory", "remote", "branch"):
            if not isinstance(pub.get(key), str) or not pub[key].strip():
                raise ValueError(f"automation.publish.{key}가 필요합니다.")
        if pub["remote"].startswith("-") or pub["branch"].startswith("-"):
            raise ValueError("Git remote/branch는 옵션으로 시작할 수 없습니다.")
        command_arguments(pub.get("verify_command"), "publish.verify_command")
        if pub.get("deploy_command") is not None:
            command_arguments(pub["deploy_command"], "publish.deploy_command")
        return opts, pub


DOCUMENTATION_DEFAULTS = {"max_chars": 18000, "max_markdown_chars": 120000, "max_growth_ratio": 1.5,
            "min_growth_chars": 1000, "duplicate_min_chars": 180}



def documentation_limits(values):
    if set(values) - set(DOCUMENTATION_DEFAULTS):
        raise ValueError("Unknown documentation limit")
    for name, value in values.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"documentation limit must be positive: {name}")
        if name != "max_growth_ratio" and not isinstance(value, int):
            raise ValueError(f"documentation limit must be an integer: {name}")
    if values["max_growth_ratio"] <= 1:
        raise ValueError("max_growth_ratio must exceed 1")



@dataclass(frozen=True)
class DocumentationConfig:
    options: dict[str, Any]

    def settings(self):
        options = self.options
        if not isinstance(options, dict) or not isinstance(options.get("enabled", False), bool):
            raise ValueError("documentation.enabled must be a boolean")
        if set(options) - {"enabled", "limits", "pages", "features", "retired_pages"}:
            raise ValueError("Unknown documentation setting")
        if not isinstance(options.get("limits", {}), dict) or not isinstance(options.get("pages", {}), dict):
            raise ValueError("documentation limits/pages must be objects")
        limits = {**DOCUMENTATION_DEFAULTS, **options.get("limits", {})}
        documentation_limits(limits)
        for key in ("features", "retired_pages"):
            if not isinstance(options.get(key, []), list):
                raise ValueError(f"documentation.{key} must be a list")
        for rel, overrides in options.get("pages", {}).items():
            if not isinstance(overrides, dict):
                raise ValueError("Page limits must be an object")
            documentation_limits({**limits, **overrides})
        return {**options, "limits": limits}


def command_arguments(value, label):
    if not isinstance(value, list) or not value or any(not isinstance(a, str) or not a for a in value):
        raise ValueError(f"{label}은 비어 있지 않은 명령 인자 목록이어야 합니다.")


def _settings(cls, values):
    # Keep unknown project keys in raw for lossless snapshots. Only the fields
    # consumed by this responsibility cross its typed boundary.
    return cls(**{name: values[name] for name in cls.__dataclass_fields__ if name in values})


@dataclass
class AgentConfig:
    kind: str = "cli"
    model: str = ""
    runner: str = "hermes"
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    allow_direct_api: bool = False
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
    # Network-independent LLM response exchange, bound to exact requests.
    response_dir: str = ""
    # 인증 토큰을 읽을 환경 변수. 설정 파일로 바꿀 수 없고, 다른 엔드포인트로 갈 때만 코드가 바꾼다.
    api_key_env: str = "SDD_AGENT_API_KEY"

    @property
    def label(self):
        return (f'cli/{self.runner}/{self.model or "cli-default"}' if self.kind == 'cli'
                else f'{self.kind}/{self.model}')


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

    # Resolve on access: existing integrations edit raw when cloning a trial or
    # disabling localization. A cached second copy would silently become stale.
    @property
    def review(self) -> ReviewConfig:
        return _settings(ReviewConfig, self.raw.get('review') or {})

    @property
    def site(self) -> SiteConfig:
        return _settings(SiteConfig, self.raw.get('site') or {})

    @property
    def update(self) -> UpdateConfig:
        return _settings(UpdateConfig, self.raw.get('update') or {})

    @property
    def visuals(self) -> VisualsConfig:
        settings = self.raw.get('visuals', {})
        if not isinstance(settings, dict) or set(settings) - {'file', 'max_nodes', 'on_stale'}:
            raise ValueError('visuals accepts file, max_nodes and on_stale')
        if settings.get('on_stale', 'error') not in {'error', 'omit'}:
            raise ValueError('visuals.on_stale must be error or omit')
        return _settings(VisualsConfig, settings)

    @property
    def automation(self) -> AutomationConfig:
        opts = self.raw.get('automation', {})
        if not isinstance(opts, dict):
            raise ValueError('automation 설정은 객체여야 합니다.')
        return AutomationConfig(opts, *(opts.get(k, {}) for k in
                                       ('schedule', 'publish', 'hermes', 'idle_review')))

    @property
    def documentation(self) -> DocumentationConfig:
        return DocumentationConfig(self.raw.get('documentation', {}))

    def diagram_policy(self, section):
        # Section overrides and false/0 are retained verbatim. Graph validity
        # (including the node limit) remains the diagram consumer's contract.
        return {**(self.raw.get('diagrams') or {}), **(section.get('diagram') or {})}

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
        from .product_context import bind
        from .reader_scope import validate_locations
        sections = bind(self, list(data.get("sections", []) or []))
        return validate_locations(sections, {section_output(s) for s in sections})

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
    for key in ('command', 'args'):
        value = agent_raw.get(key, [])
        if not isinstance(value, list) or any(not isinstance(a, str) or not a for a in value):
            raise ValueError(f'agent.{key}는 비어 있지 않은 문자열의 인자 목록이어야 합니다.')
    kind = str(agent_raw.get('kind', 'cli'))
    if kind not in ('cli', 'dry-run', 'response-bundle', 'ollama', 'openai-compatible'):
        raise ValueError('agent.kind는 cli, dry-run, response-bundle, ollama, openai-compatible 중 하나여야 합니다.')
    runner = str(agent_raw.get('runner', 'hermes'))
    if kind == 'cli' and runner not in ('hermes', 'opencode', 'claude', 'codex'):
        raise ValueError('agent.runner는 hermes, opencode, claude, codex 중 하나여야 합니다.')
    if 'allow_direct_api' in agent_raw and not isinstance(agent_raw['allow_direct_api'], bool):
        raise ValueError('agent.allow_direct_api는 boolean이어야 합니다.')

    ndk = dict(src.get("ndk_build", {}) or {})
    if ndk.get("project_dir"):
        ndk["project_dir"] = str(rel(ndk["project_dir"], "."))
    # PATH 의 이름(clang++)은 그대로 두고, 경로로 적은 NDK clang 만 설정 파일 기준으로 푼다.
    if ndk.get("clang") and any(sep in str(ndk["clang"]) for sep in "/\\"):
        ndk["clang"] = str(rel(ndk["clang"], "."))

    agent = AgentConfig(
        kind=kind,
        model=str(agent_raw.get("model", "" if kind == 'cli' else "qwen3.5:4b")),
        runner=runner,
        command=list(agent_raw.get('command', [])),
        args=list(agent_raw.get('args', [])),
        allow_direct_api=agent_raw.get('allow_direct_api', False),
        base_url=str(agent_raw.get("base_url", "http://localhost:11434")).rstrip("/"),
        max_input_chars=int(agent_raw.get("max_input_chars", 18000)),
        temperature=float(agent_raw.get("temperature", 0.1)),
        timeout_sec=int(agent_raw.get("timeout_sec", 300)),
        num_ctx=int(agent_raw.get("num_ctx", 0)),
        full_style_guides=bool(agent_raw.get("full_style_guides", False)),
        think=bool(agent_raw.get("think", False)),
        max_output_tokens=int(agent_raw.get("max_output_tokens", 1500)),
        response_dir=str(rel(agent_raw['response_dir'], '.')) if agent_raw.get('response_dir') else '',
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
