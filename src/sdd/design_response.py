"""Source-bound response decisions, with no file, CLI, Git or renderer access."""
from __future__ import annotations

import copy
import hashlib
import json
import re

from .evidence import topic_blocks, contract_text
from . import duplicates
from .manuscript import lint, describe
from .semantic import review as semantic_review, only_uncertainty, known_names
from .validate import extract_citations, check


def enabled(section):
    return section.get('design_generation') == 'llm'


def preflight(model, section):
    from .design_contracts import configuration_errors as validate_configuration
    errors = validate_configuration(section)
    if errors:
        raise ValueError(' / '.join(errors))
    tids = [t['id'] for t in section['design_topics']]
    if len(tids) != len(set(tids)):
        errors.append('설계 주제 id가 중복됐습니다.')
    for req in section['design_requirements']:
        if not isinstance(req.get('question'), str) or not req['question'].strip():
            errors.append(f"{req['id']}: 설계 질문이 비었습니다.")
    for topic in section['design_topics']:
        _, gaps = topic_blocks(model, section['id'], topic)
        errors.extend(gaps)
        if not topic.get('title') or not topic.get('question'):
            errors.append(f"{topic['id']}: 제목과 설계 질문이 필요합니다.")
        ids = [s['id'] for s in topic.get('sources', [])]
        if len(ids) != len(set(ids)):
            errors.append(f"{topic['id']}: 근거 id가 중복됐습니다.")
        for source in topic.get('sources', []):
            record = model.evidence.get(f"{section['id']}/{topic['id']}/{source['id']}", {})
            text = record.get('text')
            if not isinstance(text, str) or not text.strip() or digest(text) != record.get('sha256'):
                errors.append(f"{topic['id']}/{source['id']}: 발췌 본문과 해시가 일치하지 않습니다.")
    if errors:
        raise ValueError(' / '.join(errors))


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def quote_text(text):
    """Ignore whitespace and Doxygen line decoration, retaining source words."""
    return ' '.join(re.sub(r'^\s*\*(?: |$)', '', text, flags=re.M).split())


def source_passages(sources, *, whole_source=False, scopes=None):
    """Send each source once, with stable local IDs for verbatim paragraphs."""
    annotated, passages = {}, {}
    for source_id, text in sources.items():
        # Keep the original code, including leading multiplication/dereference
        # operators. Comment decoration is normalized only for quote comparison.
        chunks = [text] if whole_source or (scopes and source_id in scopes) else re.split(r'\n\s*\n', text)
        annotated[source_id] = []
        for index, chunk in enumerate(chunks):
            item = {'scope': scopes[source_id]} if scopes and source_id in scopes else {}
            item['text'] = chunk
            if len(quote_text(chunk)) >= 12:
                key = f'{source_id}:{index}'
                item['quote_id'] = key
                passages[key] = (source_id, chunk.strip())
            annotated[source_id].append(item)
    return annotated, passages


def resolve_passages(statements, passages):
    if not isinstance(statements, list):
        raise ValueError('statements는 설명 목록이어야 합니다.')
    result = []
    for statement in statements:
        if not isinstance(statement, dict):
            raise ValueError('설명은 JSON 객체여야 합니다.')
        if 'quote_id' not in statement:
            # Legacy quoted responses still undergo the same strict source check.
            result.append(statement)
            continue
        if (set(statement) - {'quote_id', 'text', 'covers', 'kind', 'evidence'}
                or not {'quote_id', 'text', 'covers', 'kind'} <= set(statement)):
            raise ValueError('quote_id 답변에는 text, covers, kind와 선택적 evidence만 함께 쓸 수 있습니다.')
        key = statement['quote_id']
        if not isinstance(key, str) or key not in passages:
            raise ValueError('제공되지 않은 quote_id입니다.')
        source_id, quote = passages[key]
        evidence = statement.get('evidence', [source_id])
        allowed = {sid for sid, _ in passages.values()}
        if (not isinstance(evidence, list) or any(not isinstance(sid, str) for sid in evidence)
                or len(evidence) != len(set(evidence)) or source_id not in evidence
                or not set(evidence) <= allowed):
            raise ValueError('evidence는 quote_id의 소스를 포함하는 제공된 소스 ID 목록이어야 합니다.')
        result.append({k: v for k, v in statement.items() if k != 'quote_id'} | {
            'quote': quote, 'evidence': evidence})
    return result


