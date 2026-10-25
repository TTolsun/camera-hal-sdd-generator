"""Conservative structural checks, not a general natural-language truth oracle."""
from __future__ import annotations

import re

from .facts.model import KnowledgeModel
from .validate import extract_citations


# 확인되지 않았다고 말하는 문장. 이런 문장은 인용할 근거 자체가 없다.
_UNCERTAIN = re.compile(r"확인이 필요|확인할 수 없|확인되지 않|확인하지 못|명시되지 않|"
                        r"근거가 부족|근거가 없|보장하지 않|알 수 없|추출되지 않|존재하지 않")
_CHECK_OBLIGATION = re.compile(r"(?:호출자|구현자|구현체).*(?:확인해야)")


def only_uncertainty(paragraph: str) -> bool:
    """문단의 모든 문장이 "확인되지 않았다" 는 서술인지 판정한다.

    무엇이 확인되지 않았는지 적은 문단에는 인용할 위치가 없다. 그래도 인용을 요구하면 모델이
    관계 없는 위치를 붙이게 되고, 그 인용은 근거가 아니라 검사를 통과하기 위한 장식이 된다.
    사실을 하나라도 주장하는 문단은 그대로 인용을 요구한다.
    """
    sentences = [x for x in re.split(r"(?<=[.!?])\s+|\n", paragraph) if x.strip()]
    def uncertain(sentence):
        if _CHECK_OBLIGATION.search(sentence):
            return False
        clauses = [c for c in re.split(r'(?:하고|하며|되고|되며)[,\s]+', sentence) if c.strip()]
        if len(clauses) > 1:
            return all(uncertain(clause) for clause in clauses)
        # An absence in a branch guard is a concrete condition, not a claim
        # that the behavior is unknown ("파일이 존재하지 않으면 ... 반환합니다").
        matches = [m for m in _UNCERTAIN.finditer(sentence)
                   if not re.match(r'\s*(?:으면|면|을\s*때|는\s*경우)', sentence[m.end():])]
        if not matches:
            # "호출자는 설정을 확인해야 합니다" may itself be an explicit
            # source contract. Only an explicit future runtime investigation
            # is uncertainty; other obligations still require a citation.
            return bool(re.search(r'(?:기기|실행|실측|별도 시험|추가 조사|추후).*확인해야', sentence))
        # A caller's obligation can follow an independently stated operation.
        # Do not erase that factual clause merely because the same sentence
        # ends with "호출자는 ... 확인해야 합니다". It still requires evidence.
        return True
    return bool(sentences) and all(uncertain(x) for x in sentences)


def known_names(model: KnowledgeModel) -> set[str]:
    """설명에서 가리킬 수 있는 이름. 선언된 기반 클래스는 자체 ClassInfo 가 없을 수 있다."""
    names = set(model.classes) | {b for c in model.classes.values() for b in c.bases}
    return names | {n for r in model.relations for n in (r.source, r.target)}


def normalize_symbols(text: str, model: KnowledgeModel) -> str:
    """앞 네임스페이스를 뺀 한정 이름을 facts 의 전체 이름으로 되돌린다.

    소형 모델은 `libcamera::ipa::ipu3::IPAIPU3` 를 `ipa::ipu3::IPAIPU3` 로 줄여 쓴다. 뒤쪽이
    유일하게 일치하는 이름이 하나뿐일 때만 바꾸므로 가리키는 대상이 달라지지 않는다. 후보가
    여러 개이거나 없으면 손대지 않고, 검사에서 확인할 문제로 남긴다. 인용을 고치는
    `normalize_citations` 와 같은 원칙이다.
    """
    names = known_names(model)
    if not names:
        return text

    def fix(m: re.Match[str]) -> str:
        name = m.group(1)
        if "::" not in name or name in names:
            return m.group(0)
        candidates = [n for n in names if n.endswith("::" + name)]
        return f"`{candidates[0]}`" if len(candidates) == 1 else m.group(0)

    return re.sub(r"`([\w:]+)`", fix, text)


