import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sdd import duplicates

DATA = json.loads((Path(__file__).parent / 'fixtures/source-bound-distinctions-162.json').read_text(encoding='utf-8'))


def case(name):
    return copy.deepcopy(next(r for r in DATA['records'] if r['case'] == name))


def fixture(name):
    r = case(name)
    source = r['source']
    row = dict(text=r['text'], quote=r['quote'], evidence=['x'])
    if name.startswith('indexed-channel'):
        rows = [row]
    else:
        before = {**r['earlier'], 'evidence': ['x']}
        rows = [before, row]
    return source, rows


def sync_context(source, original):
    context = source.get('context', {})
    if original in context.get('text', ''):
        context['text'] = context['text'].replace(original, source['text'], 1)
        context['sha256'] = hashlib.sha256(context['text'].encode()).hexdigest()
        delta = source['text'].count('\n') - original.count('\n')
        context['end_line'] += delta
        source['end_line'] += delta
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()


def findings(source, rows):
    model = SimpleNamespace(evidence={'s/t/x': source})
    return duplicates.statement_findings(model, 's', {'t': rows})


@pytest.mark.parametrize('name', ['indexed-channel-writes', 'indexed-channel-member-shorthand', 'unqualified-member-guard'])
def test_actual_native_false_positive_is_distinct_with_original_bound_sources(name):
    source, rows = fixture(name)
    assert hashlib.sha256(source['text'].encode()).hexdigest() == source['sha256']
    assert all(row['quote'] in source['text'] for row in rows)
    assert findings(source, rows) == []
    assert duplicates.SIMILARITY == .7 and duplicates.MINIMUM_SHARED == 6


@pytest.mark.parametrize('name', ['indexed-channel-writes', 'indexed-channel-member-shorthand', 'unqualified-member-guard'])
@pytest.mark.parametrize('change', ['missing-quote', 'unknown-quote', 'bad-hash', 'unavailable'])
def test_distinctions_need_authentic_bound_source(name, change):
    source, rows = fixture(name)
    if change == 'missing-quote':
        rows[-1].pop('quote')
    elif change == 'unknown-quote':
        rows[-1]['quote'] = 'not in the actual source'
    elif change == 'bad-hash':
        source['sha256'] = '0' * 64
    else:
        source['status'] = 'unavailable'
    assert findings(source, rows)


@pytest.mark.parametrize('wrapper', ['/*\n{}\n*/', '// {}', 'const char *note = R"text({})text";'])
def test_noncode_assignment_mentions_do_not_prove_distinct_writes(wrapper):
    source, rows = fixture('indexed-channel-writes')
    original = source['text']
    if wrapper == '// {}':
        source['text'] = '\n'.join('// ' + line for line in source['text'].splitlines())
        rows[0]['quote'] = source['text']
    else:
        source['text'] = wrapper.format(source['text'])
    sync_context(source, original)
    assert findings(source, rows)


def test_repeated_channel_pair_and_partial_overlap_still_fail():
    source, rows = fixture('indexed-channel-writes')
    first, second = duplicates._sentences(rows[0]['text'])
    rows[0]['text'] = first + ' ' + first
    assert findings(source, rows)
    second = second.replace('`gb`', '`gr`').replace('at("gb")', 'at("gr")')
    second = second.replace('lut->sets[s].gb_and_b[c].gb', 'lut->sets[s].r_and_gr[c].gr')
    rows[0]['text'] = first + ' ' + second
    assert findings(source, rows)


def test_different_index_names_do_not_prove_different_target_objects():
    source, rows = fixture('indexed-channel-writes')
    original = source['text']
    first = duplicates._sentences(rows[0]['text'])[0]
    other = first.replace('[s]', '[other]')
    source['text'] += '\n' + source['text'].replace('[s]', '[other]')
    sync_context(source, original)
    rows[0]['text'] = first + ' ' + other
    assert findings(source, rows)


@pytest.mark.parametrize('extra', ['bool enabled;', 'if (other.enabled) return;'])
def test_short_field_is_not_resolved_with_shadow_or_another_owner(extra):
    source, rows = fixture('unqualified-member-guard')
    source['text'] += '\n' + extra
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    assert findings(source, rows)


def test_repeated_boolean_guard_with_short_spelling_still_fails():
    source, rows = fixture('unqualified-member-guard')
    rows[1]['text'] = rows[0]['text'].replace('`frameContext.lsc.update`', '`update`').replace('`frameContext.lsc.enabled`', '`enabled`')
    rows[1]['quote'] = rows[0]['quote']
    assert findings(source, rows)


def test_negative_or_uncertain_boolean_text_is_not_a_new_positive_guard():
    source, rows = fixture('unqualified-member-guard')
    rows[1]['text'] = rows[1]['text'].replace('true이면', 'true가 아니면')
    model = SimpleNamespace(evidence={'s/t/x': source})
    assert not duplicates._different_bound_booleans(model, 's', 't', rows[1], rows[0])