def response_schema(topic, passages=None):
    def ids(values):
        return {'type': 'array', 'minItems': 1, 'maxItems': len(values), 'uniqueItems': True,
                'items': {'type': 'string', 'enum': values}}
    # A checked part has exactly one required factual/contract answer. Offering
    # limitation here asks the model to choose an option the validator rejects,
    # especially for negative but fully sourced API obligations.
    # 실행 절차처럼 검증된 사실로 쓰면 안 되는 질문은 생성기가 종류를 고정한다. 모델이 고르지 않는다.
    kinds = [topic['_statement_kind']] if topic.get('_statement_kind') else ['behavior'] if (topic.get('_max_statements') == 1 and topic.get('answer_contract')) or topic.get('answer_contract', {}).get('basis') == 'contract' else ['behavior', 'limitation']
    statement = {'type': 'object', 'additionalProperties': False,
                 'required': ['text', 'quote_id', 'evidence', 'covers', 'kind'], 'properties': {
                     # C++ expressions such as request->_d()->cancel() and
                     # std::unique_ptr<Request> need angle brackets. HTML is
                     # rejected outside code spans by materialize().
                    # Let the JSON grammar escape quotes/backslashes normally.
                    # A character-class pattern here can emit unescaped code
                    # string literals in constrained Ollama responses.
                    'text': {'type': 'string', 'maxLength': 600},
                     'quote_id': {'type': 'string', **({'enum': list(passages)} if passages else {})},
                     'evidence': ids(sorted({sid for sid, _ in passages.values()}) if passages
                                     else [source['id'] for source in topic.get('sources', [])]),
                     'covers': ids(topic['covers']),
                     'kind': {'type': 'string', 'enum': kinds}}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['statements'],
            'properties': {'statements': {'type': 'array', 'maxItems': topic.get('_max_statements', 8), 'items': statement}}}


def materialize(model, section, answers, enforce_repeats=True):
    """Adapt generated statements to the existing source-bound contract validator."""
    resolved = copy.deepcopy(section)
    resolved.pop('design_generation')
    pinned = copy.copy(model)
    pinned.evidence = dict(model.evidence)
    if not isinstance(answers, dict) or set(answers) != {t['id'] for t in section['design_topics']}:
        raise ValueError('LLM 답변의 주제 집합이 설정과 다릅니다.')
    for topic in resolved['design_topics']:
        statements = answers[topic['id']]
        if not isinstance(statements, list) or not statements:
            raise ValueError(f"{topic['id']}: 생성된 설명이 없습니다.")
        seen = set()
        for st in statements:
            if not isinstance(st, dict) or set(st) - {'quote', 'text', 'evidence', 'covers', 'kind', 'part_id', 'subpart_id'}:
                raise ValueError('LLM 설명의 필드가 올바르지 않습니다.')
            for field in ('evidence', 'covers'):
                if not isinstance(st.get(field), list) or not st[field] or any(not isinstance(v, str) for v in st[field]):
                    raise ValueError(f'{field}는 비어 있지 않은 문자열 목록이어야 합니다.')
            if not set(st['covers']) <= set(topic['covers']):
                raise ValueError(f"{topic['id']}: 다른 주제의 질문에 답할 수 없습니다.")
            if not isinstance(st.get('text'), str) or not st['text'].strip():
                raise ValueError('LLM 설명이 비었습니다.')
            if '\n' in st['text'] or '\r' in st['text']:
                raise ValueError('각 설명은 줄바꿈 없는 한 문단이어야 합니다.')
            normalized = ' '.join(st['text'].split())
            if normalized in seen:
                raise ValueError('LLM 설명 문단이 중복됐습니다. 각 문단은 서로 다른 내용을 설명해야 합니다.')
            seen.add(normalized)
            quote = st.get('quote')
            if not isinstance(quote, str) or len(quote_text(quote)) < 12:
                raise ValueError('각 설명에는 직접 근거로 삼은 원문 구절 quote가 필요합니다.')
            original = [quote_text(model.evidence.get(f"{section['id']}/{topic['id']}/{ref}", {}).get('text', ''))
                        for ref in st['evidence']]
            if not any(quote_text(quote) in source for source in original):
                raise ValueError('quote가 연결된 소스 발췌의 실제 원문과 일치하지 않습니다: '
                                 + repr(quote) + '. 문장 부호·대소문자·코드를 바꾸거나 생략하지 마세요.')
            from .answer_contracts import sourced_check_obligation
            if (st.get('kind', 'behavior') == 'behavior' and only_uncertainty(st['text'])
                    and not sourced_check_obligation(st['text'], quote_text(quote))):
                raise ValueError('확인 필요 문장만으로 필수 질문의 답변을 대신할 수 없습니다.')
            if extract_citations(st['text']):
                raise ValueError('인용 위치는 생성기가 evidence에서 연결합니다. 본문에 직접 쓰지 마세요.')
            if re.search(r'(^\s*[#|<>]|```|!\[|\]\(|<!--)', st['text'], re.M):
                raise ValueError('LLM은 구조·링크·HTML 없이 설명 문단만 작성해야 합니다.')
            if re.search(r'<(?:/?[a-zA-Z]|!)', re.sub(r'`[^`]*`', '', st['text'])):
                raise ValueError('LLM 설명에 HTML을 넣을 수 없습니다.')
            if re.search(r'\\(?:ref|brief|param|retval|todo|context|threadsafe|class|fn)\b',
                         re.sub(r'`[^`]*`', '', st['text'])):
                raise ValueError('렌더링되지 않는 Doxygen 명령을 설명 문단에 복사할 수 없습니다. 문서 표식 대신 질문의 내용을 설명하세요.')
        from .answer_contracts import validate as validate_answer_contract
        validate_answer_contract(topic, statements)
        topic['statements'] = statements
        for source in topic['sources']:
            key = f"{section['id']}/{topic['id']}/{source['id']}"
            record = model.evidence[key]
            source['sha256'] = record['sha256']
            pinned.evidence[key] = {**record, 'selector': copy.deepcopy(source)}
    repeated = duplicates.statement_findings(model, section['id'], {t['id']: answers[t['id']] for t in section['design_topics']})
    if repeated and enforce_repeats:
        raise ValueError(' / '.join(repeated))
    pinned.repeated_findings = repeated
    return pinned, resolved