def review(text: str, model: KnowledgeModel, supplied: set[str], *, source_identifiers: set[str] | None = None) -> list[str]:
    findings = []
    # A declared base may be a typedef/alias without its own ClassInfo.
    known = known_names(model)
    def resolve(name: str) -> str | None:
        candidates = [n for n in known if n == name or ('::' not in name and n.rsplit('::', 1)[-1] == name)]
        return candidates[0] if len(candidates) == 1 else None
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        citations = set(extract_citations(paragraph))
        if not citations:
            if not only_uncertainty(paragraph):
                findings.append("설명 문단에 근거 인용이 없습니다.")
        elif citations - supplied:
            findings.append("현재 설명 입력에 제공되지 않은 위치를 인용했습니다: " + ", ".join(sorted(citations - supplied)))
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        names = re.findall(r"`([\w:]+)`", sentence)
        resolved = []
        for name in names:
            candidate = resolve(name)
            tail = sentence.split(f'`{name}`', 1)[1].split('`', 1)[0]
            absence = bool(re.search(r"존재하지 않|추출되지 않|포함되지 않|포함되어 있지 않", tail))
            if absence and candidate:
                findings.append(f"현재 facts에 있는 클래스를 없다고 서술했습니다: {name}")
            if "::" in name and not candidate and name not in model.functions and name not in (source_identifiers or set()):
                # Qualified methods and enumerators may not be class entities.
                owner = name.rsplit("::", 1)[0]
                if not absence and not any(n == owner or n.rsplit('::', 1)[-1] == owner for n in model.classes):
                    findings.append(f"추출 사실에서 확인되지 않는 한정 이름: {name}")
            if candidate:
                resolved.append(candidate)
        if "상속" in sentence and not re.search(r"없|않|아니|확인 필요|미확인", sentence):
            # Only bind an explicit subject/base phrase. A sentence can discuss
            # several independent relationships; its first name is not necessarily
            # the subject of the inheritance clause.
            pair = re.search(r'`([\w:]+)`\s*(?:은|는|이|가)\s*`([\w:]+)`\s*(?:을|를)\s*(?:직접\s*)?상속', sentence)
            subjects = resolved if len(resolved) == 1 or re.search(r'모두|이들도|둘 다', sentence) else []
            if pair:
                source, target = resolve(pair[1]), resolve(pair[2])
                subjects = [source] if source else []
                if source in model.classes and target and target not in model.classes[source].bases:
                    findings.append(f"추출되지 않은 직접 상속: {source} → {target}")
            for name in subjects:
                if name in model.classes and not model.classes[name].bases:
                    findings.append(f"추출된 기반 클래스가 없는 {name}에 상속을 주장했습니다.")
        if "필드 참조" in sentence and len(resolved) == 2 and not re.search(r"없|않|아니|확인 필요", sentence):
            if not any(r.source == resolved[0] and r.target == resolved[1] and r.type == "association" for r in model.relations):
                findings.append(f"추출되지 않은 필드 참조: {resolved[0]} → {resolved[1]}")
    return list(dict.fromkeys(findings))


def relation_facts(model: KnowledgeModel, names: set[str]) -> str:
    rows = ["직접 상속과 관계는 아래 추출 결과만 사용합니다. 관계가 없다는 사실은 실행 동작의 부재를 증명하지 않습니다."]
    for name in sorted(names):
        c = model.classes[name]
        cite = f" `{c.loc.cite()}`" if c.loc else ""
        rows.append(f"{name}: 직접 기반 클래스 = {', '.join(c.bases) or '(없음)'}{cite}")
    for source, target, kind in sorted({(r.source, r.target, r.type) for r in model.relations if r.source in names}):
        c = model.classes[source]
        cite = f" `{c.loc.cite()}`" if c.loc else ""
        rows.append(f"{source} → {target}: {kind}{cite}")
    return "\n".join(rows)


def structural_text(model: KnowledgeModel, names: set[str]) -> str:
    """Render structural assertions directly, without generative paraphrasing."""
    labels = {'association': '필드 참조', 'aggregation': '집합', 'composition': '합성', 'dependency': '의존'}
    paragraphs = []
    for name in sorted(names):
        cls = model.classes[name]
        citation = f" `{cls.loc.cite()}`" if cls.loc else ''
        bases = ', '.join(f'`{b}`' for b in cls.bases)
        text = (f'`{name}`의 추출된 직접 기반 클래스는 {bases}입니다.' if bases else
                f'`{name}`에는 추출된 직접 기반 클래스가 없습니다.')
        for target, kind in sorted({(r.target, r.type) for r in model.relations
                                   if r.source == name and r.target in names and r.type in labels}):
            text += f' `{target}`에 대한 {labels[kind]} 관계가 추출되었습니다.'
        if not cls.loc:
            text += ' 확인 필요: 선언 위치가 없습니다.'
        paragraphs.append(text + citation)
    return '\n\n'.join(paragraphs)
