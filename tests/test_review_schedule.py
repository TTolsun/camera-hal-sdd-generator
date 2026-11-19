import threading
import unittest

from sdd.independent_review import schedule_reviews


class ReviewScheduleTests(unittest.TestCase):
    def test_default_and_one_worker_run_serially_on_the_caller(self):
        caller = threading.get_ident()
        for options in ({}, {'workers': 1}):
            with self.subTest(options=options):
                calls = []

                def review(item):
                    self.assertEqual(threading.get_ident(), caller)
                    calls.append(item)
                    return item * 2

                self.assertEqual(schedule_reviews(review, iter((3, 1, 2)), **options), [6, 2, 4])
                self.assertEqual(calls, [3, 1, 2])

    def test_parallel_reviews_overlap_and_results_keep_input_order(self):
        first_started = threading.Event()
        third_started = threading.Event()

        def review(item):
            if item == 0:
                first_started.set()
                self.assertTrue(third_started.wait(timeout=10))
            elif item == 1:
                self.assertTrue(first_started.wait(timeout=10))
            else:
                third_started.set()
            return f'review {item}'

        self.assertEqual(schedule_reviews(review, range(3), workers=2),
                         ['review 0', 'review 1', 'review 2'])

    def test_failure_propagates_without_submitting_more_work(self):
        started = threading.Barrier(2, timeout=10)
        consumed = []
        finished = [threading.Event(), threading.Event()]

        def items():
            for item in range(3):
                consumed.append(item)
                yield item

        def review(item):
            started.wait()
            finished[item].set()
            raise ValueError('review failed')

        with self.assertRaisesRegex(ValueError, 'review failed'):
            schedule_reviews(review, items(), workers=2)
        self.assertEqual(consumed, [0, 1])
        self.assertTrue(all(event.is_set() for event in finished))

    def test_invalid_worker_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'workers must be at least 1'):
            schedule_reviews(lambda item: item, (), workers=0)