def source_names(model, records):
    """Only mark identifiers that actually occur in this topic's input excerpts."""
    names = known_names(model)
    names |= {name.rsplit('::', 1)[-1] for name in names}
    tokens = set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*', '\n'.join(records)))
    tokens |= {name.split('::', 1)[0] for name in tokens}
    return (names & tokens) | {name for name in tokens if '_' in name}


def normalize_answer(model, statements, sources):
    """Apply code typography without adding facts or rewriting model sentences."""
    if not isinstance(statements, list):
        return
    names = source_names(model, sources)
    template = re.compile(r'\b(?:[A-Za-z_]\w*::)*[A-Za-z_]\w*<[^<>\n;]+>')
    templates = set(template.findall('\n'.join(sources)))
    token = re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*(?:\(\))?')
    def mark(match):
        word = match[0]
        name = word.removesuffix('()')
        return f'`{word}`' if name in names or name.split('::', 1)[0] in names else word
    for statement in statements:
        if isinstance(statement, dict) and isinstance(statement.get('text'), str):
            parts = re.split(r'(`[^`]*`)', statement['text'])
            marked = ''.join(part if i % 2 else template.sub(
                lambda m: f'`{m[0]}`' if m[0] in templates else m[0], part)
                for i, part in enumerate(parts))
            parts = re.split(r'(`[^`]*`)', marked)
            statement['text'] = ''.join(part if i % 2 else token.sub(mark, part) for i, part in enumerate(parts))


def validate_answers(model, section, answers, allow_limited=False, enforce_repeats=True):
    from .design_contracts import enforce
    preflight(model, section)
    pinned, resolved = materialize(model, section, answers, enforce_repeats)
    report = enforce(pinned, resolved, allow_limited)
    for topic in resolved['design_topics']:
        text, _ = contract_text(pinned, section['id'], topic)
        blocks, _ = topic_blocks(pinned, section['id'], topic)
        allowed = set(extract_citations('\n'.join(b.text for b in blocks)))
        # Structured answers already require nonempty text, source and coverage.
        # A narrow question may have one short complete answer; do not pad it.
        findings = check(text, allowed, require=True, min_chars=1).notes
        names = source_names(model, [b.text for b in blocks])
        # materialize has already checked repeated statements with their exact
        # source records. Do not discard that evidence by applying the weaker
        # citation-only heuristic again; all other manuscript rules still apply.
        findings += describe(lint(text, names, check_duplicates=False))
        # Excerpts can contain standard-library types and aliases absent from
        # extracted ClassInfo. Accept only exact identifiers in this topic's
        # verified source; this does not add inheritance/relationship facts.
        identifiers = set(re.findall(r'[A-Za-z_]\w*(?:::[A-Za-z_]\w*)+', '\n'.join(
            pinned.evidence[f"{section['id']}/{topic['id']}/{source['id']}"]['text']
            for source in topic['sources'])))
        findings += semantic_review(text, model, allowed, source_identifiers=identifiers)
        if findings:
            raise ValueError(' / '.join(findings))
    report['scope'] = 'LLM answer coverage, current source bindings and structural checks; not semantic or runtime approval.'
    return pinned, resolved, report


