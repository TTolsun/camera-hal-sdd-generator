"""Generated next-step navigation, separate from source-backed runtime claims."""
from __future__ import annotations

import hashlib
import os
from pathlib import PurePosixPath
import re

from .config import section_output
from .document_metadata import split_frontmatter
from .trial_workspace import contained_path
from .validation_stage import read_bytes, read_text

FOOTER = '다음 단계: [{next_title}]({next_link})'


def section_next(section):
    nxt = section.get('next') or {}
    return str(nxt.get('title', '시스템 개요')), str(nxt.get('link', 'overview.md'))


def ordered_scenarios(cfg, model):
    ids = [row['id'] for row in cfg.scenarios()]
    known = [(sid, model.scenarios[sid]) for sid in ids if sid in model.scenarios]
    return known + sorted((sid, sc) for sid, sc in model.scenarios.items() if sid not in ids)


def _next(cfg, model, name, meta):
    section = cfg.section(meta.get('section'))
    if section is None:
        return None
    sid = meta.get('scenario_id')
    if section.get('kind') == 'per-scenario' and not section.get('index_only'):
        ordered = ordered_scenarios(cfg, model)
        for index, (key, _) in enumerate(ordered):
            if sid == key and name == f'scenarios/{key}.md':
                if index + 1 < len(ordered):
                    following = ordered[index + 1][1]
                    return following.title, f'scenarios/{following.id}.md'
                return '핵심 시나리오 목록', 'scenarios/index.md'
        return None
    return section_next(section) if name == section_output(section) else None


def _outside_fence(text):
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if not match:
            continue
        marker, suffix = match.groups()
        if fence is None:
            fence = marker
        elif marker[0] == fence[0] and len(marker) >= len(fence) and not suffix.strip():
            fence = None
    return fence is None


def checked_footer(cfg, model, name, meta, body):
    """Recognize only the canonical final link to a current local document.

    Custom hints, mixed prose, fragments and examples stay in the ordinary
    claim collector. A recognized missing/stale target fails before review.
    """
    expected = _next(cfg, model, name, meta)
    if expected is None or not read_text(cfg.templates_dir/'page.md').strip().endswith(FOOTER):
        return None
    title, target = expected
    if any(c in target for c in ('#', '?', ':', '\\')) or not target.endswith('.md'):
        return None
    path = contained_path(cfg.sdd_dir, target)
    relative = os.path.relpath(path, (cfg.sdd_dir/name).parent).replace('\\', '/')
    footer = FOOTER.format(next_title=title, next_link=relative)
    paragraphs = body.split('\n\n')
    indices = [i for i, p in enumerate(paragraphs) if p.strip()]
    if not indices:
        return None
    index = indices[-1]
    if paragraphs[index].rstrip('\n') != footer or not _outside_fence('\n\n'.join(paragraphs[:index])):
        return None
    if not path.is_file():
        raise ValueError(f'Generated next-step target missing: {name} -> {target}')
    raw = read_bytes(path)
    target_meta, target_body = split_frontmatter(raw.decode('utf-8').replace('\r\n', '\n'))
    if target_meta.get('source_commit') != model.meta.get('source_commit'):
        raise ValueError(f'Generated next-step target source commit mismatch: {target}')
    heading = re.search(r'^# (.+)$', target_body, re.M)
    if heading is None or heading[1] != title:
        return None
    return dict(document=name, paragraph=index, text=paragraphs[index], target=PurePosixPath(target).as_posix(),
                title=title, target_sha256=hashlib.sha256(raw).hexdigest(),
                assessment='generated navigation; current target exists; not a runtime contract verdict')


