"""같은 절 안에서 같은 근거를 같은 뜻으로 되풀이한 문장을 결정적으로 찾는다.

모델은 근거 구절마다 한 문장씩 쓰도록 요청받기 때문에, 질문이 겹치면 같은 구절에서 같은 사실을
말만 바꿔 두 번 쓴다. 이 모듈은 의미를 이해하지 않는다. 함수·대상·조건·결과가 명시적으로 다른
문장은 먼저 구별한다. 같은 근거 발췌를 인용하면서 내용어
(코드 식별자와 한글 낱말의 앞 두 글자)가 대부분 겹치는 문장만 중복 후보로 본다. 찾은 문장은 조용히
지우지 않고 재요청 사유로 돌려준다.
"""
from __future__ import annotations

import re
import hashlib
from typing import Iterable

from .validate import extract_citations

# 비교에서 뺄 서술·연결 표현. 문장마다 나오므로 겹쳐도 같은 사실의 증거가 아니다.
_FUNCTION_WORDS = frozenset(
    "합니다 입니다 있습니다 없습니다 하며 해야 있는 하는 수행 대한 통해 위해 경우 또는 그리고 이는 이를 해당 "
    "모든 각각 따라서 대해 같은 때문 하여 됩니다 되며 않습니다 않아야 사용하여 사용 호출 함수 이때 그러나 "
    "아니라 있으며 있을 없으며 한다 된다 하고 하면 하지 해서는".split())
_CITATION = re.compile(r"`[^`\n]*\.[A-Za-z]+:\d+`")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z0-9_]+)*(?:\(\))?")
_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*"
_SUBJECT = re.compile(
    rf"(?<![A-Za-z0-9_:])({_NAME})(\([^()\n]*\))?\s*"
    r"((?:의\s*)?구현(?:자|체)?\s*(?:는|은|이|가)|(?:을|를)\s*호출하는\s*(?:쪽|호출자)\s*(?:는|은|이|가)|(?:함수|메서드)\s*(?:는|은|이|가|에서|내부)|(?:는|은|이|가))(?=\s|$)")
_MEMBER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\([^()\n]*\))?(?:\.|->)[A-Za-z_][A-Za-z0-9_]*)+")
_OWNED_FIELD = re.compile(rf"({_NAME})\s*(?:(?:구조체|클래스)\s*)?의\s*({_NAME})\s*(?:필드|멤버)")
_VALUE = r"(?:true|false|nullptr|NULL|null|-E[A-Z0-9_]+|[+-]?\d+(?:\.\d+)?)"
_BOUND_VALUE = re.compile(
    rf"^\s*(?:의\s*)?(?:값|필드)?\s*(?:에는|은|는|이|가|을|를|에|도)?\s*"
    rf"(==|!=|=|is\s+not|is)?\s*({_VALUE})(?![A-Za-z0-9_])")
