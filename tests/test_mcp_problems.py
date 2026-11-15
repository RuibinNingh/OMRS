"""问题工具的真实权限、审核、CAS与原生回执链。"""
import tempfile
import unittest
from omrs import ai_review, problems, problem_review
from omrs.mcp.keys import create_key, revoke_key
from omrs.agent.tools import build_registry


class ProblemReviewTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix='problem-review-')
        self.addCleanup(self.t.cleanup)
        self.v = self.t.name
        self.key = create_key(self.v,scopes=['omrs:read','problem:read','problem:write'])

    def propose(self, action, payload, request='proposal'):
        return problem_review.propose(self.v,self.key['key_id'],action,{**payload,'request_id':request},'http://127.0.0.1:9876')

    def test_pending_readback_apply_retry_and_receipt(self):
        op = self.propose('create_problem',{'title':'模型假设','basis':'user_confirmed'})
        self.assertEqual(problems.search(self.v)['total'],0)
        row = ai_review.decide(self.v,op['operation_id'],1,'approve')
        self.assertEqual(row['status'],'applied')
        self.assertEqual(row['result']['problem']['basis'],'ai_hypothesis')
        self.assertEqual(problems.search(self.v)['total'],1)
        self.assertEqual(self.propose('create_problem',{'title':'模型假设','basis':'user_confirmed'})['operation_id'],op['operation_id'])
        self.assertIsNotNone(ai_review._auto_receipt(self.v,row))

    def test_scope_revocation_and_manual_conflict(self):
        old = create_key(self.v)
        with self.assertRaises(PermissionError):
            problem_review.propose(self.v,old['key_id'],'create_problem',{'title':'无权','request_id':'old'},'http://127.0.0.1:9876')
        p = problems.execute(self.v,'create_problem',{'title':'人工原文','request_id':'human'})['problem']
        op = self.propose('update_problem',{'id':p['id'],'expected_revision':1,'title':'AI修改'})
        problems.execute(self.v,'update_problem',{'id':p['id'],'expected_revision':1,'title':'人工新文','request_id':'human2'})
        self.assertEqual(ai_review.decide(self.v,op['operation_id'],1,'approve')['status'],'conflict')
        pending = self.propose('create_problem',{'title':'撤权后不能执行'},'revoked')
        revoke_key(self.v,self.key['key_id'])
        self.assertEqual(ai_review.decide(self.v,pending['operation_id'],1,'approve')['status'],'conflict')

    def test_assistant_tools_registered_as_confirm(self):
        r = build_registry()
        for name in problems.ACTIONS:
            self.assertEqual(r.get(name).level,'confirm')
        self.assertEqual(r.get('search_problems').level,'read')

    def test_review_preview_contains_actual_before_and_safe_attachment(self):
        import base64
        from tests.test_schedule_banner import SVG
        p=problems.execute(self.v,'create_problem',{'title':'用户原文','request_id':'preview-original'})['problem']
        op=self.propose('update_problem',{'id':p['id'],'expected_revision':1,'title':'模型新文'},'preview')
        title=next(c for c in op['preview']['changes'] if c['field']=='title')
        self.assertEqual(title['before'],'用户原文')
        asset=self.propose('add_problem_asset',{'data_base64':base64.b64encode(SVG.encode()).decode()},'preview-asset')
        self.assertTrue(asset['preview']['asset']['src'].startswith('data:image/svg+xml;base64,'))

    def test_real_mcp_sdk_and_original_assistant_center_execution(self):
        import asyncio
        import json
        import os
        from unittest.mock import patch
        from mcp.server.auth.provider import AccessToken
        from omrs.mcp.server import build_server
        from omrs.common import save_config
        from omrs.agent import runtime
        token=AccessToken(token=self.key['secret'],client_id=self.key['key_id'],scopes=self.key['scopes'])
        server=build_server(self.v)
        async def call(name,args):
            with patch('omrs.mcp.server.get_access_token',return_value=token):
                result=await server.call_tool(name,args)
            if isinstance(result,tuple):return result[1]
            return json.loads(next(item.text for item in result if getattr(item,'text',None)))
        op=asyncio.run(call('create_problem',{'title':'MCP真实适配','request_id':'sdk'}))
        self.assertEqual(op['status'],'pending_confirmation')
        row=ai_review.decide(self.v,op['operation_id'],1,'approve')
        self.assertEqual(row['status'],'applied')
        pid=row['result']['problem']['id']
        readback=asyncio.run(call('get_problem',{'id':pid}))
        self.assertEqual(readback['title'],'MCP真实适配')
        change=asyncio.run(call('update_problem',{'id':pid,'expected_revision':1,'request_id':'sdk-change','status':'working','reason':'已制定检查流程'}))
        self.assertEqual(ai_review.decide(self.v,change['operation_id'],1,'approve')['status'],'applied')
        save_config(self.v,{'agent_enabled':True})
        rt=runtime.get_runtime(self.v)
        self.addCleanup(lambda:runtime._RUNTIMES.pop(os.path.abspath(self.v),None))
        conv=rt.create_conversation()['id']
        rt.set_permission_mode(conv,'hold',{'kind':'web'})
        run=runtime.Run('run_problem_synthetic',conv,'synthetic',rt.store)
        rt.store.create_run(run.id,conv,'synthetic');rt.runs[run.id]=run
        hooks=runtime.Hooks(rt,run,build_registry())
        tool=build_registry().get('create_problem')
        synthetic={'id':'problem_synthetic_call','name':tool.name,'args':{'title':'助手真实审核链','request_id':'agent-sdk'}}
        verdict=hooks.before_tool_call(synthetic,tool)
        self.assertEqual(verdict['status'],'deferred')
        proposed=ai_review.by_identity(self.v,runtime._review_identity(run.id,synthetic['id']))
        final=ai_review.decide(self.v,proposed['operation_id'],1,'approve',{'kind':'web'})
        self.assertEqual(final['status'],'applied')
        self.assertEqual(final['result']['problem']['title'],'助手真实审核链')
        self.assertEqual(final['result']['problem']['basis'],'ai_hypothesis')
        self.assertIsNotNone(ai_review._auto_receipt(self.v,final))