def link_topics(cfg, model, pages, sections, headings):
    """Add routes and optional memo guidance under verified topic headings.

    Resolve actual rendered headings, not guessed slugs. These routes convey
    navigation only and do not supply a runtime claim or a review verdict.
    Checkpoint text offers a copyable empty memo, never state restoration.
    """
    import html
    import posixpath
    from html.parser import HTMLParser
    from urllib.parse import quote
    import markdown

    routes = cfg.site.topic_links
    checkpoints = cfg.site.reading_checkpoints
    if not isinstance(routes, dict):
        raise ValueError('site.topic_links must map current Markdown pages to topics')
    if not isinstance(checkpoints, dict):
        raise ValueError('site.reading_checkpoints must map current Markdown pages to topic lists')
    for page, topics in checkpoints.items():
        path = PurePosixPath(page) if isinstance(page, str) else None
        if (path is None or path.is_absolute() or '..' in path.parts or path.as_posix() != page
                or not page.endswith('.md') or any(c in page for c in (':', '\\', '\n', '\r', '\0'))):
            raise ValueError('Reading checkpoint needs a current relative Markdown path')
        if (not isinstance(topics, list) or not topics
                or any(not isinstance(topic, str) or not topic.strip() or topic != topic.strip()
                       or '\n' in topic or '\r' in topic for topic in topics)):
            raise ValueError('Reading checkpoint needs a nonempty list of topic IDs')
        if len(topics) != len(set(topics)):
            raise ValueError('Reading checkpoint topic IDs must be distinct')
    if not routes and not checkpoints:
        return pages

    class Text(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts = []; self.ids = []; self.invalid_ids = False
        def handle_starttag(self, tag, attrs):
            ids = [value for key, value in attrs if key == 'id']
            self.invalid_ids |= len(ids) > 1
            self.ids.extend(ids)
        def handle_data(self, value):
            self.parts.append(value)

    def plain(value):
        parser = Text(); parser.feed(value)
        return ''.join(parser.parts).strip()

    def anchor(page, topic_id):
        if page not in pages or page not in sections:
            raise ValueError('Topic link page is not published: ' + str(page))
        if model is None or not model.meta.get('source_commit') or pages[page][1].get('source_commit') != model.meta['source_commit']:
            raise ValueError('Topic link source commit mismatch: ' + page)
        topics = [t for t in sections[page].get('design_topics', []) if t['id'] == topic_id]
        if len(topics) != 1:
            raise ValueError('Topic link needs one current topic: ' + page + '/' + str(topic_id))
        title = plain(markdown.markdown('## ' + topics[0]['title'], extensions=['attr_list']))
        def all_headings(values):
            for value in values:
                yield value
                yield from all_headings(value.get('children', []))
        matches = [h['id'] for h in all_headings(headings[page]) if h['level'] == 2 and plain(h['name']) == title]
        if len(matches) != 1:
            raise ValueError('Topic link heading missing or ambiguous: ' + page + '/' + topic_id)
        elements = Text(); elements.feed(pages[page][2])
        if elements.invalid_ids or elements.ids.count(matches[0]) != 1:
            raise ValueError('Topic link target ID is missing or duplicated: ' + page + '/' + topic_id)
        encoded = quote(matches[0], safe='')
        if encoded != matches[0] and encoded in elements.ids:
            raise ValueError('Topic link encoded fragment selects another element: ' + page + '/' + topic_id)
        return matches[0]

    # Plain display text enters the normal exact English catalog. No form,
    # storage, executable text, runtime claim or assessment is supplied here.
    checkpoint = (
        '\n<aside class="reading-checkpoint" aria-label="중단 전과 재개 후의 조사 메모">'
        '<p><strong>중단 전에 메모를 남기세요.</strong></p>'
        '<p>아래 틀을 복사해 빈칸을 채우고, 재개할 때 원래 메모와 대조하세요.</p>'
        '<ul>'
        '<li>제보된 증상과 조건을 적으세요: ____.</li>'
        '<li>직접 관측한 값과 확인 위치를 적으세요: ____.</li>'
        '<li>문서로 해석한 내용과 임시 가정을 적으세요: ____.</li>'
        '<li>아직 확인하지 못한 점을 적으세요: ____.</li>'
        '<li>다음 확인과 결과에 따른 분기를 적으세요: ____.</li>'
        '<li>근거 문서의 URL과 절 위치를 적으세요: ____.</li>'
        '</ul>'
        '<p>관측하지 않은 값은 미확인으로 남기고, 관측하려고 상태 변경 함수를 다시 호출하지 마세요.</p>'
        '<p>재개할 때 제보·관측·해석이 서로 섞이지 않았는지 원래 메모와 대조하세요.</p>'
        '</aside>\n')
    blocks = {}
    for page, topics in routes.items():
        if not isinstance(topics, dict) or not topics:
            raise ValueError('Topic links need a nonempty topic mapping')
        for topic_id, targets in topics.items():
            source_anchor = anchor(page, topic_id)
            if not isinstance(targets, list) or not targets:
                raise ValueError('Topic links need a nonempty target list')
            links, seen = [], set()
            for target in targets:
                if (not isinstance(target, dict) or set(target) != {'section', 'topic', 'label'}
                        or any(not isinstance(v, str) or not v.strip() or '\n' in v or '\r' in v for v in target.values())):
                    raise ValueError('Topic link needs explicit section, topic and plain label')
                destinations = [name for name, section in sections.items() if section.get('id') == target['section']]
                if len(destinations) != 1:
                    raise ValueError('Topic link section missing or ambiguous: ' + target['section'])
                destination = destinations[0]
                target_anchor = anchor(destination, target['topic'])
                key = (destination, target_anchor)
                if key in seen or key == (page, source_anchor):
                    raise ValueError('Topic links must be distinct and not point to themselves')
                seen.add(key)
                url = posixpath.relpath(str(PurePosixPath(destination).with_suffix('.html')), posixpath.dirname(page) or '.')
                href = quote(url, safe='/.-') + '#' + quote(target_anchor, safe='')
                links.append('<a href="' + html.escape(href, quote=True) + '">' + html.escape(target['label']) + '</a>')
            blocks.setdefault(page, {})[source_anchor] = '\n<p class="reading-links">함께 확인: ' + ' · '.join(links) + '</p>\n'
    for page, topics in checkpoints.items():
        for topic_id in topics:
            source_anchor = anchor(page, topic_id)
            existing = blocks.setdefault(page, {}).get(source_anchor, '')
            blocks[page][source_anchor] = existing + checkpoint

    result = dict(pages)
    for page, topics in blocks.items():
        additions = []
        content = pages[page][2]
        for source_anchor, block in topics.items():
            starts = list(re.finditer(r'<h2\b[^>]*\bid="([^"]+)"[^>]*>', content))
            owned = [i for i, match in enumerate(starts) if html.unescape(match[1]) == source_anchor]
            if len(owned) != 1:
                raise ValueError('Topic link source heading is not unique: ' + page)
            closing = content.find('</h2>', starts[owned[0]].end())
            if closing < 0:
                raise ValueError('Topic link source heading is not closed: ' + page)
            additions.append((closing + len('</h2>'), block))
        for position, block in sorted(additions, reverse=True):
            content = content[:position] + block + content[position:]
        title, meta, _, toc = pages[page]
        result[page] = (title, meta, content, toc)
    return result
