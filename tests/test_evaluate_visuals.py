"""The real CLI replay must recognize guards escaped by the Mermaid renderer."""
import importlib.util
from pathlib import Path

import pytest

from sdd.mermaid_text import wrapped_html_label
from sdd.visuals import wrap_label


spec = importlib.util.spec_from_file_location(
    'evaluate_visuals', Path(__file__).resolve().parents[1] / 'tools/evaluate_visuals.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.mark.parametrize('guard', ['ret >= 0', 'ret < 0', 'ret == 0'])
def test_replay_checks_actual_rendered_condition_and_rejects_stale_guard(guard):
    text = wrapped_html_label(wrap_label(f'결과 전송 조건 · {guard} [true]', width=8))
    diagram = f'flowchart TB\n a -->|"{text}"| b\n'
    replay.assert_rendered_guard(diagram, guard)
    with pytest.raises(AssertionError, match='missing guard'):
        replay.assert_rendered_guard(diagram, 'ret > 100')


def test_translation_metadata_does_not_hide_a_stale_rendered_condition():
    diagram = 'flowchart TB\n%% sdd:translations {"ret #62;= 0": "ret #62;= 0"}\n a -->|"ret == 0"| b'
    with pytest.raises(AssertionError, match='missing guard'):
        replay.assert_rendered_guard(diagram, 'ret >= 0')


def test_replay_requires_cleanup_on_both_paths():
    draft = {'nodes': [{'id': f'n{i}', 'symbol': name} for i, name in enumerate(
        ['runPipes', 'sendResult', 'onFrameDone'])], 'edges': [
            {'from': 'n0', 'to': 'n1', 'condition_ref': 'c0:true'},
            {'from': 'n0', 'to': 'n2', 'condition_ref': 'c0:false'}]}
    with pytest.raises(AssertionError, match='after sending'):
        replay.assert_fixture_branches(draft)
    draft['edges'].append({'from': 'n1', 'to': 'n2', 'condition_ref': 'always'})
    replay.assert_fixture_branches(draft)
    draft['edges'][1]['condition_ref'] = 'c0:true'
    with pytest.raises(AssertionError, match='outside the true guard'):
        replay.assert_fixture_branches(draft)


def test_rendered_guard_must_belong_to_the_correct_edge():
    graph = {'edges': [{'from': 'n0', 'to': 'n1', 'label': '결과 전송 · ret >= 0 [true]'},
                       {'from': 'n0', 'to': 'n2', 'label': '정리 · ret >= 0 [false]'}]}
    lines = ['flowchart TB']
    for edge in graph['edges']:
        text = wrapped_html_label(wrap_label(edge['label'], width=8))
        lines.append(f'  v_{edge["from"]} -->|"{text}"| v_{edge["to"]}')
    diagram = '\n'.join(lines)
    replay.assert_rendered_edges(diagram, graph)
    # The correct guard remains on another edge and in translation metadata.
    stale = diagram.replace('v_n1', 'v_wrong')
    with pytest.raises(AssertionError, match='edges differ'):
        replay.assert_rendered_edges(stale, graph)


def test_condition_prefix_is_not_the_current_source_condition():
    text = wrapped_html_label(wrap_label('ret >= 01 [true]', width=8))
    with pytest.raises(AssertionError, match='missing guard'):
        replay.assert_rendered_guard(f'flowchart TB\n a -->|"{text}"| b', 'ret>=0')
    draft = {'edges': [{'from': 'a', 'to': 'b', 'condition_ref': 'c0:true'}]}
    graph = {'edges': [{'from': 'a', 'to': 'b', 'label': '전송 · ret >= 01 [true]'}]}
    with pytest.raises(AssertionError, match='current source condition'):
        replay.assert_graph_guards(draft, graph, 'ret>=0')
