"""Canonical knowledge model.

clang-uml JSON, libclang 주석, compile DB, git 에서 뽑은 사실을 하나의 구조로 합친다.
모든 엔티티는 file:line 을 가지며, 이 값이 LLM 출력의 인용 검증 기준(citations)이 된다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Location:
    file: str
    line: int

    def cite(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class Method:
    name: str
    loc: Location | None = None        # 선언 위치 (보통 .h)
    brief: str = ""
    def_loc: Location | None = None    # 정의 위치 (보통 .cpp). libclang 이 채운다.


@dataclass
class FunctionInfo:
    """클래스 밖 자유 함수. HAL 진입점(camera_device_open 등)이 여기에 온다."""
    name: str
    loc: Location | None = None
    def_loc: Location | None = None
    brief: str = ""


@dataclass
class ClassInfo:
    name: str                      # 네임스페이스 포함 완전한 이름
    loc: Location | None = None
    package: str = ""              # 디렉터리 기준 패키지
    bases: list[str] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    brief: str = ""
    kind: str = "class"            # class | struct | enum | interface


@dataclass
class Relation:
    source: str
    target: str
    type: str                      # inheritance | association | aggregation | composition | dependency


@dataclass
class PackageInfo:
    name: str
    path: str = ""
    classes: list[str] = field(default_factory=list)


@dataclass
class Define:
    name: str
    value: str
    usages: list[Location] = field(default_factory=list)


@dataclass
class Message:
    src: str                       # participant display name
    dst: str
    name: str                      # 호출된 함수 이름
    loc: Location | None = None    # 호출 지점
    note: str = ""                 # 예: "virtual 후보" (정적으로 확정되지 않은 호출)


@dataclass
class Scenario:
    id: str
    title: str
    entry: str                     # from 함수 시그니처
    participants: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    mermaid: str = ""              # clang-uml 이 만든 Mermaid 본문
    unresolved: int = 0            # 정적으로 끊긴 호출 수 (virtual / function pointer)
    # 인자로 넘어간 메서드 수. 대상은 알지만 실행 시점과 스레드는 큐·신호 구현이 정한다.
    deferred: int = 0


@dataclass
class IncludeEdge:
    src: str
    dst: str


@dataclass
class KnowledgeModel:
    meta: dict[str, Any] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    packages: dict[str, PackageInfo] = field(default_factory=dict)
    defines: dict[str, Define] = field(default_factory=dict)
    scenarios: dict[str, Scenario] = field(default_factory=dict)
    includes: list[IncludeEdge] = field(default_factory=list)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- 조회 ------------------------------------------------------------

    def citations(self) -> set[str]:
        from ..validation_stage import current
        inputs = current()
        return inputs.memo(('citations', id(self)), self._citations) if inputs is not None else self._citations()

    def _citations(self) -> set[str]:
        """LLM 출력이 인용해도 되는 file:line 집합."""
        out: set[str] = set()
        for record in self.evidence.values():
            if record.get("status") == "available" and record.get("commit") == self.meta.get("source_commit"):
                out.add(f"{record['file']}:{record['line']}")
        for c in self.classes.values():
            if c.loc:
                out.add(c.loc.cite())
            for m in c.methods:
                for l in (m.loc, m.def_loc):
                    if l:
                        out.add(l.cite())
        for fn in self.functions.values():
            for l in (fn.loc, fn.def_loc):
                if l:
                    out.add(l.cite())
        for d in self.defines.values():
            for u in d.usages:
                out.add(u.cite())
        for s in self.scenarios.values():
            for m in s.messages:
                if m.loc:
                    out.add(m.loc.cite())
        return out

    def cited_files(self) -> set[str]:
        return {c.rsplit(":", 1)[0] for c in self.citations()}

    def classes_in_files(self, files: set[str]) -> list[ClassInfo]:
        """선언(.h) 또는 메서드 정의(.cpp)가 변경 파일에 있는 클래스."""
        out = []
        for c in self.classes.values():
            locs = [c.loc] + [l for m in c.methods for l in (m.loc, m.def_loc)]
            if any(l and l.file in files for l in locs):
                out.append(c)
        return out

    def scenarios_touching(self, files: set[str]) -> list[Scenario]:
        out = []
        for s in self.scenarios.values():
            if any(m.loc and m.loc.file in files for m in s.messages):
                out.append(s)
        return out

    # ---- 직렬화 ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        self._loaded_input = (path.resolve(), path.read_bytes())

    @classmethod
    def load(cls, path: Path) -> "KnowledgeModel":
        from ..validation_stage import read_bytes, load_json
        raw = read_bytes(path)
        model = cls.from_dict(load_json(path))
        model._loaded_input = (path.resolve(), raw)
        return model

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KnowledgeModel":
        def loc(x: dict[str, Any] | None) -> Location | None:
            return Location(**x) if x else None

        m = cls(meta=d.get("meta", {}))
        m.evidence = d.get("evidence", {})
        for name, c in (d.get("classes") or {}).items():
            m.classes[name] = ClassInfo(
                name=c["name"], loc=loc(c.get("loc")), package=c.get("package", ""),
                bases=list(c.get("bases", [])),
                methods=[Method(x["name"], loc(x.get("loc")), x.get("brief", ""), loc(x.get("def_loc")))
                         for x in c.get("methods", [])],
                brief=c.get("brief", ""), kind=c.get("kind", "class"),
            )
        for name, fn in (d.get("functions") or {}).items():
            m.functions[name] = FunctionInfo(name=fn["name"], loc=loc(fn.get("loc")),
                                             def_loc=loc(fn.get("def_loc")), brief=fn.get("brief", ""))
        m.relations = [Relation(**r) for r in d.get("relations", [])]
        for name, p in (d.get("packages") or {}).items():
            m.packages[name] = PackageInfo(name=p["name"], path=p.get("path", ""), classes=list(p.get("classes", [])))
        for name, df in (d.get("defines") or {}).items():
            m.defines[name] = Define(name=df["name"], value=df.get("value", "1"),
                                     usages=[Location(**u) for u in df.get("usages", [])])
        for sid, s in (d.get("scenarios") or {}).items():
            m.scenarios[sid] = Scenario(
                id=s["id"], title=s.get("title", sid), entry=s.get("entry", ""),
                participants=list(s.get("participants", [])),
                messages=[Message(x["src"], x["dst"], x["name"], loc(x.get("loc")), x.get("note", ""))
                          for x in s.get("messages", [])],
                mermaid=s.get("mermaid", ""), unresolved=int(s.get("unresolved", 0)),
                deferred=int(s.get("deferred", 0)),
            )
        m.includes = [IncludeEdge(**e) for e in d.get("includes", [])]
        return m


def relpath(file: str, source_root: Path) -> str:
    """절대 경로를 소스 루트 기준 posix 상대 경로로 바꾼다. 루트 밖이면 원본을 돌려준다."""
    try:
        return Path(file).resolve().relative_to(source_root.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(file).as_posix()