def decode_unit(model, section, topic, raw, sources, passages):
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    data = json.loads(cleaned)
    if not isinstance(data, dict) or set(data) != {'statements'}:
        raise ValueError('statements만 가진 JSON 객체가 필요합니다.')
    maximum = topic.get('_max_statements', 8)
    if isinstance(data['statements'], list) and len(data['statements']) > maximum:
        raise ValueError(f"질문은 {maximum}문단 이내로 답해야 합니다.")
    data['statements'] = resolve_passages(data['statements'], passages)
    original_texts = [statement.get('text') for statement in data['statements']]
    if topic.get('_statement_kind'):
        for statement in data['statements']:
            statement['kind'] = topic['_statement_kind']
    if '_part_id' in topic:
        for statement in data['statements']:
            statement['part_id'] = topic['_part_id']
            if '_subpart_id' in topic:
                statement['subpart_id'] = topic['_subpart_id']
    # Parts share a page's typography rules. A source-backed class name can
    # occur in another part of the same topic (e.g. Fence versus fences).
    # These records only identify code names; drafting and grounding still use
    # the selected part's evidence, and no model words are added or changed.
    prefix = f"{section['id']}/{topic['id']}/"
    names_context = [record['text'] for key, record in model.evidence.items()
                     if key.startswith(prefix) and record.get('status') == 'available']
    normalize_answer(model, data['statements'], [*sources.values(), *names_context, topic['question'],
        *[value for source in topic['sources'] for value in source.get('scope', {}).values()]])
    candidate = {topic['id']: data['statements']}
    subset = {**section, 'design_topics': [topic], 'design_requirements': [
        r for r in section['design_requirements'] if r['id'] in topic['covers']]}
    # A topic covers only part of a reader profile. Check its prose
    # against the full section's requirements; coverage is checked
    # before calls and again after assembling every topic.
    from .reader_profiles import profile_errors
    errors = profile_errors({**section, 'design_topics': [
        {**topic, 'statements': data['statements']}]})
    if errors:
        raise ValueError(' / '.join(errors))
    subset.pop('reader_profile', None)
    subset.pop('reader_family', None)
    try:
        validate_answers(model, subset, candidate, allow_limited=bool(topic.get('_statement_kind')))
    except ValueError as exc:
        # Diagnose only an already-rejected answer. Inspect model text before
        # typography normalization and generated citations, without repairing it.
        for text in original_texts:
            if not isinstance(text, str):
                continue
            delimiter = 0
            for mark in re.finditer(r'(?<!\\)(?:\\\\)*(`+)', text):
                width = len(mark[1])
                if not delimiter:
                    delimiter = width
                elif width == delimiter:
                    delimiter = 0
            if delimiter:
                raise ValueError(
                    f'{exc} / 코드 표기의 백틱 쌍이 맞지 않을 수 있습니다. '
                    '식별자마다 여는 백틱과 닫는 백틱을 모두 쓰고, 설명 문장은 백틱 밖에 쓰세요.'
                ) from exc
        raise
    return candidate[topic['id']]


def _validate_retained(pinned, selected, retained):
    # Normalize only typography before revalidation, so an added code
    # marking rule does not discard otherwise source-identical answers.
    for topic in selected['design_topics']:
        prefix = f"{selected['id']}/{topic['id']}/"
        normalize_answer(pinned, retained[topic['id']], [record['text']
            for key, record in pinned.evidence.items()
            if key.startswith(prefix) and record.get('status') == 'available'])
    return validate_answers(pinned, selected, retained)