def test_cross_topic_guard_comparison_uses_each_original_source_binding():
    source, rows = fixture('unqualified-member-guard')
    model = SimpleNamespace(evidence={'s/a/x': source, 's/b/x': source})
    assert duplicates.statement_findings(model, 's', {'a': [rows[0]], 'b': [rows[1]]}) == []


def test_opposite_flag_metadata_cannot_hide_a_repeated_effect():
    source, rows = fixture('unqualified-member-guard')
    for row in rows:
        row['text'] += ' 완료 함수를 호출합니다.'
    assert findings(source, rows)


def test_member_mentions_without_the_actual_return_tree_do_not_prove_a_guard():
    source, rows = fixture('unqualified-member-guard')
    source['text'] = 'void Lsc::prepare() { (void)frameContext.lsc.update; (void)frameContext.lsc.enabled; return; }'
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    for row in rows:
        row['quote'] = source['text']
    assert findings(source, rows)


def test_changed_comparison_direction_cannot_prove_the_original_return_claim():
    source, rows = fixture('unqualified-member-guard')
    source['text'] = source['text'].replace('abs_diff(ct, lastAppliedCt_) <', 'abs_diff(ct, lastAppliedCt_) >')
    rows[1]['quote'] = rows[1]['quote'].replace('abs_diff(ct, lastAppliedCt_) <', 'abs_diff(ct, lastAppliedCt_) >')
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    assert findings(source, rows)


def test_fully_qualified_negation_cannot_be_used_by_the_new_guard_proof():
    source, rows = fixture('unqualified-member-guard')
    rows[1]['text'] = rows[1]['text'].replace('`enabled`가 true이면', '`frameContext.lsc.enabled`가 true가 아니면')
    model = SimpleNamespace(evidence={'s/t/x': source})
    assert not duplicates._different_bound_booleans(model, 's', 't', rows[1], rows[0])


@pytest.mark.parametrize('replacement', ['0', 'set.at("b")[i]'])
def test_actual_rhs_must_match_each_claimed_channel_mapping(replacement):
    source, rows = fixture('indexed-channel-writes')
    original = source['text']
    source['text'] = source['text'].replace('set.at("r")[i]', replacement)
    rows[0]['quote'] = source['text']
    sync_context(source, original)
    assert findings(source, rows)


def test_guard_proof_is_independent_of_public_example_symbol_names():
    source, rows = fixture('unqualified-member-guard')
    replacements = {'Lsc::prepare': 'Processor::evaluate', 'frameContext.lsc.update': 'state.flags.update',
                    'frameContext.lsc.enabled': 'state.flags.enabled', 'utils::abs_diff': 'math::abs_diff',
                    'lastAppliedQuantizedCt_': 'previousQuantized', 'lastAppliedCt_': 'previousValue',
                    'quantizedCt': 'quantizedValue', 'kColourTemperatureQuantization': 'step'}
    for a, b in replacements.items():
        source['text'] = source['text'].replace(a, b)
        for row in rows:
            row['text'] = row['text'].replace(a, b)
            row['quote'] = row['quote'].replace(a, b)
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    assert findings(source, rows) == []


def test_named_assignment_instructions_do_not_assert_disjoint_physical_storage():
    source, rows = fixture('indexed-channel-writes')
    original = source['text']
    source['text'] = 'union Channels { int red; int blue; };\n' + source['text']
    sync_context(source, original)
    assert findings(source, rows) == []
    first = duplicates._sentences(rows[0]['text'])[0]
    rows[0]['text'] = first + ' ' + first
    assert findings(source, rows)


@pytest.mark.parametrize('change', ['missing', 'bad-hash', 'null', 'wrong-type'])
def test_assignment_owner_needs_authenticated_function_context(change):
    source, rows = fixture('indexed-channel-writes')
    if change == 'missing':
        source.pop('context')
    elif change == 'null':
        source['context'] = None
    elif change == 'wrong-type':
        source['context'] = 'not authenticated context'
    else:
        source['context']['sha256'] = '0' * 64
    assert findings(source, rows)


def test_assignment_claim_cannot_name_another_function_even_with_matching_code_elsewhere():
    source, rows = fixture('indexed-channel-writes')
    rows[0]['text'] = rows[0]['text'].replace('Lsc::prepare', 'Other::prepare')
    assert findings(source, rows)
    context = source['context']
    extra = '\nvoid Other::prepare() {\n' + source['text'] + '\n}\n'
    context['text'] += extra
    context['sha256'] = hashlib.sha256(context['text'].encode()).hexdigest()
    context['end_line'] += extra.count('\n')
    assert findings(source, rows)  # cited lines remain in Lsc::prepare


def test_same_flag_cannot_prove_reachable_opposite_nested_branches():
    source, rows = fixture('unqualified-member-guard')
    source['text'] = source['text'].replace('.enabled', '.update')
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    for row in rows:
        row['text'] = row['text'].replace('.enabled', '.update').replace('`enabled`', '`update`')
        row['quote'] = row['quote'].replace('.enabled', '.update')
    model = SimpleNamespace(evidence={'s/t/x': source})
    assert not duplicates._different_bound_booleans(model, 's', 't', rows[1], rows[0])


