"""真实 SDK 检查发现、组合权限、技术准备、提案与网页批准。"""
import asyncio
import unittest
from omrs import ai_review
from omrs.mcp.keys import create_key, revoke_key
from tests.test_mcp_protocol import MCPServerProcess, _session, _json_result


class MCPLabelPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=MCPServerProcess();cls.server.start()
    @classmethod
    def tearDownClass(cls):cls.server.stop()

    def test_sdk_permissions_and_single_proposal(self):
        async def run():
            readonly=create_key(self.server.vault,scopes=['omrs:read'])
            key=create_key(self.server.vault,scopes=['omrs:read','label:write'])
            async with _session(self.server.mcp_port,readonly['secret']) as client:
                names={t.name for t in (await client.list_tools()).tools}
                self.assertIn('list_labels',names);self.assertNotIn('stage_label_plan',names)
            async with _session(self.server.mcp_port,key['secret']) as client:
                names={t.name for t in (await client.list_tools()).tools}
                self.assertIn('stage_label_plan',names);self.assertNotIn('approve_label_plan',names)
                got=_json_result(await client.call_tool('get_labeling_candidates',{'scope':{'subject':'数学'}}))
                q=got['items'][0]
                payload={'scope':{'subject':'数学'},'label_changes':[{'action':'create','key':'new','name':'SDK方法'}],
                         'question_changes':[{'question_id':q['question_id'],'expected_content_hash':q['content_hash'],'add':['new'],'reason':'按内容归类'}]}
                draft=_json_result(await client.call_tool('stage_label_plan',{'fragment_id':'sdk-f','payload':payload}))
                self.assertFalse(draft['wrote'])
                row=_json_result(await client.call_tool('propose_label_plan',{'plan_id':draft['plan_id'],'expected_version':draft['version'],'request_id':'sdk-p'}))
                self.assertEqual(row['status'],'pending_confirmation')
                self.assertIn('/#/ai-review?',row['confirmation_url'])
                final=ai_review.decide(self.server.vault,row['operation_id'],1,'approve')
                self.assertEqual(final['status'],'applied',final)
                labels=_json_result(await client.call_tool('list_labels',{}))
                created=next(d for d in labels['items'] if d['name']=='SDK方法')
                denied=await client.call_tool('stage_label_plan',{'fragment_id':'delete','payload':{'label_changes':[{'action':'delete','label_id':created['id']}]}})
                self.assertTrue(denied.isError)
        asyncio.run(run())
