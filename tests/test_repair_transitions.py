"""Condition/evidence identity is explicit; neither wording nor pass counts suffice."""
import copy

from sdd.repair_diagnostics import compare_checks


def check(status, candidate='draft1', condition='roles-unsatisfied', **details):
    return dict(identity=dict(target='configuration', criterion='return-contract',
                              evidence=['sha-source'], condition=condition), status=status,
                candidate_sha256=candidate, verification='independent-source-review', **details)


def test_a_replaced_by_b_is_not_a_successful_repair():
    old = dict(a=check('error'), b=check('supported', condition='roles-satisfied'))
    new = dict(a=check('supported', 'draft2'), b=check('error', 'draft2', condition='roles-satisfied'))
    report = compare_checks(old, new)
    assert report['findings'] == dict(a='resolved', b='new-error')
    assert report['error_replacement'] and not report['successful_repair']


def test_different_finding_wording_keeps_the_same_evidence_condition():
    old, new = check('error', reason='null case omitted'), check('error', 'draft2', reason='failure return is absent')
    assert compare_checks(dict(a=old), dict(a=new))['findings']['a'] == 'maintained'


def test_similar_words_under_another_condition_do_not_match():
    old, new = check('error', reason='missing return'), check('error', condition='roles-satisfied', reason='missing return')
    report = compare_checks(dict(a=old), dict(a=new))
    assert report['findings']['a'] == 'newly-observed' and not report['successful_repair']


def test_missing_inspection_is_unjudged_even_if_other_checks_pass():
    report = compare_checks(dict(a=check('error'), b=check('supported')), dict(b=check('supported', 'draft2')))
    assert report['findings']['a'] == 'unjudged' and not report['successful_repair']


def test_unchanged_draft_opposite_verdict_is_a_conflict_not_resolution():
    report = compare_checks(dict(a=check('error')), dict(a=check('supported')))
    assert report['findings']['a'] == 'verdict-conflict' and not report['successful_repair']


def test_false_positive_requires_independent_additional_source_evidence():
    old = dict(a=check('error'))
    unbound = check('supported', disposition='no-change-needed', additional_evidence=[])
    assert compare_checks(old, dict(a=unbound))['findings']['a'] == 'verdict-conflict'
    bound = check('supported', disposition='no-change-needed', additional_evidence=['source-quote-and-condition'])
    assert compare_checks(old, dict(a=bound))['findings']['a'] == 'no-change-needed'
    bound['verification'] = 'generator-self-declaration'
    assert compare_checks(old, dict(a=bound))['findings']['a'] == 'verdict-conflict'


def test_unverified_claim_of_resolution_cannot_clear_an_error():
    new = check('supported', 'draft2')
    new.pop('verification')
    assert compare_checks(dict(a=check('error')), dict(a=new))['findings']['a'] == 'unjudged'


def test_evidence_change_is_not_silently_the_same_finding():
    new = copy.deepcopy(check('supported', 'draft2'))
    new['identity']['evidence'] = ['another-source']
    assert compare_checks(dict(a=check('error')), dict(a=new))['findings']['a'] == 'unjudged'
