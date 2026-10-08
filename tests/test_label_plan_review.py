"""技术准备、单次审批、人工修订与版本竞争。"""
import copy
import json
from unittest.mock import patch

from tests import test_label_plan as support
from omrs import ai_review
from omrs.label_plan_prepare import candidates, list_labels, stage, prepared_payload, _DRAFTS
from omrs.label_plan_review import propose_mcp
from omrs.labels import load_labels, save_label
from omrs.question_ops import set_question_labels
from omrs.ledger import read_commits


class LabelPreparationTests(__import__("unittest").TestCase):
    change = support.LabelPlanTests.change
    apply = support.LabelPlanTests.apply
    def setUp(self):
        support.LabelPlanTests.setUp(self)
        self.key=patch('omrs.mcp.keys.active_key',return_value={'scopes':['omrs:read','label:write','label:delete']})
        self.key.start();self.addCleanup(self.key.stop)

    def proposal(self):
        staged=stage(self.vault,'mcp','key','first',{'scope':{'subject':'数学'},'label_changes':[{'action':'create','key':'n','name':'新'}],
                    'question_changes':[self.change(add=['n'],reason='配方法')]})
        return propose_mcp(self.vault,'key','request',staged['plan_id'],staged['version'])

    def test_stage_idempotent_owner_version_and_no_business_mutation(self):
        before=len(read_commits(self.vault))
        payload={'question_changes':[self.change(uncertain_reason='信息不足')]}
        draft=stage(self.vault,'mcp','key','1',payload)
        self.assertEqual(stage(self.vault,'mcp','key','1',payload)['plan_id'],draft['plan_id'])
        with self.assertRaises(ValueError):stage(self.vault,'mcp','other','2',payload,draft['plan_id'],1)
        with self.assertRaises(ValueError):stage(self.vault,'mcp','key','2',payload,draft['plan_id'],0)
        with self.assertRaises(ValueError):stage(self.vault,'mcp','key','1',{'label_changes':[{'action':'create','key':'n','name':'n'}]},draft['plan_id'],1)
        self.assertEqual(len(read_commits(self.vault)),before)
        self.assertEqual(load_labels(self.vault)['labels'],[])

    def test_durable_proposal_revision_and_one_approval(self):
        row=self.proposal()
        self.assertEqual(load_labels(self.vault)['labels'],[])
        _DRAFTS.clear()
        revised=ai_review.update(self.vault,row['operation_id'],1,{'label_changes':[{'change_id':'first:1','name':'配方法','color':'#22cc44'}]})
        self.assertEqual(revised['revision'],2)
        with self.assertRaises(ai_review.ReviewError):ai_review.decide(self.vault,row['operation_id'],1,'approve')
        applied=ai_review.decide(self.vault,row['operation_id'],2,'approve')
        self.assertEqual(applied['status'],'applied')
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'],'配方法')
        again=ai_review.decide(self.vault,row['operation_id'],2,'approve')
        self.assertEqual(again['result'],applied['result'])

    def test_revision_cannot_expand_targets(self):
        row=self.proposal()
        for update in ({'question_changes':[{'question_id':'not-original','add':[]}]},
                       {'label_changes':[{'change_id':'first:1','action':'delete'}]},
                       {'question_changes':[{'question_id':self.q['question_id'],'add':['outside']}] } ):
            with self.assertRaises(ValueError):ai_review.update(self.vault,row['operation_id'],1,update)

    def test_catalog_and_reference_changed_after_preview(self):
        row=self.proposal();save_label(self.vault,name='后来')
        applied=ai_review.decide(self.vault,row['operation_id'],1,'approve')
        self.assertEqual(applied['status'],'conflict')
        self.assertEqual([d['name'] for d in load_labels(self.vault)['labels']],['后来'])

    def test_expiry_and_permission_revocation(self):
        row=self.proposal()
        with patch('omrs.mcp.keys.active_key',return_value=None):
            applied=ai_review.decide(self.vault,row['operation_id'],1,'approve')
        self.assertEqual(applied['error_code'],'forbidden')
        self.assertEqual(load_labels(self.vault)['labels'],[])

    def test_read_pages_are_complete_json(self):
        got=candidates(self.vault,{'subject':'数学'})
        self.assertEqual(got['items'][0]['question_id'],self.q['question_id'])
        self.assertLessEqual(len(json.dumps(got,ensure_ascii=False)),22000)
        self.assertEqual(list_labels(self.vault)['items'],[])

    def test_fragment_50_and_draft_ttl(self):
        with self.assertRaises(ValueError):stage(self.vault,'mcp','key','f',{'question_changes':[self.change()]*51})
        d=stage(self.vault,'mcp','key','f',{'question_changes':[self.change(uncertain_reason='待判断')]})
        _DRAFTS[d['plan_id']]['updated']-=1801
        with self.assertRaises(ValueError):prepared_payload(self.vault,'mcp','key',d['plan_id'],1)