_CONDITION = re.compile(r"으면|이면|라면|다면|하면|되면|경우|(?:일|할|될|인|는)\s*때")
_VARIABLE_LABEL = re.compile(r"(?<![\w:])\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_CALL = re.compile(rf"(?<![A-Za-z0-9_:])({_NAME})\s*\(")
_ACTION = r'(?:합|한|하(?:며|고|여|는|도록)|해야|됩)'
_AFFIRMATIVE = r'(?:합니다|했습니다|한다|했다|하였다|해야\s*합니다|하여야\s*합니다)'
_RETURN_PREFIX = (
    rf'(?<![A-Za-z0-9_])({_VALUE})(?![A-Za-z0-9_])\s*(?:을|를)?\s*'
    r'(?:오류(?:\s*코드)?(?:을|를)?\s*)?반환')
_RETURN_CLAUSE = re.compile(_RETURN_PREFIX + _ACTION)
_CODE_NOISE = re.compile(
    r'//[^\n]*|/\*.*?(?:\*/|$)'
    r'|(?:u8|u|U|L)?R"(?P<delimiter>[^\s()\\]{0,16})\(.*?\)(?P=delimiter)"'
    r'|(?:u8|u|U|L)?"(?:\\.|[^"\\\n])*"'
    r"|(?:u8|u|U|L)?'(?:\\.|[^'\\\n])*'", re.S)
_CONTRACTS = (
    ('ownership-transfer', r'소유권.{0,50}(?:(?:전달|이동)(?:됩니다|되어야\s*합니다|된다)|넘어(?:갑니다|간다|가야\s*합니다))(?=\s*[,!?。.]|\s*$)',
     r'ownership.{0,100}(?:is|shall be|will be)\s+(?:passed|transferred|moved).{0,50}(?:caller|application)'),
    ('reference-storage', rf'참조.{{0,25}}저장(?:{_AFFIRMATIVE}|하며(?=\s*,))(?=\s*[,!?。.]|\s*$)',
     r'reference.{0,100}(?:is|are|will be)\s+(?:stored|kept)'),
    ('thread-safety', rf'스레드\s*안전(?:합니다|해야\s*합니다|하다|성을\s*(?:보장|유지){_AFFIRMATIVE})(?=\s*[,!?。.]|\s*$)',
     r'\\threadsafe\b|(?:is|shall be|must be)\s+thread.safe'),
    ('caller-synchronization', r'동기화(?:되어야|해야|하여야)\s*합니다(?=\s*[,!?。.]|\s*$)',
     r'(?:shall|must)\s+be\s+synchroni[sz]ed\s+by\s+(?:the\s+)?caller'),
)

# 기존 고정 문장 쌍을 가른 내용어 겹침 기준을 유지한다. 높은 겹침만으로 같은 사실이라고
# 단정하지 않도록, 명시된 함수·대상·조건·결과 차이는 별도로 확인한다.
SIMILARITY = 0.7
MINIMUM_SHARED = 6


def content_tokens(text: str) -> frozenset[str]:
    """문장의 내용어 집합: 코드 식별자(마지막 성분, 소문자)와 한글 낱말 앞 두 글자."""
    text = _CITATION.sub(" ", text)
    names = {m.removesuffix("()").rstrip("_").split("::")[-1].lower() for m in _IDENTIFIER.findall(text)}
    words = {w[:2] for w in re.findall(r"[가-힣]{2,}", text) if w not in _FUNCTION_WORDS}
    return frozenset(names | words)


def similar(left: str, right: str, *, threshold: float = SIMILARITY, minimum: int = MINIMUM_SHARED) -> bool:
    if _different_claims(left, right):
        return False
    a, b = content_tokens(left), content_tokens(right)
    shared = len(a & b)
    return bool(a and b) and shared >= minimum and shared / min(len(a), len(b)) >= threshold


def _same_function(left: str, right: str) -> bool:
    # A short spelling can name a qualified function; two explicit owners cannot.
    return left == right or (('::' not in left or '::' not in right)
                             and left.rsplit('::', 1)[-1] == right.rsplit('::', 1)[-1])


def _subject(text: str) -> str | None:
    for name, call, role in _SUBJECT.findall(text):
        if call or '::' in name or role.startswith(('함수', '메서드')) or '호출하는' in role or '구현' in role:
            return name
    return None


def _members(text: str) -> dict[str, tuple[str, str] | None]:
    members = {}
    for match in _MEMBER.finditer(text):
        name = re.sub(r"\([^()]*\)", '', match[0]).replace('->', '.')
        value = _BOUND_VALUE.match(text[match.end():])
        operator = '!=' if value and value[1] in ('!=', 'is not') else '=='
        members[name] = (operator, _value(value[2])) if value else None
    for match in _OWNED_FIELD.finditer(text):
        name = match[1] + '.' + match[2]
        value = _BOUND_VALUE.match(text[match.end():])
        operator = '!=' if value and value[1] in ('!=', 'is not') else '=='
        members.setdefault(name, (operator, _value(value[2])) if value else None)
    return members


def _same_member(left: str, right: str) -> bool:
    a, _, field_a = left.rpartition('.')
    b, _, field_b = right.rpartition('.')
    return field_a == field_b and _same_function(a, b)


def _value(value: str) -> str:
    return 'null' if value in ('null', 'NULL', 'nullptr') else value


def _outcomes(text: str) -> set[str]:
    # Different observable effects of one branch are separate facts. A sentence
    # naming both effects can still duplicate either; never discard it here.
    result = set()
    if re.search(r"로그.{0,20}(?:출력|기록)|(?:출력|기록).{0,20}로그", text):
        result.add('log')
    if re.search(r"반환[하합해됩된]", text):
        result.add('return')
    return result


def _different_claims(left: str, right: str) -> bool:
    left, right = (_CITATION.sub(' ', text).replace('`', '') for text in (left, right))
    a, b = _subject(left), _subject(right)
    if a and b and not _same_function(a, b):
        return True
    am, bm = _members(left), _members(right)
    shared_members = [(a, b) for a in am for b in bm if _same_member(a, b)]
    if am and bm and not shared_members:
        return True
    for a, b in shared_members:
        if am[a] and bm[b] and am[a] != bm[b]:
            return True
    av, bv = (set(_VARIABLE_LABEL.findall(text)) for text in (left, right))
    if av and bv and not av & bv:
        return True
    returns = rf"({_VALUE})\s*(?:을|를)?\s*(?:오류(?:\s*코드)?(?:을|를)?\s*)?반환"
    ar, br = ({_value(value) for value in re.findall(returns, text)} for text in (left, right))
    if ar and br and not ar & br:
        return True
    ao, bo = _outcomes(left), _outcomes(right)
    return bool(ao and bo and not ao & bo)


def _guard(quote: str) -> set[str] | None:
    if not isinstance(quote, str):
        return None
    quote = _code(quote)
    guards = []
    for match in re.finditer(r"\bif\s*\(", quote):
        start, depth, end = match.end(), 1, match.end()
        while end < len(quote) and depth:
            depth += (quote[end] == '(') - (quote[end] == ')')
            end += 1
        if depth == 0:
            guards.append(quote[start:end - 1])
    if len(guards) != 1:
        return None
    return set(_IDENTIFIER.findall(guards[0])) - {'true', 'false', 'nullptr', 'NULL', 'null'}


def _different_guards(left: dict, right: dict) -> bool:
    # One quote can cover many conditions. Only compare single-guard claims;
    # mixed claims still need review for their repeated portion.
    if any(len(_CONDITION.findall(row['text'])) != 1 for row in (left, right)):
        return False
    return _new_return_guard(left, right)


def _source_text(model, section_id: str, topic_id: str, statement: dict) -> str:
    """Novelty needs a real source-bound quote, not just a newly chosen token."""
    quote = statement.get('quote')
    if not isinstance(quote, str) or not quote.strip():
        return ''
    sources = []
    for ref in statement.get('evidence', []) or []:
        record = model.evidence.get(f'{section_id}/{topic_id}/{ref}', {})
        text = record.get('text')
        if (record.get('status') == 'available' and isinstance(text, str)
                and hashlib.sha256(text.encode('utf-8')).hexdigest() == record.get('sha256')):
            sources.append(text)
    return '\n'.join(sources) if any(quote.strip() in text for text in sources) else ''


def _source_calls(source: str) -> set[str]:
    code = _code(source)
    types = set(re.findall(r'\b(?:struct|class|union)\s+([A-Za-z_][A-Za-z0-9_]*)', code))
    names = set()
    for match in _CALL.finditer(code):
        start = max(code.rfind(ch, 0, match.start()) for ch in ';{}') + 1
        prefix = code[start:match.start()].strip()
        end, depth = match.end(), 1
        while end < len(code) and depth:
            depth += (code[end] == '(') - (code[end] == ')')
            end += 1
        arguments = code[match.end():end - 1]
        # Only clear expression statements count. Type prefixes, definition
        # heads, constructors, nested expressions and ambiguous syntax do not.
        receiver = r'[A-Za-z_][A-Za-z0-9_]*(?:(?:\.|->)[A-Za-z_][A-Za-z0-9_]*)*(?:\.|->)'
        assignment = r'[A-Za-z_][A-Za-z0-9_]*(?:(?:\.|->)[A-Za-z_][A-Za-z0-9_]*)*\s*='
        if (depth == 0 and code[end:].lstrip().startswith(';')
                and match[1].rsplit('::', 1)[-1] not in types
                and not re.search(r'(?:^|,)\s*(?:const\s+)?[A-Za-z_][A-Za-z0-9_:]*\s*[*&]+\s*[A-Za-z_][A-Za-z0-9_]*', arguments)
                and (not prefix or prefix == 'return' or re.fullmatch(receiver, prefix)
                     or re.fullmatch(assignment, prefix))):
            names.add(match[1])
    return names


def _code(source: str) -> str:
    """Mask comments/literals for code evidence; keep contract text separate."""
    # C++ joins escaped physical lines before it recognizes // comments.
    source = re.sub(r'\\\r?\n', '', source)
    code = _CODE_NOISE.sub(lambda match: re.sub(r'[^\n]', ' ', match[0]), source)
    # Incomplete or ambiguous literals cannot establish executable behavior.
    return '' if '"' in code or "'" in code else code


def _claimed_calls(text: str) -> set[str]:
    calls = set()
    for match in _CALL.finditer(text):
        end, depth = match.end(), 1
        while end < len(text) and depth:
            depth += (text[end] == '(') - (text[end] == ')')
            end += 1
        # A modifying phrase ("호출하는 것은 아닙니다"), negative obligation or
        # trailing qualification is not an unambiguous affirmative call claim.
        if depth == 0 and re.fullmatch(
                rf'\s*(?:함수|메서드)?(?:를|을)?\s*(?:호출|실행|사용){_AFFIRMATIVE}[.!?]?\s*', text[end:]):
            calls.add(match[1])
    return calls


def _return_condition(text: str) -> tuple[set[str], str] | None:
    text = _CITATION.sub(' ', text).replace('`', '')
    returns = list(_RETURN_CLAUSE.finditer(text))
    if len(returns) != 1:
        return None
    result = returns[0]
    prefix = re.split(r'[,!?]|\.(?:\s|$)', text[:result.start()])[-1]
    conditions = list(_CONDITION.finditer(prefix))
    if len(conditions) != 1:
        return None
    condition = _SUBJECT.sub('', prefix[:conditions[0].end()])
    return content_tokens(condition), _value(result[1])


def _new_return_guard(earlier: dict, later: dict) -> bool:
    """A separate return branch can add information to an otherwise mixed claim."""
    a, b = (_return_condition(row['text']) for row in (earlier, later))
    if not a or not b or a[1] != b[1] or not (a[0] - b[0] and b[0] - a[0]):
        return False
    ag, bg = (_guard(row.get('quote', '')) for row in (earlier, later))
    if not ag or not bg or ag & bg:
        return False
    for row, (_, value) in ((earlier, a), (later, b)):
        returns = re.findall(rf'\breturn\s+({_VALUE})(?![A-Za-z0-9_])\s*;', _code(row.get('quote', '')))
        if len(returns) != 1 or _value(returns[0]) != value:
            return False
    return True


def _affirmative_contract(pattern: str, text: str) -> bool:
    for match in re.finditer(pattern, text):
        # The original paragraph can qualify an otherwise positive sentence.
        # Uncertain follow-up denials do not establish an affirmative contract.
        if not re.search(r'(?:하지만|그러나|실제로|사실은|것은|것이|의무가|의무는)'
                         r'[^.!?]*(?:아니|아닙|않|없|안\s)', text[match.end():]):
            return True
    return False


def _novel_features(model, section_id: str, topic_id: str, later: dict, earlier: dict,
                    *, earlier_topic: str | None = None) -> set[str]:
    """Keep directional, source-backed additions; this is not a truth verdict."""
    source = _source_text(model, section_id, topic_id, later)
    if not source:
        return set()
    before, after = (row['text'].replace('`', '') for row in (earlier, later))
    context = later.get('_novelty_context', later['text']).replace('`', '')
    previous_names = {name.removesuffix('()') for name in _IDENTIFIER.findall(before)}
    code = _code(source)
    features = set()
    for name in _claimed_calls(after):
        if (not any(_same_function(name, old) for old in previous_names)
                and any(_same_function(name, claimed) for claimed in _claimed_calls(context))
                and any(_same_function(name, called) for called in _source_calls(source))):
            features.add('call:' + name)
    # Member mutations need both an asserted action and an assignment in code.
    members = set(_members(after)) | set(re.findall(r'(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*_(?![A-Za-z0-9_])', after))
    for name in members:
        expression = re.escape(name).replace(r'\.', r'(?:\.|->)')
        claim = (expression + rf'\s*(?:을|를|에|은|는|이|가)?\s*(?:초기화|설정|저장|갱신|대입)'
                 rf'(?:{_AFFIRMATIVE}|한\s*뒤\s*{_RETURN_PREFIX}{_AFFIRMATIVE})[.!?]?\s*$')
        if (not re.search(expression, before)
                and re.search(claim, after) and re.search(claim, context)
                and re.search(expression + r'\s*=(?!=)', code)):
            features.add('member-write:' + name)
    normalized_source = ' '.join(re.sub(r'(?m)^\s*\*\s?', '', source).split())
    for name, claim, proof in _CONTRACTS:
        if (_affirmative_contract(claim, after) and _affirmative_contract(claim, context)
                and not _affirmative_contract(claim, before)
                and re.search(proof, normalized_source, re.I)):
            features.add('contract:' + name)
    if (_new_return_guard(earlier, later)
            and _source_text(model, section_id, earlier_topic or topic_id, earlier)):
        features.add('return-guard:' + ','.join(sorted(_guard(later['quote']) or [])))
    return features


def _clip(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _repeats(model, section_id: str, topic_id: str, later: dict, earlier: dict,
             *, earlier_topic: str | None = None) -> bool:
    return (similar(later['text'], earlier['text']) and not _different_guards(later, earlier)
            and not _novel_features(model, section_id, topic_id, later, earlier,
                                    earlier_topic=earlier_topic))


def statement_findings(model, section_id: str, answers: dict[str, list[dict]],
                       *, only_after: dict[str, int] | None = None) -> list[str]:
    """설계 답변 문장 사이의 중복. 앞 문장과 뜻이 겹치는 뒤 문장을 반려 사유로 돌려준다.

    only_after 가 있으면 주제별로 그 개수 뒤에 온 문장만 뒤 문장으로 본다. 재요청 때 이미 통과한
    앞 문장끼리의 관계는 다시 지적하지 않고, 새로 추가한 문장만 검사하기 위해 쓴다.
    """
    def evidence_ids(topic_id: str, statement: dict) -> frozenset[str]:
        ids = set()
        for ref in statement.get("evidence", []) or []:
            record = model.evidence.get(f"{section_id}/{topic_id}/{ref}", {})
            ids.add(record.get("sha256") or f"{topic_id}/{ref}")
        return frozenset(ids)

    seen: list[tuple[str, int, dict, frozenset[str]]] = []
    findings: list[str] = []
    for topic_id, statements in answers.items():
        start = (only_after or {}).get(topic_id, 0)
        for index, statement in enumerate(statements or []):
            text = statement.get("text") if isinstance(statement, dict) else None
            if not isinstance(text, str):
                continue
            evidence = evidence_ids(topic_id, statement)
            if index >= start:
                # Keep paragraph-to-paragraph comparisons intact. Only the
                # paragraph's own sentences need this additional narrow check.
                sentences = []
                if evidence:
                    for number, sentence in enumerate(_sentences(text), 1):
                        current = {**statement, 'text': sentence, '_novelty_context': text}
                        for other_number, other in sentences:
                            if _repeats(model, section_id, topic_id, current, other):
                                findings.append(
                                    f"[의미 중복] {topic_id} {index + 1}번째 설명의 {number}번째 문장이 "
                                    f"같은 설명의 {other_number}번째 문장을 되풀이합니다: "
                                    f'"{_clip(sentence)}" ≈ "{_clip(other["text"])}". '
                                    "같은 설명 안에서 새 조건·호출·동작을 추가하지 않는 문장 반복을 줄입니다.")
                                break
                        sentences.append((number, current))
                for other_topic, other_index, other, other_evidence in seen:
                    other_text = other['text']
                    if evidence & other_evidence and _repeats(model, section_id, topic_id, statement, other,
                                                              earlier_topic=other_topic):
                        findings.append(
                            f"[의미 중복] {topic_id} {index + 1}번째 설명이 앞의 {other_topic} {other_index + 1}번째 "
                            f"설명과 같은 근거로 같은 내용을 되풀이합니다: \"{_clip(text)}\" ≈ \"{_clip(other_text)}\". "
                            "앞 설명에 없는 조건·예외·호출 책임만 쓰고, 새로 쓸 내용이 없으면 이 질문의 범위를 좁혀 다시 답합니다.")
                        break
            seen.append((topic_id, index, statement, evidence))
    return findings


def body_findings(body: str) -> list[tuple[int, str, str]]:
    """모델이 쓴 본문(문단 끝에 인용이 붙은 Markdown)에서 같은 인용을 공유하는 중복 문장을 찾는다.

    반환값은 (뒤 문장의 시작 행, 문장, 반려 사유)이다."""
    paragraphs: list[tuple[int, str, frozenset[str]]] = []
    fenced = False
    for number, block in _blocks(body):
        if block.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or re.match(r"^\s*(?:#|\||[-*+]\s|\d+\.\s)", block):
            continue
        citations = frozenset(extract_citations(block))
        if citations:
            paragraphs.append((number, block, citations))
    findings: list[tuple[int, str, str]] = []
    sentences: list[tuple[int, str, frozenset[str]]] = []
    for number, block, citations in paragraphs:
        for sentence in _sentences(block):
            for other_number, other, other_citations in sentences:
                if citations & other_citations and similar(sentence, other):
                    findings.append((number, sentence,
                                     f"{other_number}행의 문장과 같은 근거로 같은 내용을 되풀이합니다. "
                                     "앞 문장에 없는 조건·예외·호출 책임만 쓰고 같은 설명은 한 번만 씁니다."))
                    break
            sentences.append((number, sentence, citations))
    return findings


def _blocks(body: str) -> Iterable[tuple[int, str]]:
    start, lines = 0, []
    for number, line in enumerate(body.replace("\r\n", "\n").split("\n"), 1):
        if line.strip():
            if not lines:
                start = number
            lines.append(line)
        elif lines:
            yield start, "\n".join(lines)
            lines = []
    if lines:
        yield start, "\n".join(lines)


def _sentences(block: str) -> list[str]:
    text = _CITATION.sub(" ", " ".join(block.split()))
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 12]


def repeated_topics(model, section: dict, answers: dict[str, list[dict]]) -> list[str]:
    """재사용하려는 이전 답변 중, 앞 주제와 뜻이 겹쳐 다시 만들어야 하는 주제의 id.

    이전 원고에 중복이 남아 있으면 절 전체 검사가 마지막에 생성을 실패시키므로, 뒤쪽 주제를 재사용에서
    빼서 같은 실행 안에서 다시 쓰게 한다."""
    kept: dict[str, list[dict]] = {}
    dropped: list[str] = []
    for topic in section["design_topics"]:
        tid = topic["id"]
        if tid not in answers:
            continue
        trial = {**kept, tid: answers[tid]}
        skip = {key: len(value) for key, value in kept.items()}
        if statement_findings(model, section["id"], trial, only_after=skip):
            dropped.append(tid)
        else:
            kept[tid] = answers[tid]
    return dropped
