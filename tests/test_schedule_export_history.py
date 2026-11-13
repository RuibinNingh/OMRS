"""导出历史以稳定身份取有效反馈，排序按作答时间而非分数或提交时间。"""
import json
import re
import tempfile
import unittest
from unittest.mock import patch

from omrs.creation import create_question
from omrs.data_repository import resolve_question
from omrs.exporting import _build_export_data, _normalize_history_options, export_schedule_artifact
from omrs.ledger import append_commit
from omrs.projections import rebuild_projection


def seed_history(vault, question_id, uid):
    """提交顺序故意乱序，覆盖补录、同日多次、零分与高分答错。"""
    commits = []
    for day, clock, score, correct in [
        ('2026-11-10', '19:00:00', 2, False),
        ('2026-11-13', '09:00:00', 4, True),
        ('2026-11-12', '20:00:00', 9, False),
        ('2026-11-13', '21:00:00', 0, False),
        ('2026-11-11', '20:00:00', 8, True),
        ('2026-10-02', '20:00:00', 6, True),
        ('2026-10-07', '20:00:00', 3, False),
        ('2026-10-21', '20:00:00', 7, True),
    ]:
        commits.append(append_commit(vault, 'test', 'review.batch_submit', '合成练习记录', {'feedbacks': [{
            'question_id': question_id, 'uid_at_that_time': uid, 'source': 'due', 'sub_score': score,
            'is_correct': correct, 'review_date': day, 'recorded_at': f'{day}T{clock}+08:00',
            'note': '不应导出这段私有备注',
        }]}))
    rebuild_projection(vault)
    return commits


class ScheduleExportHistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='omrs-export-history-')
        self.addCleanup(self.folder.cleanup)
        self.vault = self.folder.name
        self.question = create_question(self.vault, '数学', '函数', 5,
                                        question_text='求函数的单调区间。', answer_text='单调递增。')
        self.row = resolve_question(self.vault, self.question['uid'])
        self.qid = self.row['question_id']
        self.commits = seed_history(self.vault, self.qid, '历史旧编号')

    def data(self, history=None, answers=False):
        payload, _, _, _ = export_schedule_artifact(self.vault, question_refs=[{'question_id': self.qid}],
                                                   include_answers=answers, history=history)
        source = payload.decode()
        return json.loads(re.search(r'window.OMRS_DATA = (.*?);</script>', source).group(1)), source

    def test_order_is_newest_first_with_same_day_attempts_and_limit(self):
        data, _ = self.data({'position': 'question', 'limit': 4})
        records = data['questions'][0]['history']
        self.assertEqual([r['score'] for r in records], [0, 4, 9, 8])
        self.assertEqual([r['correct'] for r in records], [False, True, False, True])
        self.assertEqual(data['answers'][0]['history'], [])

    def test_feedback_history_survives_without_answers_or_notes(self):
        data, source = self.data({'position': 'feedback'})
        self.assertEqual(data['answers'][0]['blocks'], [])
        self.assertEqual(data['answers'][0]['notes'], {})
        self.assertEqual(len(data['answers'][0]['history']), 8)
        self.assertEqual(data['questions'][0]['history'], [])
        self.assertNotIn('不应导出这段私有备注', source)

    def test_same_minute_records_compare_instants_with_mixed_timezones(self):
        for recorded_at, score in [('2026-11-13T13:00:59Z', 6), ('2026-11-13T21:00:30+08:00', 7)]:
            append_commit(self.vault, 'test', 'review.batch_submit', '同分钟不同时间表示', {'feedbacks': [{
                'question_id': self.qid, 'uid_at_that_time': self.question['uid'], 'source': 'due',
                'sub_score': score, 'is_correct': True, 'review_date': '2026-11-13', 'recorded_at': recorded_at,
            }]})
        rebuild_projection(self.vault)
        data, _ = self.data({'position': 'question', 'limit': 3})
        self.assertEqual([r['score'] for r in data['questions'][0]['history']], [6, 7, 0])

    def test_default_and_disabled_history_do_not_read_records(self):
        for options in (None, {'position': 'none'}, {'position': 'invalid'}):
            with self.subTest(options=options), patch('omrs.exporting.history_rows', side_effect=AssertionError('不应读取')):
                data, _ = self.data(options)
                self.assertEqual(data['meta']['history']['position'], 'none')
                self.assertEqual(data['questions'][0]['history'], [])

    def test_retracted_feedback_is_absent_and_old_uid_still_matches_identity(self):
        append_commit(self.vault, 'test', 'review.retract', '撤销合成反馈', {
            'target_commit_id': self.commits[3]['commit_id'], 'target_review_index': 0})
        rebuild_projection(self.vault)
        data, _ = self.data({'position': 'question', 'limit': 16})
        self.assertEqual([r['score'] for r in data['questions'][0]['history']], [4, 9, 8, 2, 7, 3, 6])
        # 导出按稳定身份读取，即便反馈载荷保留历史编号也不能丢失。
        self.assertEqual(len(data['questions'][0]['history']), 7)

    def test_options_are_bounded_and_no_history_has_no_placeholder(self):
        self.assertEqual(_normalize_history_options({'position': 'question', 'limit': 999, 'scores': False}),
                         {'position': 'question', 'limit': 16, 'scores': False, 'dates': True})
        self.assertEqual(_normalize_history_options({'limit': 'bad'})['limit'], 8)
        empty = create_question(self.vault, '物理', '力学', 4, question_text='求加速度。')
        row = resolve_question(self.vault, empty['uid'])
        question = {'uid': empty['uid'], 'question_id': row['question_id'], 'question': '求加速度。'}
        data = _build_export_data(self.vault, 'TMP-test', [question], False, history={'position': 'feedback'})
        self.assertEqual(data['answers'][0]['history'], [])


if __name__ == '__main__':
    unittest.main()
