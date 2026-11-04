"""The actual explanation renderer must remain auditable per reader question."""
import gzip
import hashlib
import json

import pytest

from sdd.explanation import STAGES
from sdd.contract_render import SourceDetails
from sdd.config import section_output
from sdd.site_markdown import _render as render_markdown
from sdd.visual_audit import (apply_reviews, baseline_contract, inventory_page,
                              policy, retain_baseline_items)
from sdd.visuals import place, render
from test_design_contracts import contract
from test_visuals import visual


def staged_page(tmp_cfg, visual):
    section, model, graph, save = visual
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id=s, question=s, sources=['stop']) for s in STAGES]
    topic['explanation'] = [dict(id=s, title=s.title(), parts=[s]) for s in STAGES]
    graph['stage'] = 'conditions'
    save()
    body = '## ' + topic['title'] + '\n\nTopic introduction.\n\n'
    for stage in STAGES:
        body += '### ' + stage.title() + '\n\n' + stage + ' explanation.\n\n' + stage + ' details.\n\n'
        if stage == 'conditions':
            body += '#### Independent followup\n\nA separate reader question.\n\n'
    sources = SourceDetails()
    sources.links(model, section['id'], topic)
    body += sources.render()
    rendered = render(tmp_cfg, model, section)
    composed = place(body, rendered, section)
    for definition, _, mermaid in rendered:
        filename = section_output(section).removesuffix('.md') + '.' + definition['id'] + '.mmd'
        (tmp_cfg.root / filename).write_text(mermaid + '\n', encoding='utf-8', newline='\n')
    html, _, _ = render_markdown(composed, 'guide.md', {'guide.md'}, model,
                                  'https://example.test/source', model.meta['source_commit'])
    return '<html lang="ko"><article>' + html + '</article></html>'


def test_real_stage_figure_keeps_its_h3_owner_and_independent_h4_question(tmp_cfg, visual):
    page = staged_page(tmp_cfg, visual)
    rows = inventory_page(page, 'guide.html', policy(), source_commit='a' * 40, root=tmp_cfg.root)
    stage = next(row for row in rows if row['title'] == 'Conditions')
    caption = next(row for row in rows if row.get('role') == 'visual_title')
    followup = next(row for row in rows if row['title'] == 'Independent followup')
    assert caption['level'] == 4 and caption['parent'] == stage['id']
    assert [figure['id'] for figure in stage['figures']] == ['stop-flow']
    assert caption['figures'][0]['id'] == 'stop-flow'
    assert stage['paragraphs'] == ['conditions explanation.', 'conditions details.']
    assert followup['level'] == 4 and followup['parent'] == stage['id']
    assert followup['paragraphs'] == ['A separate reader question.']
    assert not followup['figures'] and followup.get('role') != 'visual_title'
    reviewed = apply_reviews(dict(items=rows, policy=policy(), errors=[]), dict(schema=1, items={}))
    assert next(row for row in reviewed['items'] if row['id'] == followup['id'])['status'] == 'unreviewed'


@pytest.mark.parametrize('owner,heading', [('h2', 'h4'), ('h3', 'h5'), ('h4', 'h4')])
def test_unsupported_marker_heading_does_not_hide_a_question(owner, heading):
    page = ('<article><' + owner + ' id="question">Question</' + owner + '><p>Answer.</p>'
            '<!-- sdd:visual:picture --><' + heading + ' id="caption">Caption</' + heading + '>'
            '<pre class="mermaid">flowchart TB\n a --> b</pre><!-- /sdd:visual:picture --></article>')
    with pytest.raises(ValueError, match='Ordinary section inside visualization'):
        inventory_page(page, 'guide.html', policy())


def test_second_heading_inside_stage_figure_is_still_rejected(tmp_cfg, visual):
    page = staged_page(tmp_cfg, visual).replace('<!-- /sdd:visual:stop-flow -->',
        '<h4 id="hidden">Hidden independent question</h4><!-- /sdd:visual:stop-flow -->')
    with pytest.raises(ValueError, match='Ordinary section inside visualization'):
        inventory_page(page, 'guide.html', policy())


def test_reader_h4_cannot_be_replaced_by_a_stage_figure_title(tmp_cfg, visual):
    page = staged_page(tmp_cfg, visual)
    original = inventory_page(page, 'guide.html', policy(), root=tmp_cfg.root)
    followup = next(row for row in original if row['title'] == 'Independent followup')
    raw = gzip.compress(json.dumps(dict(schema=1, items=original)).encode(), mtime=0)
    baseline = tmp_cfg.root / 'previous-items.json.gz'
    baseline.write_bytes(raw)
    tmp_cfg.raw['visual_audit'] = dict(baseline=dict(file=baseline.name, sha256=hashlib.sha256(raw).hexdigest()))
    # A real, rendered figure is not permission to relabel a retained question.
    caption = next(row for row in original if row.get('role') == 'visual_title')
    changed = page.replace('id="' + followup['anchor'] + '"', 'id="moved-followup"')
    changed = changed.replace('id="' + caption['anchor'] + '"', 'id="' + followup['anchor'] + '"')
    report = dict(items=inventory_page(changed, 'guide.html', policy(), root=tmp_cfg.root), errors=[])
    retain_baseline_items(report, baseline_contract(tmp_cfg, policy(tmp_cfg)))
    assert any('replaced by a figure title' in error for error in report['errors'])