def test_unavailable_alternate_context_cannot_establish_the_claimed_owner():
    source, rows = fixture('indexed-channel-writes')
    alternate = copy.deepcopy(source)
    source.pop('context')
    alternate['status'] = 'unavailable'
    model = SimpleNamespace(evidence={'s/t/x': source, 's/t/alternate': alternate})
    rows[0]['evidence'].append('alternate')
    assert duplicates.statement_findings(model, 's', {'t': rows})


@pytest.mark.parametrize('wrapper', ['/*\n{}\n*/', 'R"fixture(\n{}\n)fixture";'])
def test_bare_quote_inside_a_context_comment_or_literal_is_not_executable(wrapper):
    source, rows = fixture('indexed-channel-writes')
    context = source['context']
    context['text'] = context['text'].replace(source['text'], wrapper.format(source['text']), 1)
    context['sha256'] = hashlib.sha256(context['text'].encode()).hexdigest()
    context['end_line'] += 2
    source['line'] += 1
    source['end_line'] += 1
    assert findings(source, rows)


def test_ambiguous_physical_line_splicing_cannot_prove_assignment_context():
    source, rows = fixture('indexed-channel-writes')
    original = source['text']
    source['text'] = original.replace('\n', '\\\n')
    rows[0]['quote'] = source['text']
    sync_context(source, original)
    assert findings(source, rows)


@pytest.mark.parametrize('transfer', ['throw 0;', 'goto after_guard;'])
def test_preceding_control_transfer_cannot_prove_the_return_tree(transfer):
    source, rows = fixture('unqualified-member-guard')
    source['text'] = source['text'].replace('if (!frameContext.lsc.update)', transfer + '\n\tif (!frameContext.lsc.update)', 1)
    source['text'] = source['text'].replace('params->use.acc_shd = 1;', 'after_guard: params->use.acc_shd = 1;')
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    assert findings(source, rows)


def test_conditional_compilation_does_not_prove_executable_assignment_context():
    source, rows = fixture('indexed-channel-writes')
    context = source['context']
    context['text'] = context['text'].replace(source['text'], '#if 0\n' + source['text'] + '\n#endif', 1)
    context['sha256'] = hashlib.sha256(context['text'].encode()).hexdigest()
    context['end_line'] += 2
    source['line'] += 1
    source['end_line'] += 1
    assert findings(source, rows)


def test_spliced_apparent_raw_string_terminator_cannot_expose_a_guard_tree():
    source, rows = fixture('unqualified-member-guard')
    source['text'] = ('const char *note = R"(' + chr(10) + ')' + chr(92) + chr(10)
                      + '"' + chr(10) + source['text'] + chr(10) + ')";')
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    assert findings(source, rows)


def test_return_tree_cannot_be_assembled_from_two_authenticated_source_records():
    source, rows = fixture('unqualified-member-guard')
    split = source['text'].index('/*\n\t\t * Add a threshold')
    first = {**source, 'file': 'first.cpp', 'text': source['text'][:split]}
    second = {**source, 'file': 'second.cpp', 'text': source['text'][split:]}
    for record in (first, second):
        record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    model = SimpleNamespace(evidence={'s/t/a': first, 's/t/b': second})
    for row in rows:
        row['evidence'] = ['a', 'b']
    assert duplicates.statement_findings(model, 's', {'t': rows})


def test_identical_text_in_different_files_is_not_one_bound_function_record():
    source, rows = fixture('unqualified-member-guard')
    other = {**copy.deepcopy(source), 'file': 'other.cpp'}
    model = SimpleNamespace(evidence={'s/t/a': source, 's/t/b': other})
    rows[0]['evidence'] = ['a']
    rows[1]['evidence'] = ['b']
    assert duplicates.statement_findings(model, 's', {'t': rows})


@pytest.mark.parametrize('reference', ['경계값', '해당 값'])
def test_comparison_limit_reference_names_the_immediately_preceding_bound(reference):
    source, rows = fixture('unqualified-member-guard')
    rows[-1]['text'] = rows[-1]['text'].replace('경계값', reference)
    assert findings(source, rows) == []
    rows[-1]['text'] = rows[-1]['text'].replace(reference + ' 이상이면', reference + ' 미만이면')
    assert findings(source, rows)  # reversing the complementary comparison remains rejected


@pytest.mark.parametrize('change', ['swapped-read', 'wrong-index', 'repeated-pair', 'extra-effect'])
def test_member_index_shorthand_retains_full_mapping_proof(change):
    source, rows = fixture('indexed-channel-member-shorthand')
    text = rows[0]['text']
    if change == 'swapped-read':
        text = text.replace('`set`의 `gb`와 `b`', '`set`의 `b`와 `gb`')
    elif change == 'wrong-index':
        text = text.replace('`i`번째', '`other`번째')
    elif change == 'repeated-pair':
        text = text.replace('lut->sets[s].gb_and_b[c]', 'lut->sets[s].r_and_gr[c]').replace('`gb`와 `b`', '`r`과 `gr`')
    else:
        text = text.replace('또한', '커널을 활성화하고 또한')
    rows[0]['text'] = text
    assert findings(source, rows)
