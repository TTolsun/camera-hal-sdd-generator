import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sdd import independent_review as review
from sdd.change_review import change_review_instructions


def source(path, blob, **windows):
    return dict(path=path, git_blob=blob, windows=[
        dict(name=name, start_line=1, end_line=1, text=text) for name, text in windows.items()
    ])


class ChangeReviewTest(unittest.TestCase):
    def test_only_changed_windows_and_stable_order(self):
        before = [source('a', 'old', other='unchanged', target='old operation', removed='retired'),
                  source('b', 'same', another='irrelevant')]
        after = [source('a', 'new', target='new operation', other='unchanged', added='introduced'),
                 before[1]]
        self.assertEqual(change_review_instructions(before, before[::-1]), '')
        prefix = change_review_instructions(before, after)
        reordered = [dict(file, windows=file['windows'][::-1]) for file in before[::-1]]
        self.assertEqual(prefix, change_review_instructions(reordered, after[::-1]))
        for text in ('old operation', 'retired', 'absent_from_parent_windows',
                     'absent_from_current_windows', '"line_range":[1,1]'):
            self.assertIn(text, prefix)
        for text in ('unchanged', 'irrelevant', 'new operation', 'introduced'):
            self.assertNotIn(text, prefix)

    def test_unseen_changes_are_explicit(self):
        before = [source('a', 'old', target='visible')]
        after = [source('a', 'new', target='visible')]
        prefix = change_review_instructions(before, after)
        self.assertIn('"outside_windows_uncertain":true', prefix)
        self.assertNotIn('visible', prefix)
        with self.assertRaises(ValueError):
            change_review_instructions([], [])

    def test_checkpoint_identity_and_effective_request(self):
        request = dict(system='instructions', user='original payload', response_schema={})
        original_request = request.copy()
        cfg = SimpleNamespace(agent=SimpleNamespace(kind='cli', model='configured'), build_dir=Path('.'))
        cache, sent = {}, []
        validate = lambda raw: [raw]

        class Capture:
            def __init__(self, execution):
                pass

            def chat(self, system, user, **kwargs):
                sent.append((system, user))
                return 'verdict'

        class Store:
            def __init__(self, cfg, identity, *, calls):
                self.key = review.canonical_request_hash(identity)

            def read(self):
                return cache.get(self.key)

            def write(self, raw, checked, capture):
                system, user = sent[-1]
                reviewer = Mock()
                reviewer.chat.side_effect = lambda s, u, **kw: self.replay(s, u, system, user, raw)
                cache[self.key] = (dict(raw=raw, statements=checked, receipts=[]), reviewer)

            @staticmethod
            def replay(system, user, expected_system, expected_user, raw):
                if (system, user) != (expected_system, expected_user):
                    raise AssertionError('Replay did not use the effective request')
                return raw

        def invoke(policy='v1', change=None):
            result = review.review_unit(cfg, Mock(), 'unit', request, validate,
                                        policy=policy, change_sources=change)[1]
            self.assertEqual(request, original_request)
            return result

        head = [source('a', 'head', target='new'), source('b', 'same', other='other')]
        previous = [source('a', 'parent', target='old'), head[1]]
        with patch.multiple(review, UnitStore=Store, Capture=Capture,
                            execution_identity=Mock(return_value={}), validate_original=Mock()):
            plain = invoke()
            unchanged = invoke(change=(head, head[::-1]))
            self.assertEqual(unchanged['status'], 'checkpoint-reused')
            self.assertEqual(unchanged['request_sha256'], plain['request_sha256'])
            changed = invoke(change=(previous, head))
            self.assertEqual(invoke(change=(previous[::-1], head[::-1]))['status'], 'checkpoint-reused')
            self.assertEqual(invoke(policy='v2', change=(previous, head))['status'], 'completed')
            older = [source('a', 'older', target='old'), head[1]]
            self.assertEqual(invoke(change=(older, head))['status'], 'completed')
        self.assertEqual(len(sent), 4)
        self.assertEqual(sent[0], ('instructions', 'original payload'))
        self.assertEqual(sent[1], ('instructions', change_review_instructions(previous, head) + '\noriginal payload'))
        self.assertNotEqual(plain['request_sha256'], changed['request_sha256'])
