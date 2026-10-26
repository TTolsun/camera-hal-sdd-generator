"""Optional lexical checks for narrowly scoped answers, not semantic approval.

Project-specific identifiers and known failure patterns belong in configuration.
Part identities are assigned by the generator, never supplied by the model.
"""
from __future__ import annotations

import re


BASES = {'contract', 'implementation', 'description', 'measurement', 'investigation'}
OBLIGATION = re.compile(r'[가-힣]야\s*(?:합니다|하며|하고|할)|해서는\s*안|하면\s*안|하지\s*말아야|할\s*의무')


def sourced_check_obligation(text, quote):
    """Do not misclassify a cited 'caller shall check' duty as missing evidence."""
    return (bool(re.search(r'\b(?:shall|must)\s+(?:check|verify)\b', quote, re.I))
            and bool(re.search(r'호출자[^.!?]*확인해야', text))
            and not re.search(r'확인할 수 없|확인되지 않|알 수 없|근거가 없|명시되지 않', text))


def configuration_errors(owner):
    if 'answer_contract' not in owner:
        return []
    rule = owner['answer_contract']
    if not isinstance(rule, dict) or not rule or set(rule) - {'basis', 'required_terms', 'reject_patterns'}:
        return ['answer_contract에는 basis, required_terms, reject_patterns만 지정할 수 있습니다.']
    errors = []
    if rule.get('basis') not in BASES:
        errors.append('answer_contract.basis는 contract, implementation, description, measurement, investigation 중 하나여야 합니다.')
    groups = rule.get('required_terms', [])
    if not isinstance(groups, list) or any(not isinstance(g, list) or not g or
            any(not isinstance(t, str) or not t.strip() for t in g) for g in groups):
        errors.append('required_terms는 비어 있지 않은 용어 대안 목록들의 목록이어야 합니다.')
    patterns = rule.get('reject_patterns', [])
    if not isinstance(patterns, list):
        return errors + ['reject_patterns는 pattern과 message 객체 목록이어야 합니다.']
    for item in patterns:
        if (not isinstance(item, dict) or set(item) != {'pattern', 'message'}
                or any(not isinstance(item[k], str) or not item[k].strip() for k in item)):
            errors.append('reject_patterns에는 비어 있지 않은 pattern과 message가 필요합니다.')
            continue
        try:
            re.compile(item['pattern'])
        except re.error:
            errors.append('reject_patterns의 정규식이 올바르지 않습니다.')
    return errors


def has_term(text, term):
    # Invalid must not satisfy Valid; stopDevice must not satisfy stop.
    pattern = re.escape(term)
    if re.match(r'[A-Za-z0-9_]', term):
        pattern = r'(?<![A-Za-z0-9_])' + pattern
    if re.search(r'[A-Za-z0-9_]$', term):
        pattern += r'(?![A-Za-z0-9_])'
    return bool(re.search(pattern, text))


def check(rule, statements, label):
    if not rule:
        return
    errors = []
    texts = [re.sub(r'`([^`]*)`', r'\1', st['text']) for st in statements]
    text = '\n'.join(texts)
    for alternatives in rule.get('required_terms', []):
        if not any(has_term(text, term) for term in alternatives):
            errors.append('필수 용어 누락: ' + ' / '.join(alternatives))
    if not any(st.get('kind', 'behavior') == 'behavior' for st in statements):
        errors.append('이 분할 질문에 근거가 있는 동작 또는 계약 답변이 필요합니다.')
    if rule['basis'] == 'contract':
        for st, prose in zip(statements, texts):
            if st.get('kind', 'behavior') == 'behavior' and not OBLIGATION.search(prose):
                errors.append('구현 의무는 해야 합니다/해서는 안 됩니다로 표현하세요. 관측된 구현이나 시험 보장으로 바꾸지 마세요.')
    if rule['basis'] == 'investigation':
        for st, prose in zip(statements, texts):
            if 'quote_id' in prose and 'quote_id' not in st.get('quote', ''):
                errors.append('조사 계획 본문에는 생성기 검증 키 quote_id를 쓰지 마세요. 소스의 관측 지점과 제안할 기록 항목을 설명하세요.')
    for item in rule.get('reject_patterns', []):
        if re.search(item['pattern'], text):
            errors.append(item['message'])
    if errors:
        raise ValueError(f'{label}: 답변 계약 검사: ' + ' / '.join(errors))


def validate(topic, statements):
    """Reapply checks to saved answers, including part coverage and evidence scope."""
    check(topic.get('answer_contract'), statements, topic['id'])
    parts = topic.get('parts', [])
    if not parts:
        if any('part_id' in st and st['part_id'] != topic.get('_part_id') for st in statements):
            raise ValueError('정의되지 않은 분할 질문의 답변입니다.')
        if any('subpart_id' in st and st['subpart_id'] != topic.get('_subpart_id') for st in statements):
            raise ValueError('정의되지 않은 세부 질문의 답변입니다.')
        return
    # Old parts without checks have no stored identities; preserve that format.
    if not any('answer_contract' in p or 'max_statements' in p or p.get('subquestions') for p in parts) and not any('part_id' in st for st in statements):
        return
    ids = {p['id'] for p in parts}
    if any(not isinstance(st.get('part_id'), str) or st['part_id'] not in ids for st in statements):
        raise ValueError('분할 질문의 답변 id가 없거나 정의되지 않았습니다.')
    for part in parts:
        selected = [st for st in statements if st['part_id'] == part['id']]
        subquestions = part.get('subquestions', [])
        maximum = len(subquestions) if subquestions else part.get('max_statements', 1 if part.get('answer_contract') else 2)
        sub_ids = [st.get('subpart_id') for st in selected]
        if (not 1 <= len(selected) <= maximum or
                (subquestions and (any(type(i) is not int for i in sub_ids)
                                   or sorted(sub_ids) != list(range(len(subquestions)))))
                or (not subquestions and any('subpart_id' in st for st in selected))):
            raise ValueError(f"{topic['id']}/{part['id']}: 각 질문의 답변 수와 세부 질문 식별자가 일치해야 합니다.")
        if any(not set(st['evidence']) <= set(part['sources']) for st in selected):
            raise ValueError(f"{topic['id']}/{part['id']}: 다른 분할 질문의 근거를 사용할 수 없습니다.")
        check(part.get('answer_contract'), selected, topic['id'] + '/' + part['id'])
