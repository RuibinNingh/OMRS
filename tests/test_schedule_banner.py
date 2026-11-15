"""首页提醒快照、安全profile及旧Session兼容。"""
import tempfile
import unittest
from omrs import schedule_banner as banner
from omrs.creation import create_question
from omrs.sessions import create_session_from_selection
from omrs.data_repository import mastery_rows
from omrs.exporting import export_schedule_html

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="680" height="60" viewBox="0 0 680 60"><title>作答流程</title><rect width="680" height="60" fill="white"/><text x="16" y="38" font-size="20">读题 → 独立作答 → 核对 → 记录错因</text></svg>'


class BannerTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix='banner-')
        self.addCleanup(self.t.cleanup)
        self.v = self.t.name
        create_question(self.v,'数学','合成',5,question_text='解不等式 x+1>2')
        self.q = mastery_rows(self.v)[0]['question_id']

    def test_snapshot_old_sessions_and_export_override(self):
        banner.save_settings(self.v,{'enabled':True,'svg':SVG,'expected_revision':0})
        session = create_session_from_selection(self.v,[{'question_id':self.q}])
        sid = session['session_id']
        original = banner.for_export(self.v,sid)
        banner.save_settings(self.v,{'enabled':False,'svg':'','expected_revision':1})
        self.assertEqual(banner.for_export(self.v,sid),original)
        self.assertIsNone(banner.for_export(self.v,'EXP-old'))
        self.assertIsNone(banner.for_export(self.v,sid,{'mode':'off'}))
        data,_ = export_schedule_html(self.v,session_id=sid)
        self.assertIn(b'"schedule_banner"',data)
        self.assertIn(b'data:image/svg+xml;base64,',data)

    def test_unsafe_tall_and_unreadable_refused(self):
        for bad in [SVG.replace('<text ','<text onclick="x" '),SVG.replace('height="60"','height="600"').replace('680 60','680 600'),SVG.replace('font-size="20"','font-size="2"')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                banner.save_settings(self.v,{'enabled':True,'svg':bad,'expected_revision':0})
        self.assertFalse(banner.settings(self.v)['enabled'])
