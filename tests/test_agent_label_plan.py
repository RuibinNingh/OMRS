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
        self.assertTrue(ai_review.detail(self.vault,review['operation_id'])['result']['reverted_by'])

    def test_prepare_budget_and_candidate_result_cap(self):
        import json
        from omrs.agent.loop import AgentLoop
        tool=self.registry.get('stage_label_plan')
        call={'id':'budget','name':tool.name,'parse_error':'','args':{'fragment_id':'budget','payload':{'label_changes':[{'action':'create','key':'b','name':'预算'}]}}}
        loop=AgentLoop(None,self.registry,self.hooks,lambda *args:None,{'rounds':1,'calls':1,'writes':0})
        outcome=loop._execute(call)
        self.assertEqual(outcome.status,'done');self.assertFalse(outcome.commits)
        self.assertEqual(loop.budget.writes,0);self.assertEqual(loop.budget.calls,1)
        self.assertEqual(self.registry.get('get_labeling_candidates').result_cap,24000)
        self.assertIsNone(self.registry.get('list_labels').result_cap)

    def test_abort_after_staging_rolls_back_and_preserves_original_data(self):
        from unittest.mock import patch
        from omrs import label_plan_journal
        draft=stage(self.vault,'agent',self.conv,'abort',{'label_changes':[{'action':'create','key':'n','name':'中止标记'}]})
        row=self.start('propose_label_plan',{'plan_id':draft['plan_id'],'expected_version':1},execute=False)
        ai_review.decide(self.vault,row['operation_id'],1,'approve');self.finish()
        before=len(read_commits(self.vault));original_stage=label_plan_journal._stage
        def abort(*args):
            result=original_stage(*args);self.run.abort.set();return result
        with patch('omrs.label_plan_journal._stage',side_effect=abort),self.assertRaises(ValueError):self.hooks.execute(self.call,self.tool)
        self.assertEqual(load_labels(self.vault)['labels'],[])
        self.assertEqual(len(read_commits(self.vault)),before)

    def test_native_receipt_recovers_before_tool_result_and_review_end_are_saved(self):
        draft=stage(self.vault,'agent',self.conv,'receipt',{'label_changes':[{'action':'create','key':'n','name':'恢复标记'}]})
        row=self.start('propose_label_plan',{'plan_id':draft['plan_id'],'expected_version':1},execute=False)
        ai_review.decide(self.vault,row['operation_id'],1,'approve');self.finish()
        actual=self.hooks.execute(self.call,self.tool)
        # 模拟业务事务已提交，但 after_tool_call 和审核结果尚未落盘就中断。
        self.assertEqual(ai_review.get(self.vault,row['operation_id'])['status'],'applying')
        before=len(read_commits(self.vault))
        self.assertEqual(ai_review.detail(self.vault,row['operation_id'])['status'],'applied')
        ai_review.initialize(self.vault)
        recovered=ai_review.get(self.vault,row['operation_id'])
        self.assertEqual(recovered['status'],'applied')
        self.assertFalse(recovered['result'].get('failed'))
        self.assertEqual(recovered['result']['label_changes'],actual['result']['label_changes'])
        self.assertEqual(len(read_commits(self.vault)),before)
        self.assertEqual(load_labels(self.vault)['labels'][0]['name'],'恢复标记')
