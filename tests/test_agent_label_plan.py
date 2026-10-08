"""助手 prepare 无业务审批，最终整批票据与按运行完整撤销。"""
import unittest

from tests import test_agent_review as support
from omrs import ai_review
from omrs.agent.revert import apply_revert, plan_revert
from omrs.label_plan_prepare import stage
from omrs.ledger import read_commits
from omrs.labels import load_labels
from omrs.content_history import projection_row, read_question_file
from omrs.ledger import blob_hash


class AgentLabelPlanTests(unittest.TestCase):
    setUp=support.AgentReviewTests.setUp
    start=support.AgentReviewTests.start
    stop=support.AgentReviewTests.stop
    finish=support.AgentReviewTests.finish

    def test_prepare_then_single_confirm_revision_and_whole_run_undo(self):
        q=self.question;row=projection_row(self.vault,question_id=q['question_id'])
        args={'fragment_id':'f','payload':{'label_changes':[{'action':'create','key':'n','name':'原名称'}],
               'question_changes':[{'question_id':q['question_id'],'expected_content_hash':blob_hash(read_question_file(self.vault,row)),'add':['n'],'reason':'解题方法'}]}}
        tool=self.registry.get('stage_label_plan');call={'id':'prepare','name':tool.name,'args':args}
        self.assertIsNone(self.hooks.before_tool_call(call,tool))
        prepared=self.hooks.execute(call,tool);self.hooks.after_tool_call(call,tool,prepared)
        self.assertEqual(prepared['commits'],[])
        self.assertEqual(ai_review.counts(self.vault)['pending'],0)
        self.assertEqual(load_labels(self.vault)['labels'],[])
        draft=prepared['result']
        review=self.start('propose_label_plan',{'plan_id':draft['plan_id'],'expected_version':draft['version']})
        token=self.pc.token
        revised=ai_review.update(self.vault,review['operation_id'],1,{'label_changes':[{'change_id':'f:1','name':'配方法'}]})
        self.assertNotEqual(token,self.pc.token)
        ai_review.decide(self.vault,review['operation_id'],2,'approve');self.finish()
        self.assertEqual(self.results[0]['result']['label_changes'][0]['after']['name'],'配方法')
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'],'配方法')
        plan=plan_revert(self.vault,self.run.id);self.assertTrue(plan['ok'],plan)
        self.assertEqual(len(plan['items']),1)
        self.assertEqual(plan['items'][0]['commit_type'],'labels.plan_apply')
        self.assertTrue(apply_revert(self.vault,self.run.id)['ok'])
        self.assertEqual(load_labels(self.vault)['labels'],[])
        self.assertTrue(plan_revert(self.vault,self.run.id)['already'])
