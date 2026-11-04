"""One fixed two-question input across prose/translation/graph dependencies.

Every process here is a controlled CLI double. Real selected-CLI measurements
are recorded separately; these archives never certify a public model run.
"""
import copy
import hashlib
import json
import subprocess
import time
import re
from dataclasses import asdict

import pytest
import yaml

from test_generated_design import generated, cli_units
from sdd.generate import Generator
from sdd.export_site import export_site
from sdd.site_build import verify_site
from sdd.translation import translate_missing
from sdd.document_metadata import split_frontmatter


CASES = [
    ('same', (0, 0, 0, 0)), ('question', (1, 1, 0, 0)),
    ('evidence', (1, 1, 1, 0)), ('translation', (0, 0, 0, 1)),
    ('visual', (0, 0, 1, 0)), ('ui', (0, 0, 0, 0)),
    ('validation-policy', (0, 0, 0, 0)), ('grounding-policy', (0, 2, 0, 0)),
    ('style', (2, 2, 2, 0)), ('cli-profile', (2, 2, 2, 2)),
    ('unknown-dependency', (2, 2, 0, 0)),
]


def exercise_fixed_input(cli_units, tmp_cfg, monkeypatch, change, expected):
    section, model, save, calls, state, factory = cli_units
    state['interrupt'] = False
    tmp_cfg.raw['review']['design_grounding'] = True
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    plans = [dict(id=f'{tid}-flow', topic=tid, kind='flow', generation='llm',
                  title=f'{tid} 호출', question=f'{tid}의 직접 호출은 무엇입니까?')
             for tid in ('stop', 'prepare')]
    def save_visuals():
        (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(
            dict(schema=1, sections={'device': plans}), allow_unicode=True), encoding='utf-8')
    save_visuals()
    catalog = dict(strings={'종료 설명': '', '준비 설명': ''})
    # Freeze the complete effective representative input before any execution
    # or mutation, independently of diagnostic identities under test.
    fixed = dict(section=section, model=asdict(model), agent=asdict(tmp_cfg.agent),
        review=tmp_cfg.raw['review'], site=tmp_cfg.raw.get('site', {}),
        visual_config=tmp_cfg.raw['visuals'], visual_plans=plans, catalog=catalog,
        assets={kind: {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in folder.rglob('*') if p.is_file()}
                for kind, folder in [('style',tmp_cfg.style_dir),('prompts',tmp_cfg.prompts_dir),
                                     ('templates',tmp_cfg.templates_dir)]})
    fixed_bytes = json.dumps(fixed, ensure_ascii=False, sort_keys=True).encode()
    fixed_sha256 = hashlib.sha256(fixed_bytes).hexdigest()
    tmp_cfg.build_dir.mkdir(parents=True, exist_ok=True)
    (tmp_cfg.build_dir/'fixed-representative-input.json').write_bytes(fixed_bytes)
    extra_calls = []
    changed_prose = [False]
    from sdd import cli_agent
    original_run = cli_agent.run
    def run(argv, **kwargs):
        prompt = kwargs['prompt']
        if 'Return only graph JSON' in prompt:
            request = json.loads(prompt.split('<user>\n', 1)[1].split('\n</user>', 1)[0]
                                 .split('\nPrevious native draft', 1)[0])
            first = 'stop' if 'stop' in request['question'] else 'prepare'
            second = 'cancelPending' if first == 'stop' else 'enable'
            quote = first + ':0'
            draft = dict(nodes=[dict(id='entry', symbol=first, label=first, label_en=first,
                                    shape='box', quote_ids=[quote]),
                                dict(id='call', symbol=second, label=second, label_en=second,
                                     shape='box', quote_ids=[quote])],
                         edges=[dict(**{'from': 'entry', 'to': 'call'}, label='호출', label_en='Calls',
                                     condition_ref='always', quote_ids=[quote])])
            extra_calls.append(('visual', first))
            value = draft
        elif 'Translate Korean' in prompt:
            extra_calls.append(('translation', 'unit'))
            value = dict(text='A changed source description.' if '수정한 종료 설명' in prompt else 'A source description.')
        else:
            result = original_run(argv, **kwargs)
            if changed_prose[0] and calls[-1] == 'stop':
                envelope = json.loads(result.stdout)
                body = json.loads(envelope['result'])
                body['statements'][0]['text'] = body['statements'][0]['text'].replace('종료 시','정지할 때')
                envelope['result'] = json.dumps(body,ensure_ascii=False)
                return subprocess.CompletedProcess(argv,result.returncode,json.dumps(envelope),result.stderr)
            return result
        return subprocess.CompletedProcess(argv, 0, json.dumps(dict(
            subtype='success', is_error=False, result=json.dumps(value, ensure_ascii=False))), '')
    monkeypatch.setattr(cli_agent, 'run', run)
    save()
    Generator(tmp_cfg, model, factory()).run()
    original_translation = translate_missing(tmp_cfg, catalog)
    original_meta,_ = split_frontmatter((tmp_cfg.sdd_dir/'device.md').read_text(encoding='utf-8'))
    original_site = export_site(tmp_cfg)
    original_outputs = {p.relative_to(original_site).as_posix(): p.read_bytes()
                        for p in original_site.rglob('*') if p.is_file()}
    archives = {p: p.read_bytes() for directory in ('prompts', 'translation-prompts')
                for archive in ('calls', 'cli')
                for p in (tmp_cfg.build_dir/directory/archive).rglob('*') if p.is_file()}
    before_calls, before_extra = len(calls), len(extra_calls)
    if change == 'question':
        changed_prose[0] = True
        section['design_topics'][0]['question'] += ' 진입점 책임도 확인하세요.'
    elif change == 'evidence':
        changed_prose[0] = True
        row = model.evidence['device/stop/stop']
        row['text'] += ' // source edit'
        row['sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
    elif change == 'translation':
        catalog['strings'] = {'수정한 종료 설명': '', '준비 설명': ''}
    elif change == 'visual':
        plans[0]['question'] += ' 호출 관계를 확인하세요.'
        save_visuals()
    elif change == 'ui':
        tmp_cfg.raw['site'] = dict(title='New presentation title')
    elif change == 'validation-policy':
        monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'changed': 'checks'})
    elif change == 'grounding-policy':
        monkeypatch.setattr('sdd.grounding.policy_hash', lambda: 'new-independent-review-policy')
    elif change == 'style':
        path = tmp_cfg.style_dir/'README.md'
        path.write_text(path.read_text(encoding='utf-8')+'\n13. 전역 집필 규칙 변경입니다.\n', encoding='utf-8')
    elif change == 'cli-profile':
        tmp_cfg.agent.args = ['--effort', 'medium']
    elif change == 'unknown-dependency':
        from sdd.design_checkpoint import store_for
        from sdd.cli_checkpoint import UnitStore
        def unknown(*args, **kwargs):
            store, identity = store_for(*args, **kwargs)
            identity['unregistered-semantic-input'] = 'unclassified-change'
            comparison = dict(comparison_scope=store.comparison_scope) if hasattr(store, 'comparison_scope') else {}
            return UnitStore(tmp_cfg, identity, **comparison), identity
        monkeypatch.setattr('sdd.design_checkpoint.store_for', unknown)
    save()
    start = time.perf_counter()
    Generator(tmp_cfg, model, factory()).run()
    translated = translate_missing(tmp_cfg, catalog)
    site = export_site(tmp_cfg)
    quality = verify_site(site)
    assert quality['manifest_verified'] and quality['broken_links'] == 0
    elapsed = time.perf_counter()-start
    fresh, extra = calls[before_calls:], extra_calls[before_extra:]
    actual = (len([c for c in fresh if c != 'grounding']), fresh.count('grounding'),
              sum(c[0] == 'visual' for c in extra), sum(c[0] == 'translation' for c in extra))
    assert actual == expected
    assert all(path.read_bytes() == raw for path, raw in archives.items())
    outputs = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*') if p.is_file()}
    assert outputs.keys() == original_outputs.keys()  # No unaffected page/asset disappears.
    for name in ('assets/reading.css','assets/site.js'):
        assert outputs[name] == original_outputs[name]
    def article(raw):
        values = re.findall(r'<article>(.*?)</article>',raw.decode('utf-8'),re.S)
        assert len(values) == 1
        return values[0]
    old_article,new_article = article(original_outputs['device.html']),article(outputs['device.html'])
    prepare_marker = '<h2 id="시작-준비">'
    assert old_article.count(prepare_marker) == new_article.count(prepare_marker) == 1
    def prepare_html(value):
        return value.split(prepare_marker,1)[1].split('<h2 ',1)[0]
    assert prepare_html(new_article) == prepare_html(old_article)
    if change not in ('question','evidence','visual'):
        # DESIGN.md places mutable generation/checkpoint metadata outside the
        # article. Compare the complete original visible article and sources.
        assert new_article == old_article
    else:
        assert new_article != old_article
    meta,body = split_frontmatter((tmp_cfg.sdd_dir/'device.md').read_text(encoding='utf-8'))
    old_design,new_design = original_meta['generated_design'],meta['generated_design']
    assert new_design['answers']['prepare'] == old_design['answers']['prepare']
    if change in ('question','evidence'):
        assert new_design['answers']['stop'] != old_design['answers']['stop']
        assert '정지할 때' in body and '정지할 때' in (site/'device.html').read_text(encoding='utf-8')
        assert new_design['topic_inputs']['stop'] != old_design['topic_inputs']['stop']
    else:
        assert new_design['answers']['stop'] == old_design['answers']['stop']
    old_graphs,new_graphs = original_meta['generated_visuals']['records'],meta['generated_visuals']['records']
    for key in ('draft','graph'):
        assert new_graphs['prepare-flow'][key] == old_graphs['prepare-flow'][key]
    if change in ('visual','evidence','style','cli-profile'):
        assert new_graphs['stop-flow']['input_fingerprint'] != old_graphs['stop-flow']['input_fingerprint']
    if change == 'visual':
        assert new_graphs['stop-flow']['graph']['question'] == plans[0]['question']
        assert new_graphs['stop-flow']['graph']['question'] != old_graphs['stop-flow']['graph']['question']
    if change == 'evidence':
        references=new_graphs['stop-flow']['graph']['nodes'][0]['evidence']
        assert references[0]['sha256'] == model.evidence['device/stop/stop']['sha256']
    if change == 'translation':
        assert '종료 설명' not in translated['strings']
        assert translated['strings']['수정한 종료 설명'] == 'A changed source description.'
        assert translated['strings']['준비 설명'] == original_translation['strings']['준비 설명']
    else:
        assert translated['strings'] == original_translation['strings']
    if change == 'style':
        assert new_design['style_policy'] != old_design['style_policy']
    if change == 'ui':
        assert 'New presentation title' in (site/'index.html').read_text(encoding='utf-8')
        assert new_design['topic_inputs'] == old_design['topic_inputs']
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    generation = max((r for r in runs if any(d['section'] == 'device' for d in r['documents'])),
                     key=lambda r: r['started_at'])
    decisions = generation.get('decisions', [])
    resolved = [d for d in decisions if d['stage'] == 'validated']
    plan = json.loads((tmp_cfg.build_dir/'publication-plan.json').read_bytes())
    if change == 'same':
        # Generation has its own timestamps/checkpoint annotations. Determinism
        # applies to two exports of the same validated manuscripts.
        outputs = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*') if p.is_file()}
        export_site(tmp_cfg)
        assert {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*') if p.is_file()} == outputs
    result = dict(
        fixed_input_sha256=fixed_sha256,
        transport='controlled CLI double; no actual inference', case=change,
        new_generation=actual[0], new_grounding=actual[1], new_visual=actual[2], new_translation=actual[3],
        seconds=elapsed, expected=expected, resolved=resolved, forecast=plan['units'],
        decisions=decisions, statuses=generation['documents'][0]['units'], quality=quality,
        original_archives_preserved=len(archives), site_files=len(original_outputs))
    (tmp_cfg.build_dir/f'issue242-{change}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


@pytest.mark.parametrize('change,expected', CASES)
def test_fixed_input_decisions_and_calls(cli_units, tmp_cfg, monkeypatch, change, expected):
    result = exercise_fixed_input(cli_units, tmp_cfg, monkeypatch, change, expected)
    codes = {c for d in result['decisions'] for c in d.get('reason_codes', [])}
    if change == 'question':
        assert 'question-changed' in codes
    if change == 'style':
        assert 'global-style-changed' in codes
    if change == 'cli-profile':
        assert 'cli-profile-changed' in codes
    if change == 'unknown-dependency':
        assert 'unregistered-dependency-changed' in codes
    for row in result['resolved']:
        assert row.get('human_review', 'pending') == 'pending'
        if row['unit'].startswith('device_'):
            status = result['statuses'][row['unit']]
            assert status == {'generate': 'newly-generated', 'reuse-checkpoint': 'checkpoint-reused',
                              'revalidate-checkpoint': 'checkpoint-revalidated',
                              'review-existing': 'checkpoint-revalidated'}[row['action']]
    if change in ('question', 'evidence', 'style', 'cli-profile', 'unknown-dependency'):
        assert result['forecast'][1]['action'] == 'resolve-after-dependencies'
        assert result['forecast'][1]['depends_on'] == ['device_stop']


def test_comparison_does_not_authorize_unknown_identity_reuse(cli_units, tmp_cfg):
    from sdd.cli_checkpoint import UnitStore
    _, model, _, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    checkpoint = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    original = checkpoint.read_bytes()
    payload = json.loads(original)['payload']
    changed = copy.deepcopy(payload['identity'])
    changed['unknown-policy'] = {'meaning': 'not registered'}
    store = UnitStore(tmp_cfg, changed, comparison_scope=payload.get('comparison_scope'))
    assert store.read() is None
    diagnostic = store.explain()
    assert diagnostic['comparison_only']
    assert diagnostic['reason_codes'] == ['unregistered-dependency-changed']
    assert diagnostic['comparisons'][0]['receipts_verified'] is False
    assert checkpoint.read_bytes() == original


def test_diagnostics_never_attribute_another_section_or_legacy_record(cli_units, tmp_cfg):
    from sdd.cli_checkpoint import UnitStore, checksum
    _, model, _, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    checkpoint = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    data = json.loads(checkpoint.read_bytes())
    payload = data['payload']
    changed = {**payload['identity'], 'unknown-policy': 'changed'}
    other = list(payload['comparison_scope'])
    other[1] = 'another-section'
    assert UnitStore(tmp_cfg, changed, comparison_scope=other).explain()['comparisons'] == []
    original_scope = payload.pop('comparison_scope')
    data['sha256'] = checksum(payload)
    checkpoint.write_text(json.dumps(data), encoding='utf-8')
    assert UnitStore(tmp_cfg, changed, comparison_scope=original_scope).explain()['comparisons'] == []


def test_optional_comparison_failure_cannot_add_a_reuse_gate(cli_units, tmp_cfg, monkeypatch):
    from sdd.cli_checkpoint import UnitStore, checksum
    from sdd.validation_stage import InputChanged
    _, model, _, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    checkpoint = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    payload = json.loads(checkpoint.read_bytes())['payload']
    store = UnitStore(tmp_cfg, payload['identity'], comparison_scope=payload['comparison_scope'])
    # An optional comparison can encounter an unrelated unavailable archive;
    # the verified requested hit continues through the original read() gate.
    (checkpoint.parent/'unrelated.json').write_text('{}', encoding='utf-8')
    explanation = store.explain()
    assert 'unrelated.json' in explanation['unavailable_comparisons']
    assert store.read() is not None
    malformed = dict(schema=1,payload={**payload, 'receipts': None})
    malformed['sha256'] = checksum(malformed['payload'])
    (checkpoint.parent/'unrelated.json').write_text(json.dumps(malformed), encoding='utf-8')
    assert 'unrelated.json' in store.explain()['unavailable_comparisons']
    assert store.read() is not None
    with monkeypatch.context() as missing:
        def unavailable():
            raise PermissionError('Optional comparison directory unavailable')
        missing.setattr(store, '_explain_comparisons', unavailable)
        assert 'diagnostic-unavailable-current-gates-required' in store.explain()['reason_codes']
        assert store.read() is not None
    with monkeypatch.context() as changed:
        def mutated(path):
            raise InputChanged('Required input mutated during validation')
        changed.setattr('sdd.cli_checkpoint.load_json', mutated)
        with pytest.raises(ValueError,match='Required input mutated'):
            store.read()  # Required receipt/checkpoint inputs remain fatal.


def test_validated_archive_replay_resolves_forecast_without_new_inference(generated, tmp_cfg, monkeypatch):
    from sdd.llm import Agent
    section, model, _, base = generated
    tmp_cfg.agent.model = 'synthetic-archive-model'
    calls = []
    def transport(self, *args):
        calls.append('synthetic HTTP response; no real inference')
        return json.dumps(dict(statements=[base.statement]), ensure_ascii=False)
    monkeypatch.setattr(Agent, '_ollama', transport)
    def agent():
        return Agent(tmp_cfg.agent, tmp_cfg.build_dir/'prompts')
    Generator(tmp_cfg, model, agent()).run()
    Generator(tmp_cfg, model, agent(), replay_http=True).run()
    assert len(calls) == 1
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    latest = max(runs, key=lambda r: r['started_at'])
    resolved = [d for d in latest['decisions'] if d['stage'] == 'validated']
    assert resolved[0]['action'] == 'replay-archive' and resolved[0]['origin']['receipt']
    assert not latest['calls']


def test_comparison_does_not_enlist_unrelated_archives_as_stage_inputs(cli_units, tmp_cfg):
    from sdd.cli_checkpoint import UnitStore
    from sdd.validation_stage import stage
    _, model, _, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    checkpoint = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    payload = json.loads(checkpoint.read_bytes())['payload']
    unrelated = checkpoint.parent/'diagnostic-only.json'
    unrelated.write_text('{}', encoding='utf-8')
    with stage() as inputs:
        store = UnitStore(tmp_cfg,payload['identity'],comparison_scope=payload['comparison_scope'])
        assert store.read() is not None
        assert store.explain()['comparisons'] == []  # No lookup snapshot for this exact hit.
        assert unrelated.resolve() not in inputs.files
        unrelated.write_text('{"historical":"changed"}',encoding='utf-8')
        inputs.verify()  # Required receipt/current-input mutations still fail elsewhere.


def test_retained_manuscript_forecast_keeps_unresolved_prior_dependency(cli_units, tmp_cfg):
    from sdd.impact import ImpactReport
    from sdd.publication_plan import prepare
    section, model, save, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    section['design_topics'][0]['question'] += ' 호출 책임도 설명하세요.'
    save()
    report = prepare(tmp_cfg,model,impact=ImpactReport(base='a'*40,head='a'*40,sections={'device':['question edit']}))
    later = report['units'][1]
    assert later['forecast'] == 'reuse-manuscript'
    assert later['action'] == 'resolve-after-dependencies'
    assert later['certainty'] == 'conditional' and later['depends_on'] == ['device_stop']


def test_decision_journal_serializes_concurrent_updates(tmp_cfg):
    from concurrent.futures import ThreadPoolExecutor
    from sdd.generation_run import Execution
    execution = Execution(tmp_cfg,object())
    def record(index):
        execution.decision(str(index),dict(action='revalidate-review',stage='validated'))
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(record,range(32)))
    saved = json.loads(execution.path.read_bytes())
    assert {row['unit'] for row in saved['decisions']} == {str(i) for i in range(32)}
    assert len(saved['decisions']) == len(execution.report['decisions']) == 32


def test_relabelled_checkpoint_cannot_hide_an_unknown_dependency_type_change(cli_units, tmp_cfg):
    from sdd.cli_checkpoint import UnitStore, checksum
    _, model, _, _, state, factory = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, factory()).run()
    original = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    saved = json.loads(original.read_bytes())
    old = copy.deepcopy(saved['payload']['identity'])
    old['unknown-policy'] = 1
    current = copy.deepcopy(old)
    current['unknown-policy'] = True  # Python equality hides this JSON type change.
    saved['payload']['identity'] = old
    saved['sha256'] = checksum(saved['payload'])
    store = UnitStore(tmp_cfg,current)
    # A checksum-valid archive cannot become current by moving it to the new
    # expected filename. The receipt is valid, but its policy input is stale.
    store.path.write_text(json.dumps(saved),encoding='utf-8')
    with pytest.raises(ValueError,match='identity'):
        store.read()
    from sdd.reuse_decision import differences
    assert differences({'unknown-policy':1},{'unknown-policy':True})[0]['path'] == 'unknown-policy'
