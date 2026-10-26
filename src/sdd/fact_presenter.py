"""Select and present structural facts without model calls or output writes."""
from __future__ import annotations
import fnmatch
from collections import Counter
from typing import Any
from .facts.model import ClassInfo
from .matching import is_anonymous, matches_symbol, package_of, package_selected

_MAX_DEPS = 20


class FactPresenter:
    def __init__(self, model, package_depth):
        self.model, self.package_depth = model, package_depth

    def sorted_classes(self) -> list[ClassInfo]:
        return sorted(self.model.classes.values(), key=lambda x: x.name)

    def package_table(self, pats: list[str]) -> str:
        rows = ["| 패키지 | 클래스 수 | 대표 클래스 |", "|---|---|---|"]
        for name in sorted(self.model.packages):
            if not _pkg_selected(name, pats):
                continue
            p = self.model.packages[name]
            # 익명 구조체의 libclang 이름에는 파싱한 기계의 절대 경로가 들어간다. 대표 클래스에서 뺀다.
            named = [c for c in p.classes if not is_anonymous(c)]
            reps = ", ".join(f"`{c}`" for c in named[:5]) or "(이름 있는 클래스 없음)"
            rows.append(f"| `{name}` | {len(p.classes)} | {reps} |")
        return "\n".join(rows)

    def package_deps_table(self, pats: list[str]) -> str:
        # 패키지 표에 없는 이름은 의존 표에서도 뺀다. 두 표의 기준이 다르면 읽는 사람이
        # 표에 없는 패키지를 근거 없이 추측하게 된다.
        pkg_of = {name: c.package for name, c in self.model.classes.items() if c.package}
        edges: Counter[tuple[str, str, str]] = Counter()
        for r in self.model.relations:
            s, t = pkg_of.get(r.source), pkg_of.get(r.target)
            if s and t and s != t and _pkg_selected(s, pats) and _pkg_selected(t, pats):
                edges[(s, t, r.type)] += 1
        if not edges:
            return ""
        # 같은 방향의 상속과 필드 참조를 한 줄로 합친다. 종류마다 줄을 나누면 개요에서
        # 읽어야 할 줄이 두 배가 되고, 어느 방향이 굵은지가 보이지 않는다.
        pairs: dict[tuple[str, str], dict[str, int]] = {}
        for (src, dst, typ), n in edges.items():
            pairs.setdefault((src, dst), {"inheritance": 0, "association": 0})[typ] = n
        ordered = sorted(pairs.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
        rows = ["| 방향 | 상속 | 필드 참조 |", "|---|---|---|"]
        for (src, dst), counts in ordered[:_MAX_DEPS]:
            rows.append(f"| `{src}` → `{dst}` | {counts['inheritance']} | {counts['association']} |")
        if len(ordered) > _MAX_DEPS:
            rows.append("")
            rows.append(f"관계가 많은 순으로 {_MAX_DEPS} 개만 실었습니다. 나머지 {len(ordered) - _MAX_DEPS} 개 방향은"
                        " `facts.json` 의 `relations` 에 있습니다.")
        return "\n".join(rows)

    def entrypoint_table(self, pats: list[str]) -> str:
        rows = ["| 함수 | 위치 | 설명 |", "|---|---|---|"]
        for name in sorted(self.model.functions):
            if not matches_symbol(name, pats):
                continue
            fn = self.model.functions[name]
            loc = next((l for l in (fn.def_loc, fn.loc) if l), None)
            rows.append(f"| `{name}()` | {f'`{loc.cite()}`' if loc else '위치 없음'} | {fn.brief or '확인 필요'} |")
        return "\n".join(rows) if len(rows) > 2 else ""

    def entity_files(self, sec: dict[str, Any]) -> set[str]:
        """표에 file:line 이 없는 절(개요)에서도 근거 파일을 남기기 위해, 표에 오른 엔티티의 파일을 모은다."""
        facts = sec.get("facts", {})
        files: set[str] = set()
        pkg_pats = facts.get("packages") or []
        for name, p in self.model.packages.items():
            if any(fnmatch.fnmatch(name, pat) for pat in pkg_pats):
                for cname in p.classes:
                    c = self.model.classes.get(cname)
                    if c and c.loc:
                        files.add(c.loc.file)
        fn_pats = facts.get("functions") or []
        # 패키지 색인은 고른 패키지의 함수만 싣는다. 싣지 않은 함수의 파일을 근거로 적지 않는다.
        by_package = sec.get("kind") == "per-package" and bool(pkg_pats)
        for name, fn in self.model.functions.items():
            if matches_symbol(name, fn_pats):
                locs = [l for l in (fn.def_loc, fn.loc) if l]
                if by_package and not any(package_selected(package_of(l.file, self.package_depth), pkg_pats)
                                          for l in locs):
                    continue
                files.update(l.file for l in locs)
        sc = self.model.scenarios.get(str(facts.get("reading_order", "")))
        if sc:
            files.update(m.loc.file for m in sc.messages if m.loc)
        return files


def _pkg_selected(name: str, pats: list[str]) -> bool:
    return package_selected(name, pats)
