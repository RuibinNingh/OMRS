"""整图评估口径与训练内存保护。"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from tools.boxdetect.evaluate import score_image, summarize
from tools.boxdetect import train


def box(role='question', **changes):
    return dict(role=role, x=0., y=0., w=.5, h=.5, **changes)


class EvaluationTests(unittest.TestCase):
    def test_perfect_two_roles(self):
        expected = [box(), box('answer')]
        row = score_image(expected, expected)
        self.assertTrue(row['unchanged'])
        result = summarize([row])
        self.assertEqual(result['answer']['mean_iou'], 1)
        self.assertEqual(result['answer']['histogram'][-1], 1)
        self.assertEqual(result['unchanged_rate'], 1)

    def test_missing_answer_is_failure(self):
        row = score_image([box(), box('answer')], [box()])
        self.assertEqual(row['answer']['ious'], [0])
        self.assertFalse(row['unchanged'])

    def test_duplicate_prediction_counts_false_positive(self):
        truth = [box(), box('answer')]
        row = score_image(truth, truth + [box()])
        self.assertEqual(row['question']['extra'], 1)
        self.assertFalse(row['unchanged'])

    def test_one_prediction_cannot_match_two_boxes(self):
        row = score_image([box(), box(), box('answer')], [box(), box('answer')])
        self.assertEqual(sorted(row['question']['ious']), [0, 1])
        self.assertFalse(row['unchanged'])

    def test_no_images(self):
        self.assertEqual(summarize([])['images'], 0)
        self.assertEqual(summarize([])['answer']['pass_rate'], 0)


class MemoryGuardTests(unittest.TestCase):
    def arguments(self, run):
        return argparse.Namespace(run=str(run), dataset='/unused', resume=False,
                                  epochs=120, max_rss_gib=6, max_hours=4)

    def test_low_available_memory_refuses_to_spawn(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(train, 'memory_available', return_value=3 * 1024**3), \
                mock.patch.object(train.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, '不足 4 GiB'):
                train.supervise(self.arguments(Path(folder) / 'run'))
            spawn.assert_not_called()

    def test_rss_limit_stops_only_training_process_group_and_records_failure(self):
        child = mock.Mock(pid=876543, returncode=0)
        child.poll.return_value = None
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(train, 'memory_available', return_value=12 * 1024**3), \
                mock.patch.object(train, 'process_tree_rss', return_value=7 * 1024**3), \
                mock.patch.object(train.subprocess, 'Popen', return_value=child) as spawn, \
                mock.patch.object(train.os, 'killpg') as stop, \
                mock.patch.object(train.signal, 'signal'), contextlib.redirect_stdout(io.StringIO()):
            run = Path(folder) / 'run'
            self.assertEqual(train.supervise(self.arguments(run)), 1)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            stop.assert_called_once_with(child.pid, train.signal.SIGTERM)
            child.wait.assert_called_once_with(timeout=10)
            state = json.loads((run / 'status.json').read_text())
            self.assertEqual(state['state'], 'failed')
            self.assertIn('内存上限', state['error'])
            self.assertEqual(state['peak_rss_bytes'], 7 * 1024**3)