class ProblemTransportTests(unittest.TestCase):
    def test_all_problem_tools_over_real_http_mcp_and_web_review(self):
        import asyncio
        import base64
        import json
        import urllib.request
        from tests.test_mcp_protocol import MCPServerProcess, _session, _json_result, _png
        from omrs.data_repository import mastery_rows
        server=MCPServerProcess()
        try:
            server.start()
            key=create_key(server.vault,scopes=['omrs:read','problem:read','problem:write'])
            qids=[r['question_id'] for r in mastery_rows(server.vault)]
            before=mastery_rows(server.vault)
            def approve(op):
                self.assertEqual(op['status'],'pending_confirmation')
                body=json.dumps({'id':op['operation_id'],'expected_revision':op['revision'],'decision':'approve'}).encode()
                req=urllib.request.Request(f'http://127.0.0.1:{server.web_port}/api/ai-review/decide',data=body,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:row=json.load(response)['item']
                self.assertEqual(row['status'],'applied',row)
                return row['result']
            async def run():
                async with _session(server.mcp_port,server.keys['read']['secret']) as old:
                    names={t.name for t in (await old.list_tools()).tools}
                    self.assertNotIn('search_problems',names)
                    self.assertTrue((await old.call_tool('create_problem',{'title':'无权','request_id':'old'})).isError)
                async with _session(server.mcp_port,key['secret']) as client:
                    async def call(name,**args):
                        result=await client.call_tool(name,args)
                        self.assertFalse(result.isError,result)
                        return _json_result(result)
                    asset=approve(await call('add_problem_asset',data_base64=base64.b64encode(_png()).decode(),request_id='asset-http'))['asset']
                    p=approve(await call('create_problem',title='MCP问题全链路',description_md='## 合成观察\n'+asset['markdown'],request_id='create-http'))['problem']
                    self.assertEqual(p['basis'],'ai_hypothesis')
                    p=approve(await call('link_problem_questions',id=p['id'],expected_revision=1,question_ids=qids,request_id='link-http'))['problem']
                    detail=await call('get_problem',id=p['id'])
                    self.assertEqual(len(detail['questions']),2)
                    p=approve(await call('update_problem',id=p['id'],expected_revision=p['revision'],status='working',reason='人工批准合成分析',description_md='更新后的观察\n'+asset['markdown'],request_id='update-http'))['problem']
                    e=approve(await call('add_reflection_entry',question_id=qids[0],content_md='模型推测，待用户确认',problem_ids=[p['id']],request_id='entry-http'))['entry']
                    e=approve(await call('revise_reflection_entry',id=e['id'],expected_revision=1,content_md='修订后仍是模型推测',reason='补充假设',request_id='revise-http'))['entry']
                    self.assertEqual(e['basis'],'ai_hypothesis')
                    self.assertEqual((await call('get_reflections',question_id=qids[0]))['items'][0]['revision'],2)
                    self.assertEqual((await call('search_problems',query='全链路'))['total'],1)
                    p=approve(await call('unlink_problem_questions',id=p['id'],expected_revision=p['revision'],question_ids=[qids[1]],request_id='unlink-http'))['problem']
                    self.assertEqual(len((await call('get_problem',id=p['id']))['questions']),1)
                    self.assertEqual((await call('create_problem',title='MCP问题全链路',description_md='## 合成观察\n'+asset['markdown'],request_id='create-http'))['status'],'applied')
            asyncio.run(run())
            self.assertEqual(mastery_rows(server.vault),before)
        finally:
            server.stop()
