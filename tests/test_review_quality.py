import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from sdd.review_quality import validate_korean_review
from sdd import independent_review


class KoreanReviewQualityTests(unittest.TestCase):
    candidate = '요청을 받으면 대기열을 즉시 비운다. 실패하면 오류를 반환한다.'

    def test_missing_finding_cannot_attribute_a_source_only_call_to_the_draft(self):
        records = Path(__file__).resolve().parents[1] / 'docs/libcamera/records/stop-review-comparison'
        with ZipFile(records / 'grounded-first-evidence.zip') as series, ZipFile(records / 'evidence.zip') as original:
            decision = json.loads(series.read('block3/PF/full/decisions/S.json'))
            response = json.loads(series.read('block3/PF/' + decision['proof']['attempt'] + '/final.txt'))
            claim = response['claims'][4]
            draft = original.read('run/baseline/attempts/draft/S/attempt-000001/final.txt').decode('utf-8')
            self.assertEqual(claim['assessment'], 'missing')
            self.assertNotIn('doQueueRequests(camera)', draft)
            with self.assertRaisesRegex(ValueError, 'manuscript reference'):
                validate_korean_review({'claims': [claim]}, draft)

    def test_replays_both_observed_native_regressions(self):
        records = (Path(__file__).resolve().parents[1] / 'docs' / 'libcamera' / 'records'
                   / 'stop-review-comparison')
        with ZipFile(records / 'evidence.zip') as original, ZipFile(records / 'repeat-evidence.zip') as repeat:
            for unit, issue in [('A', 'Japanese kana'), ('S', 'verbatim substring')]:
                prefix = f'block3/PI/incremental/attempts/review/{unit}/attempt-000001'
                review = json.loads(repeat.read(prefix + '/final.txt'))
                draft = original.read(f'run/baseline/attempts/draft/{unit}/attempt-000001/final.txt')
                with self.subTest(unit=unit), self.assertRaisesRegex(ValueError, issue):
                    validate_korean_review(review, draft.decode('utf-8'))
                if unit == 'S':
                    stale_claims = [claim for claim in review['claims'] if claim['assessment'] == 'stale']
                    self.assertTrue(stale_claims)
                    with self.assertRaisesRegex(ValueError, 'verbatim substring'):
                        validate_korean_review({'claims': stale_claims}, draft.decode('utf-8'))

    def test_fresh_and_replayed_verdicts_use_the_same_quality_checks(self):
        verdicts = (
            ('supported', '要求を処理します。', 'Japanese kana'),
            ('missing', '원고는 `flush_shadow()`가 호출된다고 설명하지만 호출 조건은 밝히지 않는다.',
             'without a manuscript reference'),
        )
        cfg = SimpleNamespace(agent=SimpleNamespace(kind='cli', model='reviewer'), build_dir=Path('.'))
        request = {'system': '검토', 'user': self.candidate, 'response_schema': None}
        for assessment, claim, issue in verdicts:
            raw = json.dumps({'claims': [{'assessment': assessment, 'claim': claim,
                                          'correction': None, 'consequence': None}]})
            for replay in (False, True):
                runner = Mock()
                runner.chat.return_value = raw
                store = Mock()
                store.read.return_value = ({'raw': raw}, runner) if replay else None
                with self.subTest(assessment=assessment, replay=replay), patch.multiple(
                    independent_review, UnitStore=Mock(return_value=store), Capture=Mock(return_value=runner),
                    execution_identity=Mock(return_value={}),
                ), self.assertRaisesRegex(ValueError, issue):
                    independent_review.review_unit(cfg, Mock(), 'S', request, json.loads,
                                                   policy='quality', korean_candidate=self.candidate)
                store.write.assert_not_called()
                if not replay:
                    self.assertEqual(runner.chat.call_args.args[1].count(self.candidate), 1)

    def validate(self, *, candidate=None, **changes):
        claim = dict(assessment='missing', claim='재시도 조건에 대한 설명이 빠져 있다.',
                     correction='현재 코드는 `retry()`를 호출한다.',
                     consequence='독자가 오류 복구 시점을 알기 어렵다.')
        claim.update(changes)
        validate_korean_review({'claims': [claim]}, self.candidate if candidate is None else candidate)

    def test_rejects_kana_in_each_mixed_language_field(self):
        for field in ('claim', 'correction', 'consequence'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f'{field} contains Japanese kana'):
                self.validate(**{field: '현재 코드는 요청을 처리한다。処理を続けます。'})

    def test_rejects_all_japanese_and_backtick_wrapping(self):
        for text in ('要求を処理します。', '`要求を処理します`', '현재 코드의 결과는 `処理します`이다.'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'contains Japanese kana'):
                self.validate(claim=text, correction=text, consequence=text)

    def test_each_non_null_field_requires_hangul(self):
        for field in ('claim', 'correction', 'consequence'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f'{field} must contain Hangul'):
                self.validate(**{field: '`retry()` returns an error.'})
        self.validate(correction=None, consequence=None)

    def test_korean_prose_accepts_identifiers_and_ascii_f(self):
        for name in ('`bufferCompleted`', 'bufferCompleted', '`flush()`', 'flush', '`f`', 'f', '`문서_상태`'):
            with self.subTest(name=name):
                self.validate(claim=f'처리가 끝나면 {name} 호출 조건을 명시해야 한다.')
        self.validate(claim='후보정 단계가 시작되는 조건을 명시해야 한다.')

    def test_supported_and_stale_require_meaningful_verbatim_text(self):
        for assessment in ('supported', 'stale'):
            for claim in (None, '', '한다', '대기열을 곧바로 비운다.', '비운다. 실패하면 오류 반환',
                          '«실패하면 오류를 반환한다.»', '**실패하면 오류를 반환한다.**',
                          '실패하면 오류를 반환한다!', ' 실패하면 오류를 반환한다.'):
                with self.subTest(assessment=assessment, claim=claim), self.assertRaisesRegex(ValueError, 'claim must'):
                    self.validate(assessment=assessment, claim=claim)
            self.validate(assessment=assessment, claim='대기열을 즉시 비운다.')
            self.validate(assessment=assessment, claim='실패하면 오류를 반환한다.')
        self.validate(assessment='stale', claim='요청을 받으면 대기열을 즉시 비운다.',
                      correction='과거 코드는 즉시 비웠지만 현재 코드는 응답을 보낸 뒤에 비운다.')
        self.validate(candidate='완료 후 `flush()`를 호출한다.', assessment='supported',
                      claim='`flush()`를 호출한다.', correction=None, consequence=None)

    def test_missing_rejects_fabricated_attribution_in_every_free_field(self):
        examples = {
            'claim': '원고는 `flush_shadow()`가 호출된다고 설명하지만, 호출 조건은 충분히 밝히지 않는다.',
            'correction': '초안은 `flush_shadow()`를 호출한다고 설명하지만, 호출 조건도 명시해야 한다.',
            'consequence': '본문은 `flush_shadow()`가 호출된다고 설명하지만, 실패 시점을 알 수 없다.',
        }
        for field, text in examples.items():
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f'{field}.*manuscript reference'):
                self.validate(**{field: text})
        self.validate(claim='대기열을 비우기 시작하는 조건이 빠져 있다.',
                      correction='응답을 보낸 뒤 대기열을 비우는 경로를 명시해야 한다.',
                      consequence='대기열을 비우는 시점을 판단하기 어렵다.')

    def test_valid_quote_does_not_excuse_attribution_in_free_prose(self):
        for assessment in ('supported', 'stale', 'missing'):
            for field in ('claim', 'correction', 'consequence'):
                if assessment != 'missing' and field == 'claim':
                    continue
                text = ('«실패하면 오류를 반환한다.»는 재시도 조건을 특정하지 못한다. '
                        '후보 문서는 `flush_shadow()`를 호출한다고 설명하지만, 호출 시점은 빠져 있다.')
                changes = {'assessment': assessment}
                if assessment != 'missing':
                    changes['claim'] = '실패하면 오류를 반환한다.'
                changes[field] = text
                with self.subTest(assessment=assessment, field=field), self.assertRaisesRegex(
                    ValueError, f'{field}.*manuscript reference'
                ):
                    self.validate(**changes)

    def test_free_prose_rejects_manuscript_references_in_ordinary_markup(self):
        for manuscript in ('후보', '후보원고', '설계문서', '“원고”', '`초안`', '본문'):
            with self.subTest(manuscript=manuscript), self.assertRaisesRegex(ValueError, 'manuscript reference'):
                self.validate(claim=f'{manuscript}에는 재시도 횟수가 빠져 있다.')

    def test_free_prose_accepts_grounded_tagged_literals_with_korean_explanation(self):
        self.validate(claim='«실패하면 오류를 반환한다.»에서 오류를 반환하는 조건이 구체적이지 않다.')
        self.validate(candidate='본문 제목은 処理モード이다.', claim='«본문 제목은 処理モード»의 적용 범위를 명시해야 한다.',
                      correction='«処理モード»의 전환 조건을 명시해야 한다.',
                      consequence='현재 코드의 `state.処理モード`와 연결되는 조건을 판단하기 어렵다.')
        with self.assertRaisesRegex(ValueError, 'must contain Hangul'):
            self.validate(claim='«실패하면 오류를 반환한다.»')

    def test_free_prose_rejects_ungrounded_trivial_or_malformed_literal_tags(self):
        for literal in ('«오류가 나면 다시 시도한다.»', '«한다»', '«실패하면 오류를 반환한다.',
                        '««실패하면 오류를 반환한다.»»', '« 실패하면 오류를 반환한다.»'):
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, 'verbatim substring'):
                self.validate(correction=f'{literal}의 재시도 조건을 명시해야 한다.')
        with self.assertRaisesRegex(ValueError, 'Japanese kana'):
            self.validate(candidate='상태 이름은 処理モード이다.',
                          correction='“処理モード”의 전환 조건을 명시해야 한다.')
