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

    def test_fresh_and_replayed_verdicts_use_the_same_language_check(self):
        raw = json.dumps({'claims': [{'assessment': 'supported', 'claim': '要求を処理します。',
                                     'correction': None, 'consequence': None}]})
        runner = Mock()
        runner.chat.return_value = raw
        cfg = SimpleNamespace(agent=SimpleNamespace(kind='cli', model='reviewer'), build_dir=Path('.'))
        request = {'system': '검토', 'user': self.candidate, 'response_schema': None}
        for cached in (None, ({'raw': raw}, runner)):
            store = Mock()
            store.read.return_value = cached
            with self.subTest(replay=cached is not None), patch.multiple(
                independent_review, UnitStore=Mock(return_value=store), Capture=Mock(return_value=runner),
                execution_identity=Mock(return_value={}),
            ), self.assertRaisesRegex(ValueError, 'Japanese kana'):
                independent_review.review_unit(cfg, Mock(), 'S', request, json.loads,
                                               policy='quality', korean_candidate=self.candidate)
            store.write.assert_not_called()
            self.assertEqual(runner.chat.call_args.args[1].count(self.candidate), 1)

    def validate(self, **changes):
        claim = dict(assessment='missing', claim='재시도 조건에 대한 설명이 빠져 있다.',
                     correction='현재 코드는 `retry()`를 호출한다.',
                     consequence='독자가 오류 복구 시점을 알기 어렵다.')
        claim.update(changes)
        validate_korean_review({'claims': [claim]}, self.candidate)

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

    def test_ordinary_identifier_in_korean_prose_is_valid(self):
        self.validate(claim='버퍼 처리가 끝나면 `bufferCompleted`를 보낸다.')
        self.validate(claim='버퍼 처리가 끝나면 bufferCompleted를 보낸다.')

    def test_stale_requires_meaningful_verbatim_text(self):
        for claim in ('대기열을 곧바로 비운다.', '비운다. 실패하면 오류 반환', '한다', ''):
            with self.subTest(claim=claim), self.assertRaisesRegex(ValueError, 'claim must'):
                self.validate(assessment='stale', claim=claim)
        self.validate(assessment='stale', claim='요청을 받으면 대기열을 즉시 비운다.',
                      correction='과거 코드는 즉시 비웠지만 현재 코드는 응답을 보낸 뒤에 비운다.')

    def test_missing_and_exact_quoted_supported_claims(self):
        self.validate(claim='후보 원고에는 재시도 횟수에 대한 설명이 없다.')
        self.validate(assessment='supported', claim='원고는 “실패하면 오류를 반환한다.”라고 설명한다.')
        validate_korean_review({'claims': [{'assessment': 'supported',
                               'claim': '원고는 “処理中”이라는 이름을 사용한다.',
                               'correction': None, 'consequence': '현재 코드의 `state.処理中`과 이름이 같다.'}]},
                               '상태 이름은 処理中이다.')
