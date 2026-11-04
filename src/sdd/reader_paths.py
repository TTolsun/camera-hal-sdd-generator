"""Task and decision entrances projected from one set of canonical answers.

This is deterministic navigation, not a new LLM manuscript or human approval.
"""
from __future__ import annotations

import html
import re

import yaml

from .document_metadata import split_frontmatter
from .validation_stage import load_yaml


ASPECTS = {
    'work': {'reproduction', 'investigation', 'responsibility', 'verification'},
    'decision': {'problem', 'value', 'risk', 'options', 'decision'},
}
KINDS = {
    'fact': '관측된 사실 · 정적 소스 설명',
    'hypothesis': '가설 · 검증 전',
    'unmeasured': '미측정 효과',
    'decision_request': '결정 요청 · 승인 아님',
}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Reader paths: {name} must be nonempty')
    return value


def _line(value, name):
    value = _text(value, name)
    if '\n' in value or '\r' in value:
        raise ValueError(f'Reader paths: {name} must be one line')
    return value


def _items(value, name):
    if not isinstance(value, list) or not value:
        raise ValueError(f'Reader paths: {name} must be a nonempty list')
    return value


def _mapping(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise ValueError(f'Reader paths: expected fields {sorted(required)}')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', value):
        raise ValueError('Reader paths: IDs must be lowercase slugs')
    return value


def _plain(value):
    # Configuration is display text, never raw HTML, links or Markdown headings.
    escaped = html.escape(value).replace('\n', ' ').replace('|', '&#124;')
    return re.sub(r'([\\`*_{}\[\]()#!~])', r'\\\1', escaped)


def assemble(cfg, texts, sections, entries, approval_states, model, validate):
    data = load_yaml(cfg.root / cfg.site.reader_paths)
    _mapping(data, {'schema', 'ready', 'scope', 'limitations', 'required_inputs', 'claims', 'roles'})
    if type(data['schema']) is not int or data['schema'] != 1:
        raise ValueError('Reader paths: unsupported schema')
    inputs = [_line(v, 'required input') for v in _items(data['required_inputs'], 'required_inputs')]
    if data['ready'] is not True:
        raise ValueError('Reader paths: incomplete inputs; ' + '; '.join(inputs))
    scope = _line(data['scope'], 'scope')
    limits = _line(data['limitations'], 'limitations')
    if model is None:
        raise ValueError('Reader paths: current facts are required')
    commit = _text(model.meta.get('source_commit'), 'source_commit')
    by_id = {s['id']: (rel, s) for rel, s in sections.items()}
    checked = set()

    def source(ref, *, quote=False):
        _mapping(ref, {'section', 'topic'}, {'part'})
        section_id, topic_id = _id(ref['section']), _id(ref['topic'])
        if section_id not in by_id:
            raise ValueError('Reader paths: missing canonical section ' + section_id)
        rel, section = by_id[section_id]
        topics = [t for t in section.get('design_topics', []) if t['id'] == topic_id]
        if len(topics) != 1 or rel not in texts:
            raise ValueError('Reader paths: missing canonical topic ' + topic_id)
        if rel not in checked:
            validate(rel)
            checked.add(rel)
        meta, _ = split_frontmatter(texts[rel])
        if meta.get('source_commit') != commit:
            raise ValueError('Reader paths: facts and canonical source commits differ')
        title = topics[0]['title']
        # The normal renderer validates the actual destination anchor as well.
        anchor = re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', title.lower().strip()))
        link = f'[{_plain(title)}]({rel}#{anchor})'
        if not quote:
            if 'part' in ref:
                raise ValueError('Reader paths: part is only valid for a fact projection')
            return link
        part = _id(ref.get('part'))
        from .generated_design import verify
        from .render_profiles import for_page
        verify(model, section, texts[rel], cfg=for_page(cfg, rel))
        answers = meta.get('generated_design', {}).get('answers', {}).get(topic_id, [])
        selected = [a for a in answers if a.get('part_id') == part]
        if not selected or any(a.get('kind') != 'behavior' or not a.get('evidence') for a in selected):
            raise ValueError('Reader paths: fact needs evidence-bound behavior answers for its part')
        # Preserve every statement in the selected part, including conditions.
        paragraphs = '\n\n'.join('> ' + a['text'].replace('\n', '\n> ') for a in selected)
        return paragraphs + f'\n\n[전체 조건·상세 근거]({rel}#{anchor})'

    claims, claim_titles = {}, {}
    for claim in _items(data['claims'], 'claims'):
        _mapping(claim, {'id', 'title', 'kind', 'condition', 'sources'}, {'text', 'needed_inputs', 'options'})
        cid, kind = _id(claim['id']), claim['kind']
        if cid in claims or not isinstance(kind, str) or kind not in KINDS:
            raise ValueError('Reader paths: unique claim ID and known kind required')
        condition = _line(claim['condition'], 'condition')
        claim_titles[cid] = _plain(_line(claim['title'], 'claim title'))
        refs = _items(claim['sources'], 'sources')
        if kind == 'fact':
            if set(claim) & {'text', 'needed_inputs', 'options'} or len(refs) != 1:
                raise ValueError('Reader paths: facts project one canonical part; no authored replacement')
            answer = source(refs[0], quote=True)
        else:
            answer = _plain(_line(claim.get('text'), 'text'))
            needed = _items(claim.get('needed_inputs'), 'needed_inputs')
            answer += '\n\n| 구분 | 확인할 내용 |\n|---|---|\n'
            answer += '| 필요한 입력 | ' + '<br>'.join(_plain(_line(v, 'needed input')) for v in needed) + ' |\n'
            answer += '| 판단의 배경 근거(효과 측정값이 아님) | ' + ' · '.join(source(r) for r in refs) + ' |\n'
        if kind == 'decision_request':
            answer += '| 선택지 | ' + '<br>'.join(
                _plain(_line(v, 'option')) for v in _items(claim.get('options'), 'options')) + ' |\n'
        elif 'options' in claim:
            raise ValueError('Reader paths: only decision requests have options')
        claims[cid] = f'**{KINDS[kind]}**\n\n{answer}\n\n적용 조건·한계: {_plain(condition)}\n'

    roles = _items(data['roles'], 'roles')
    seen_roles, used, role_facts, pages = set(), set(), [], {}
    for role in roles:
        _mapping(role, {'id', 'title', 'questions'})
        rid = role['id']
        if not isinstance(rid, str) or rid not in ASPECTS or rid in seen_roles:
            raise ValueError('Reader paths: exactly one work and one decision role required')
        seen_roles.add(rid)
        title = _line(role['title'], 'title')
        questions = _items(role['questions'], 'questions')
        seen_questions, selected_facts, displayed = set(), set(), set()
        body = (f'# {_plain(title)}\n\n{_plain(scope)}\n\n**확인 한계:** {_plain(limits)}\n\n'
                '상세 설명과 소스 근거는 연결된 기준 문서에서 관리합니다. 아래 사실은 그 문서의 답변을 그대로 표시합니다. '
                '이 경로는 조직의 직책·승인 권한을 정의하지 않습니다.\n\n')
        for q in questions:
            _mapping(q, {'aspect', 'question', 'claims'})
            aspect = q['aspect']
            if not isinstance(aspect, str) or aspect not in ASPECTS[rid] or aspect in seen_questions:
                raise ValueError('Reader paths: unknown or duplicate role question')
            seen_questions.add(aspect)
            body += f"## {_plain(_line(q['question'], 'question'))} {{#question-{aspect}}}\n\n"
            for cid in _items(q['claims'], 'question claims'):
                if not isinstance(cid, str) or cid not in claims:
                    raise ValueError('Reader paths: unknown claim')
                used.add(cid)
                if next(c for c in data['claims'] if c['id'] == cid)['kind'] == 'fact':
                    selected_facts.add(cid)
                if cid in displayed:
                    body += f'[{claim_titles[cid]} · 같은 근거·조건 다시 보기](#claim-{cid})\n\n'
                else:
                    displayed.add(cid)
                    body += f'### {claim_titles[cid]} {{#claim-{cid}}}\n\n' + claims[cid] + '\n'
        if seen_questions != ASPECTS[rid]:
            raise ValueError('Reader paths: missing required role questions')
        role_facts.append(selected_facts)
        body += '## 적용·평가에 필요한 입력\n\n' + '\n'.join('- ' + _plain(v) for v in inputs)
        body += '\n\n사람 비작성자 평가·사내 HAL 검증·실제 임원 평가는 별도 확인이 필요합니다.\n'
        rel = f'reader-{rid}.md'
        if rel in texts or rel in sections or (cfg.sdd_dir / rel).exists():
            raise ValueError('Reader paths: output path conflicts with an existing manuscript')
        metadata = dict(generation_method='deterministic', source_commit=commit,
                        status='navigation-only', semantic_review='human-review-required')
        pages[rel] = '---\n' + yaml.safe_dump(metadata) + '---\n' + body
        approval_states[rel] = 'unreviewed'
        entries.append(('역할별 판단', title, rel))
    if (seen_roles != set(ASPECTS) or used != set(claims) or not set.intersection(*role_facts)
            or {c['kind'] for c in data['claims']} != set(KINDS)):
        raise ValueError('Reader paths: both roles must share facts and cover all four claim kinds without unused claims')
    texts.update(pages)
    links = '\n\n## 같은 근거에서 작업과 결정 찾기\n\n' + '\n'.join(
        f"- [{_plain(r['title'])}](reader-{r['id']}.md)" for r in roles) + '\n'
    # Keep the original home and its source-bound guide figures untouched.
    from .guide_visuals import headings
    first_heading = next(iter(headings(texts['index.md'])), None)
    position = first_heading.start() if first_heading else len(texts['index.md'])
    texts['index.md'] = texts['index.md'][:position] + links + '\n' + texts['index.md'][position:]
    approval_states['index.md'] = 'unreviewed'
