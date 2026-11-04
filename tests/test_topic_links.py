"""Rendered navigation must resolve real, current topics and preserve prose."""
import copy
import json
import re
from urllib.parse import quote
import pytest
import yaml

from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.site_localization import display_strings, source_hash
from test_generated_design import generated, cli_units


@pytest.fixture
def linked(tmp_cfg, generated, request):
    section, model, _, agent = generated
    other = copy.deepcopy(section)
    other.update(id='other', title='다른 문서', output='nested/other.md')
    options = getattr(request, 'param', {})
    other['output'] = options.get('output', other['output'])
    other['design_topics'][0]['title'] = options.get('heading', other['design_topics'][0]['title'])
    other['next'] = {'title': section['title'], 'link': 'device.md'}
    model.evidence['other/stop/stop'] = copy.deepcopy(model.evidence['device/stop/stop'])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section, other]}, allow_unicode=True), encoding='utf-8')
    model.save(tmp_cfg.facts_path)
    Generator(tmp_cfg, model, agent).run()
    tmp_cfg.raw['site'] = {'topic_links': {'device.md': {'stop': [
        {'section': 'other', 'topic': 'stop', 'label': '자세한 종료 조건 확인'}]}}}
    return model


def test_topic_route_uses_current_heading_and_preserves_manuscripts(tmp_cfg, linked):
    before = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    out = export_site(tmp_cfg)
    content = (out / 'device.html').read_text(encoding='utf-8')
    target = (out / 'nested/other.html').read_text(encoding='utf-8')
    assert 'href="nested/other.html#' + quote('종료-책임') + '"' in content
    assert 'id="종료-책임"' in target
    assert content.index('class="reading-links"') > content.index('id="종료-책임"')
    assert all(p.read_bytes() == raw for p, raw in before.items())
    manifest = (out / 'site-manifest.json').read_bytes()
    export_site(tmp_cfg)
    assert (out / 'site-manifest.json').read_bytes() == manifest


@pytest.mark.parametrize('failure', ['missing-page', 'missing-topic', 'duplicate', 'self', 'bad-shape', 'empty', 'stale-target'])
def test_bad_topic_routes_preserve_the_previous_site(tmp_cfg, linked, failure):
    out = export_site(tmp_cfg)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    routes = tmp_cfg.raw['site']['topic_links']
    target = routes['device.md']['stop'][0]
    if failure == 'missing-page':
        routes['absent.md'] = routes.pop('device.md')
    elif failure == 'missing-topic':
        target['topic'] = 'absent'
    elif failure == 'duplicate':
        routes['device.md']['stop'].append(dict(target))
    elif failure == 'self':
        target['section'] = 'device'
    elif failure == 'bad-shape':
        target['url'] = 'https://example.invalid/'
    elif failure == 'empty':
        routes['device.md']['stop'] = []
    else:
        path = tmp_cfg.sdd_dir / 'nested/other.md'
        path.write_text(path.read_text(encoding='utf-8').replace('a' * 40, 'b' * 40), encoding='utf-8')
    with pytest.raises((ValueError, RuntimeError)):
        export_site(tmp_cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}


def test_duplicate_heading_is_not_guessed(tmp_cfg, cli_units):
    section, model, save, _, state, agent = cli_units
    section['design_topics'][1]['title'] = section['design_topics'][0]['title']
    state['interrupt'] = False
    save()
    Generator(tmp_cfg, model, agent()).run()
    tmp_cfg.raw['site'] = {'topic_links': {'device.md': {'stop': [
        {'section': 'device', 'topic': 'prepare', 'label': '시작 준비 확인'}]}}}
    with pytest.raises(ValueError, match='ambiguous'):
        export_site(tmp_cfg)


def test_topic_routes_join_the_normal_english_catalog(tmp_cfg, linked):
    """Synthetic translation fixtures verify routing, never model quality."""
    out = export_site(tmp_cfg)
    pages, units = {}, set()
    for path in out.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        pages[path.relative_to(out).as_posix()] = source_hash(text)
        units.update(display_strings(text))
    for row in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
        units.update(row[k] for k in ('title', 'page') if re.search('[가-힣]', row[k]))
    assert any('함께 확인' in unit for unit in units)
    assert any('자세한 종료 조건 확인' in unit for unit in units)
    catalog = {'schema': 1, 'pages': pages, 'strings': {
        unit: 'English section ' + ' '.join(re.findall(r'\{\{\d+\}\}', unit)) for unit in units}}
    path = tmp_cfg.root / 'english.json'
    path.write_text(json.dumps(catalog), encoding='utf-8')
    tmp_cfg.raw['site']['english_catalog'] = str(path)
    export_site(tmp_cfg)
    content = (out / 'en/device.html').read_text(encoding='utf-8')
    assert 'href="nested/other.html#' + quote('종료-책임') + '"' in content
    assert '함께 확인' not in content and '자세한 종료 조건 확인' not in content


@pytest.mark.parametrize('linked', [{'output': 'nested/other #%.md',
                                    'heading': '종료 책임 {#stop%?tag}'}], indirect=True)
def test_topic_routes_encode_paths_and_explicit_heading_ids_separately(tmp_cfg, linked):
    from sdd.next_steps import link_topics
    from sdd.site_markdown import _render
    names = {'device.md', 'nested/other #%.md'}
    pages, headings = {}, {}
    for name, text in [('device.md', '## 종료 책임\n'),
                       ('nested/other #%.md', '## 종료 책임 {#stop%?tag}\n')]:
        content, toc, tokens = _render(text, name, names, linked, '', linked.meta['source_commit'])
        pages[name] = ('Title', {'source_commit': linked.meta['source_commit']}, content, toc)
        headings[name] = tokens
    sections = {'device.md': tmp_cfg.section('device'), 'nested/other #%.md': tmp_cfg.section('other')}
    result = link_topics(tmp_cfg, linked, pages, sections, headings)
    content = result['device.md'][2]
    assert 'href="nested/other%20%23%25.html#stop%25%3Ftag"' in content
    assert 'id="stop%?tag"' in result['nested/other #%.md'][2]
