"""A real supported but unnecessary benefit clause stays out of layer roles."""
import copy
import json
from pathlib import Path

import pytest

from sdd.answer_contracts import check
from sdd.config import load


def case():
    root = Path(__file__).parents[1]
    data = json.loads((root/'tests/fixtures/value-layer-overlap-165.json').read_text(encoding='utf-8'))
    cfg = load(root/'examples/libcamera/sdd.yaml')
    section = next(s for s in cfg.sections() if s['id'] == 'vendor-overview')
    topic = next(t for t in section['design_topics'] if t['id'] == 'value')
    return data, topic


def test_actual_layer_benefit_overlap_is_rejected_by_its_scope_contract():
    data, topic = case()
    assert data['independent_review']['classification'] == 'avoidable-duplicate'
    part = next(p for p in topic['parts'] if p['id'] == 'layers')
    rows = [r for r in data['actual_statements'] if r['part_id'] == 'layers']
    with pytest.raises(ValueError, match='앞의 정의 답변'):
        check(part['answer_contract'], rows, 'value/layers')


def test_unique_layer_roles_remain_valid_without_erasing_api_or_boundary_contracts():
    data, topic = case()
    part = next(p for p in topic['parts'] if p['id'] == 'layers')
    rows = copy.deepcopy([r for r in data['actual_statements'] if r['part_id'] == 'layers'])
    # Test-only contrast: remove the observed final repeated claim. This text is
    # never a replacement manuscript or a stored response for publication.
    assert ' Linux 기반 시스템에서 ' in rows[1]['text']
    rows[1]['text'] = rows[1]['text'].split(' Linux 기반 시스템에서 ', 1)[0]
    check(part['answer_contract'], rows, 'value/layers')
    assert len(rows) == 4 and '범위 밖' in rows[-1]['text']
    assert part['sources'] == ['stack', 'product-official-stack']


def test_the_source_backed_benefit_remains_required_and_allowed_in_definition():
    data, topic = case()
    part = next(p for p in topic['parts'] if p['id'] == 'what')
    rows = [r for r in data['actual_statements'] if r['part_id'] == 'what']
    assert len(rows) == 2 and '알고리즘' in rows[1]['text']
    check(part['answer_contract'], rows, 'value/what')
    assert part['sources'] == ['what', 'for', 'product-official-stack']
