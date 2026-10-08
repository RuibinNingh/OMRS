"""三百题：假模型分批准备、真实 MCP SDK、聊天原位修订批准与整批撤销。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
if sys.path and Path(sys.path[0]).resolve()==Path(__file__).resolve().parent:sys.path.pop(0)
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from browser_runtime import launch_chromium, open_app
from test_mcp_protocol import MCPServerProcess, _session, _json_result
from omrs import ai_review
from omrs.common import save_config
from omrs.creation import create_question
from omrs.labels import save_label, load_labels
from omrs.question_ops import set_question_labels
from omrs.label_plan_prepare import candidates
from omrs.ledger import read_commits, verify_ledger
from omrs.stats import get_stats


def main():
    from playwright.sync_api import sync_playwright
    checks=[]
    def check(name,ok):
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
        if not ok:raise AssertionError(name)
        checks.append(name)
    server=MCPServerProcess()
    shots=Path('/tmp/omrs-label-plan-shots');shots.mkdir(exist_ok=True)
    try:
        qs=[create_question(server.vault,'数学','整理',5,question_text=f'第{i+1}题：用配方法解 $x^2-2x=0$。',answer_text='配方得 $(x-1)^2=1$。') for i in range(300)]
        labels={name:save_label(server.vault,name=name) for name in ['旧方法','目标方法','移除标记','重命名']}
        other=create_question(server.vault,'物理','跨科目',5,question_text='用图像法分析运动。')
        set_question_labels(server.vault,qs[0]['uid'],['旧方法','目标方法','重命名'])
        set_question_labels(server.vault,qs[1]['uid'],['移除标记'])
        set_question_labels(server.vault,other['uid'],['旧方法','移除标记','重命名'])
        original={q['question_id']:Path(server.vault,q['file_path']).read_text() for q in qs+[other]}
        original_defs=load_labels(server.vault)
        scope={'subject':'数学','category':'整理'}
        all_candidates=[];cursor=''
        while True:
            result=candidates(server.vault,scope,cursor=cursor)
            all_candidates.extend(result['items']);cursor=result['next_cursor']
            if not cursor:break
        definitions=[{'action':'create','key':'method','name':'配方法'},
                     {'action':'merge','label_id':labels['旧方法']['id'],'into':labels['目标方法']['id']},
                     {'action':'delete','label_id':labels['移除标记']['id']},
                     {'action':'update','label_id':labels['重命名']['id'],'name':'图像方法','color':'#64748b','order':2}]
        changes=[{'question_id':q['question_id'],'expected_content_hash':q['content_hash'],'add':['method'],'reason':'答案使用配方形成完全平方。'} for q in all_candidates]
        rounds=[{'ttft_ms':0,'tps':1000000,'tool_calls':[{'name':'list_labels','arguments':{}}]}]
        for i in range(15):
            rounds.append({'ttft_ms':0,'tps':1000000,'tool_calls':[{'name':'get_labeling_candidates','arguments':{'scope':scope,**({'cursor':'{{r:get_labeling_candidates.next_cursor}}'} if i else {})}}]})
        for i in range(6):
            args={'fragment_id':f'f{i}','payload':{'question_changes':changes[i*50:(i+1)*50]}}
            if i==0:args['payload'].update(scope=scope,label_changes=definitions)
            else:args.update(plan_id='{{r:stage_label_plan.plan_id}}',expected_version='{{raw:stage_label_plan.version}}')
            rounds.append({'ttft_ms':0,'tps':1000000,'tool_calls':[{'name':'stage_label_plan','arguments':args}]})
        rounds.extend([{'ttft_ms':0,'tps':1000000,'tool_calls':[{'name':'propose_label_plan','arguments':{'plan_id':'{{r:stage_label_plan.plan_id}}','expected_version':'{{raw:stage_label_plan.version}}'}}]},
                       {'ttft_ms':0,'tps':1000000,'text':'整理已执行，以人工修订后的真实结果为准。'}])
        faux=Path(server.vault,'label-faux.json');faux.write_text(json.dumps({'default':{'rounds':rounds}},ensure_ascii=False))
        save_config(server.vault,{'agent_enabled':True})
        env=dict(os.environ,OMRS_AGENT_FAUX_SCRIPT=str(faux));env.pop('OMRS_SYSTEMD_SERVICE',None);env.pop('OMRS_BOXDETECT_CONTROL',None)
        log=open(Path(server.work.name,'label-server.log'),'w')
        server._log=log
        server.process=subprocess.Popen([sys.executable,str(ROOT/'omrs_engine.py'),'--vault',server.vault,'serve','-p',str(server.web_port),'--mcp-port',str(server.mcp_port)],cwd=ROOT,env=env,stdout=log,stderr=log)
        base=f'http://127.0.0.1:{server.web_port}'
        for _ in range(150):
            try:urllib.request.urlopen(base+'/api/auth/session',timeout=1);break
            except OSError:
                if server.process.poll() is not None:raise RuntimeError(Path(log.name).read_text())
                time.sleep(.1)
        with sync_playwright() as pw:
            browser=launch_chromium(pw)
            page=browser.new_page(viewport={'width':1440,'height':900});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            open_app(page,base,'assistant');page.fill('#ast-input','按解题方法整理数学题');page.click('[data-action="assistant.send"]')
            gate=page.locator('.ast-op.is-waiting');gate.wait_for(timeout=60000)
            check('三百题分批准备后只有一个最终待审',gate.count()==1 and ai_review.counts(server.vault)['pending']==1)
            check('批准前定义和三百题文件均未变化',load_labels(server.vault)==original_defs and all(Path(server.vault,q['file_path']).read_text()==original[q['question_id']] for q in qs+[other]))
            page.fill('#ast-input','未发送输入需要保留')
            gate.locator('[data-action="assistant.gate"]').click()
            drawer=page.locator('.ast-review-panel[open]');drawer.locator('.arv-label-plan').wait_for()
            check('整批详情在聊天原位，三项跨科目操作默认关闭', '#/assistant' in page.url and drawer.locator('[data-change="ai-review.labelCross"]').count()==3 and not drawer.locator('[data-change="ai-review.labelCross"]').first.is_checked())
            check('逐题列表按25题分页且理由可查',drawer.locator('.arv-label-question').count()==25 and '答案使用配方' in drawer.inner_text())
            drawer.locator('[data-action="ai-review.labelPage"]').last.click()
            check('分页切换显示不同题目', '第 2 / 13 页' in drawer.inner_text())
            drawer.locator('[data-action="ai-review.edit"]').click()
            field=drawer.locator('.arv-label-fields input[maxlength="80"]').first
            field.fill('配方法·人工修订')
            drawer.locator('[data-drawer-close]').click()
            page.locator('.ui-dialog [data-dialog-cancel]').last.click()
            check('未保存修订阻止关闭且保留输入',field.input_value()=='配方法·人工修订' and '#/assistant' in page.url)
            drawer.locator('[data-action="ai-review.save"]').click()
            drawer.locator('[data-change="ai-review.labelCross"]').first.check()
            page.wait_for_function("() => document.querySelector('.arv-facts')?.textContent.includes('第 3 版')")
            check('勾选跨科目操作重新编译并换版本',drawer.locator('[data-change="ai-review.labelCross"]').first.is_checked())
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':900 if width==1440 else 844})
                for theme in ('light','dark'):
                    page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme)
                    page.screenshot(path=str(shots/f'assistant-{width}-{theme}.png'),animations='disabled')
                    check(f'{width}px/{theme}整批详情无横向溢出',not page.evaluate('document.documentElement.scrollWidth>innerWidth'))
            page.set_viewport_size({'width':1440,'height':900})
            drawer.locator('[data-action="ai-review.approve"]').click()
            drawer.locator('[data-action="ai-review.labelRevert"]').wait_for(timeout=30000)
            check('一次确认完成300题且应用人工标记名称',len([i for i in get_stats(server.vault)['items'] if '配方法·人工修订' in i['labels']])==300)
            check('已选跨科目合并去重，未选删除和改名仍保留',next(i for i in get_stats(server.vault)['items'] if i['question_id']==other['question_id'])['labels']==['目标方法','移除标记','重命名'])
            drawer.locator('[data-action="ai-review.labelRevert"]').click()
            drawer.locator('[data-action="ai-review.labelRevertConfirm"]').click()
            page.wait_for_function("() => document.querySelector('.arv-operation')?.textContent.includes('整批撤销已完成')")
            check('整批撤销恢复全部定义和题目',load_labels(server.vault)==original_defs and all(Path(server.vault,q['file_path']).read_text()==original[q['question_id']] for q in qs+[other]))
            drawer.locator('[data-drawer-close]').click()
            check('关闭详情后保留聊天输入',page.input_value('#ast-input')=='未发送输入需要保留' and '#/assistant' in page.url)
            from omrs.mcp.keys import create_key
            key=create_key(server.vault,'三百题 SDK',['omrs:read','label:write','label:delete'])
            async def mcp_prepare():
                async with _session(server.mcp_port,key['secret']) as client:
                    cursor='';questions=[]
                    while True:
                        result=_json_result(await client.call_tool('get_labeling_candidates',{'scope':scope,'cursor':cursor}))
                        questions.extend(result['items']);cursor=result['next_cursor']
                        if not cursor:break
                    draft=None
                    for i in range(6):
                        chunk=[{'question_id':q['question_id'],'expected_content_hash':q['content_hash'],'add':['method'],'reason':'答案使用配方法。'} for q in questions[i*50:(i+1)*50]]
                        args={'fragment_id':f'm{i}','payload':{'question_changes':chunk}}
                        if i==0:args['payload'].update(scope=scope,label_changes=definitions)
                        else:args.update(plan_id=draft['plan_id'],expected_version=draft['version'])
                        result=await client.call_tool('stage_label_plan',args)
                        assert not result.isError,result
                        draft=_json_result(result)
                    result=await client.call_tool('propose_label_plan',{'plan_id':draft['plan_id'],'expected_version':draft['version'],'request_id':'mcp-300'})
                    assert not result.isError,result
                    return _json_result(result)
            with ThreadPoolExecutor(max_workers=1) as worker:
                row=worker.submit(asyncio.run,mcp_prepare()).result()
            open_app(page,base,'ai-review?operation='+row['operation_id'])
            page.locator('.arv-label-plan').wait_for()
            check('真实SDK三百题归类在审核中心统一确认',ai_review.counts(server.vault)['pending']==1 and page.locator('.arv-label-question').count()==25)
            page.locator('[data-action="ai-review.approve"]').click()
            page.locator('[data-action="ai-review.labelRevert"]').wait_for(timeout=30000)
            check('MCP单次批准落地300题且Ledger有效',sum('配方法' in i['labels'] for i in get_stats(server.vault)['items'])==300 and verify_ledger(server.vault)['valid'])
            page.locator('[data-action="ai-review.labelRevert"]').click();page.locator('[data-action="ai-review.labelRevertConfirm"]').click()
            page.wait_for_function("() => document.querySelector('.arv-operation')?.textContent.includes('整批撤销已完成')")
            check('MCP整批撤销也恢复原数据且无页面错误',load_labels(server.vault)==original_defs and not errors)
            browser.close()
        print(f'标记整理 E2E：{len(checks)} 项通过',flush=True)
    finally:server.stop()


if __name__=='__main__':main()
