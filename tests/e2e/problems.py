"""真实服务与Chromium：问题、错因草稿、手机和首页提醒；仅合成题库。"""
import base64
import importlib.util
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import traceback
import uuid
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs import schedule_banner, problems, problem_review
from omrs.mcp.keys import create_key
from omrs.sessions import create_session_from_selection, mark_session_completed
from omrs.exporting import export_schedule_html

spec=importlib.util.spec_from_file_location('visual_run',ROOT/'tests/visual/run.py')
visual=importlib.util.module_from_spec(spec); spec.loader.exec_module(visual)
SVG='<svg xmlns="http://www.w3.org/2000/svg" width="680" height="60" viewBox="0 0 680 60"><title>复习作答流程</title><rect width="680" height="60" fill="white"/><rect x="2" y="2" width="676" height="56" rx="8" fill="#eef4ff" stroke="#334155" stroke-width="1"/><text x="22" y="38" font-size="20" fill="#172554">读题与圈条件 → 独立作答 → 核对依据 → 记错因与验证</text></svg>'
DIAGRAM='<svg xmlns="http://www.w3.org/2000/svg" width="640" height="110" viewBox="0 0 640 110"><title>符号检查流程</title><rect width="640" height="110" fill="white"/><text x="20" y="44" font-size="22">乘除前检查符号 → 负数则改变不等号方向</text><text x="20" y="82" font-size="18">验证：用两个数代入，检查解集边界。</text></svg>'


def main():
    evidence=Path(os.environ.get('OMRS_PROBLEM_EVIDENCE','/worker/evidence'))
    shots=evidence/'screenshots'; shots.mkdir(parents=True,exist_ok=True)
    checks=[]; errors=[]
    def check(name,condition,detail=None):
        checks.append({'name':name,'ok':bool(condition),'detail':detail})
        print(name,condition,flush=True)
        assert condition,(name,detail)
    with tempfile.TemporaryDirectory(prefix='problem-e2e-') as vault:
        for n in range(18):
            create_question(vault,'数学','不等式与边界',5,question_text=f'第{n+1}份合成演示材料：解不等式 {n+2} - 2x > {n}，并写明每一步变形的依据。\n\n分别代入一个满足条件和一个不满足条件的数，说明不等号方向与端点是否正确。',answer_text='除以负数时必须变号，再检查边界。')
        q=mastery_rows(vault); qids=[r['question_id'] for r in q]
        baseline=mastery_rows(vault)
        old_session=create_session_from_selection(vault,[{'question_id':qid} for qid in qids])
        schedule_banner.save_settings(vault,{'enabled':True,'svg':SVG,'expected_revision':0})
        proc,port=visual.start_server(str(ROOT),vault,str(evidence/'problem-server.log'))
        base=f'http://127.0.0.1:{port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                context=browser.new_context(viewport={'width':1440,'height':1100},device_scale_factor=1)
                context.add_init_script("localStorage.setItem('omrs-theme','light')")
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#/problems')
                page.locator('[data-prb="new"]').first.click()
                page.locator('[data-prb-field="title"]').fill('不等式变形时遗漏符号检查')
                page.locator('[data-prb-field="description_md"]').fill('## 具体表现\n连续练习中，乘除负数时忘记改变不等号方向。\n\n## 应对办法\n先标出乘除项的符号，再变形。\n\n## 怎样验证改善\n在新题和隔时复习中解释每一步的依据。')
                page.locator('[data-prb-upload]').set_input_files({'name':'符号流程.svg','mimeType':'image/svg+xml','buffer':DIAGRAM.encode()})
                page.wait_for_function("() => document.querySelector('[data-prb-field=description_md]').value.includes('PA-')")
                photo=io.BytesIO();Image.new('RGB',(180,60),'#eef4ff').save(photo,format='PNG')
                page.locator('[data-prb-upload]').set_input_files({'name':'检查卡片.png','mimeType':'image/png','buffer':photo.getvalue()})
                page.wait_for_function("() => document.querySelector('[data-prb-field=description_md]').value.includes('.png')")
                page.locator('[data-prb="save"]').click(); page.locator('.prb-detail h1').wait_for()
                pid=page.request.get(base+'/api/problems').json()['items'][0]['id']
                page.locator('[data-prb="picker"]').click()
                for qid in qids[:2]:page.locator(f'[data-prb-qid="{qid}"]').check()
                page.locator('[data-prb="link"]').click();page.wait_for_function("() => document.querySelectorAll('.prb-linked .prb-question').length===2")
                check('问题关联两题',len(problems.get(vault,pid)['questions'])==2)
                second=page.request.post(base+'/api/problems/write',data={'action':'create_problem','data':{'title':'端点条件需要单独核对','description_md':'验证边界与取等条件，避免漏写端点。','question_ids':[qids[0]],'request_id':str(uuid.uuid4())}}).json()
                check('一题可属于两个问题',problems.search(vault,question_id=qids[0])['total']==2,second)
                page.reload(); page.locator(f'[data-prb="open"][data-id="{pid}"]').click(); page.locator('.prb-markdown img').first.wait_for()
                check('SVG重开能解码',page.locator('.prb-markdown img').first.evaluate('(e)=>e.complete&&e.naturalWidth>0'))
                check('图片重开能解码',page.locator('.prb-markdown img').count()==2 and page.locator('.prb-markdown img').last.evaluate('(e)=>e.complete&&e.naturalWidth>0'))
                page.screenshot(path=str(shots/'problems-desktop.png'),full_page=True)
                page.locator('[data-prb="edit"]').click()
                before_source=page.locator('[data-prb-field="description_md"]').input_value()
                page.locator('[data-prb-field="description_md"]').evaluate("(el,svg)=>{const data=new DataTransfer();data.setData('text/plain',svg);el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));}",DIAGRAM)
                page.wait_for_function("before=>document.querySelector('[data-prb-field=description_md]').value.length>before",arg=len(before_source),timeout=3000)
                check('粘贴完整SVG转受管引用','<svg' not in page.locator('[data-prb-field="description_md"]').input_value())
                source_length=len(page.locator('[data-prb-field="description_md"]').input_value())
                page.locator('[data-prb-field="description_md"]').evaluate("(el,svg)=>{const data=new DataTransfer();data.items.add(new File([svg],'拖入示意.svg',{type:'image/svg+xml'}));el.dispatchEvent(new DragEvent('drop',{dataTransfer:data,bubbles:true,cancelable:true}));}",DIAGRAM)
                page.wait_for_function("before=>document.querySelector('[data-prb-field=description_md]').value.length>before",arg=source_length)
                check('拖入图示转受管引用','<svg' not in page.locator('[data-prb-field="description_md"]').input_value())
                page.locator('[data-prb="save"]').click();page.locator('.prb-detail h1').wait_for()
                page.locator('[data-prb="question"]').first.click();page.locator('#modal .ref-head').wait_for()
                page.locator('[data-qv-reflection]').click()
                textarea=page.locator('#modal [data-ref-input="content_md"]')
                textarea.fill('两边除以 -2 时，没有改变不等号方向。')
                textarea.press('Control+Enter');page.wait_for_function("() => document.querySelectorAll('#modal .ref-entry').length===1")
                check('保存后清空表单便于连续录入',textarea.input_value()=='')
                textarea.fill('核对时只代入了一个值，遗漏了解集端点。')
                textarea.dispatch_event('compositionstart');textarea.press('Control+Enter')
                check('输入法组合不提交',len(problems.reflections(vault,qids[0])['items'])==1)
                textarea.dispatch_event('compositionend')
                def fail_once(route):route.abort('failed')
                page.route('**/api/problems/write',fail_once,times=1)
                page.locator('#modal [data-ref="save"]').click();page.get_by_text('草稿已保留，可重试。',exact=False).wait_for()
                check('失败保留草稿','遗漏' in textarea.input_value())
                page.locator('#modal [data-ref="save"]').click();page.wait_for_function("() => document.querySelectorAll('#modal .ref-entry').length===2")
                page.get_by_role('tab',name='历史记录',exact=False).click()
                page.locator('#modal .ref-entry').last.locator('summary').first.click()
                page.locator('#modal [data-ref="recurrence"]').last.click();page.locator('#modal [data-ref="save"]').click();page.wait_for_function("() => document.querySelectorAll('#modal .ref-entry').length===3")
                check('两条错因与一次再次发生',len(problems.reflections(vault,qids[0])['items'])==3)
                check('学习状态未变化',mastery_rows(vault)==baseline)
                textarea.fill('尚未保存的下一条观察')
                page.locator('#modal [data-dialog-cancel]').click();page.locator('dialog[open]').last.get_by_text('还有未保存的错因',exact=True).wait_for()
                page.locator('dialog[open]').last.get_by_role('button',name='继续编辑',exact=True).click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('关闭保护保留输入',textarea.input_value()=='尚未保存的下一条观察')
                page.screenshot(path=str(shots/'reflections-modal.png'),full_page=True)
                page.get_by_role('tab',name='历史记录',exact=False).click()
                page.locator('#modal .ref-entry').first.locator('summary').first.click()
                page.locator('#modal [data-ref="recurrence"]').first.click()
                page.locator('dialog[open]').last.get_by_text('还有未保存的错因',exact=True).wait_for(timeout=3000)
                page.locator('dialog[open]').last.get_by_role('button',name='继续编辑',exact=True).click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                page.get_by_role('tab',name='记录本次',exact=True).click()
                check('再次发生不覆盖未存草稿',textarea.input_value()=='尚未保存的下一条观察')
                page.keyboard.press('Escape');page.locator('dialog[open]').last.get_by_text('还有未保存的错因',exact=True).wait_for()
                page.locator('dialog[open]').last.get_by_role('button',name='继续编辑',exact=True).click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('Esc保护草稿',textarea.input_value()=='尚未保存的下一条观察')
                page.locator('#modal [data-qv-nav="next"]').click(timeout=3000)
                page.locator('dialog[open]').last.get_by_text('还有未保存的错因',exact=True).wait_for()
                page.locator('dialog[open]').last.get_by_role('button',name='继续编辑',exact=True).click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('翻题取消保留当前题草稿',textarea.input_value()=='尚未保存的下一条观察')
                page.mouse.click(3,3);page.locator('dialog[open]').last.get_by_text('还有未保存的错因',exact=True).wait_for()
                page.locator('dialog[open]').last.get_by_role('button',name='继续编辑',exact=True).click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('遮罩保护草稿',textarea.input_value()=='尚未保存的下一条观察')
                page.locator('#modal [data-qv-nav="next"]').click()
                page.locator('[data-discard-reflection]').click();page.wait_for_function("!document.querySelector('dialog.is-closing')")
                page.wait_for_function("document.querySelector('#modal .ref-head strong')?.textContent.includes('0 条')")
                page.locator('[data-qv-reflection]').click()
                check('翻到另一题草稿不串题',textarea.input_value()=='')
                page.locator('#modal [data-qv-nav="prev"]').click();page.wait_for_function("document.querySelectorAll('#modal .ref-entry').length===3")
                page.get_by_role('tab',name='历史记录',exact=False).click()
                page.locator('#modal .ref-entry').last.locator('summary').first.click()
                page.locator('#modal [data-ref="revise"]').last.click();textarea.fill('修订：负数乘除前先圈出符号。')
                page.locator('#modal [data-ref="save"]').click();page.wait_for_function("[...document.querySelectorAll('#modal .ref-entry')].some(e=>e.textContent.includes('第 2 版'))")
                page.get_by_role('tab',name='历史记录',exact=False).click()
                page.locator('#modal .ref-entry').first.locator('summary').first.click()
                page.locator('#modal [data-ref="withdraw"]').first.click();page.locator('dialog[open]').last.locator('input').fill('重复记录，保留审计')
                page.locator('dialog[open]').last.locator('[data-dialog-ok]').click();page.wait_for_function("[...document.querySelectorAll('#modal .ref-entry')].some(e=>e.textContent.includes('此记录已撤回'))")
                check('修订撤回留痕',any(e['revision']>1 for e in problems.reflections(vault,qids[0])['items']))
                page.locator('[data-qv-reflection]').click();textarea.fill('');page.locator('#modal [data-dialog-cancel]').click();page.wait_for_selector('#modal',state='detached')
                page.set_viewport_size({'width':390,'height':844});page.reload();page.locator(f'[data-prb="open"][data-id="{pid}"]').click();page.locator('.prb-detail h1').wait_for()
                check('390px无页面横向滚动',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                page.screenshot(path=str(shots/'problems-mobile.png'),full_page=True)
                page.evaluate("document.documentElement.dataset.theme='dark'")
                page.screenshot(path=str(shots/'problems-dark.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1100});page.evaluate("document.documentElement.dataset.theme='light'");page.goto(base+'/#/settings');page.locator('#st-banner-editor textarea').wait_for();page.locator('#st-banner-card').scroll_into_view_if_needed()
                page.locator('[data-banner-preview]').click();page.locator('.st-banner-preview').wait_for();page.screenshot(path=str(shots/'banner-settings.png'),full_page=True)
                page.locator('[data-banner-save]').click();page.get_by_text('已保存，仅影响之后创建的计划。',exact=True).wait_for()
                check('设置真实保存默认提醒',schedule_banner.settings(vault)['enabled'])
                bad=page.request.post(base+'/api/schedule-banner/preview',data={'svg':SVG.replace('<text ','<text onclick="x" ')})
                check('HTTP拒绝危险SVG',bad.status==400)
                key=create_key(vault,scopes=['omrs:read','problem:read','problem:write'])
                op=problem_review.propose(vault,key['key_id'],'create_problem',{'title':'审核后的合成AI假设','request_id':'browser-review'},base)
                page.goto(base+'/#/ai-review?operation='+op['operation_id']);page.locator('[data-action="ai-review.approve"]').wait_for()
                check('审核前没有正式问题',problems.search(vault,query='审核后的')['total']==0)
                page.locator('[data-action="ai-review.approve"]').click();page.wait_for_function("document.body.textContent.includes('当前状态：已执行')")
                check('审核UI执行并读回假设',problems.search(vault,query='审核后的')['items'][0]['basis']=='ai_hypothesis')
                page.screenshot(path=str(shots/'problem-review.png'),full_page=True)
                mark_session_completed(vault,old_session['session_id'])
                session=create_session_from_selection(vault,[{'question_id':qid} for qid in qids])
                for columns in (True,False):
                    data,_=export_schedule_html(vault,session_id=session['session_id'],a4_two_columns=columns)
                    path=evidence/('schedule-double.html' if columns else 'schedule-single.html');path.write_bytes(data)
                    export= context.new_page();export.goto(path.as_uri());export.wait_for_function('window.__OMRS_RESULT && document.getElementById("btnPrint").disabled===false')
                    report=export.evaluate('''() => {const pages=[...document.querySelectorAll('.page')];return {result:window.__OMRS_RESULT,banners:document.querySelectorAll('.schedule-banner').length, heights:pages.map(p=>[...p.querySelectorAll('.col')].map(c=>({top:c.getBoundingClientRect().top,bottom:c.getBoundingClientRect().bottom,last:c.lastElementChild?.getBoundingClientRect().bottom}))),firstTop:pages[0].querySelector('.col').getBoundingClientRect().top, bannerBottom:pages[0].querySelector('.schedule-banner').getBoundingClientRect().bottom};}''')
                    check('双栏' if columns else '单栏',not report['result']['errors'] and report['banners']==1 and report['firstTop']>report['bannerBottom'] and all(c['last'] is None or c['last']<=c['bottom']+.05 for p in report['heights'] for c in p),report)
                    export.emulate_media(media='print');export.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                    check('打印无溢出',not export.evaluate('window.__OMRS_RESULT.errors.length'))
                    export.emulate_media(media='screen')
                    if columns:
                        export.screenshot(path=str(shots/'schedule-banner.png'),full_page=True)
                        export.pdf(path=str(evidence/'schedule-banner.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
                    export.close()
                data,_=export_schedule_html(vault,session_id=session['session_id'],variant='screen');path=evidence/'schedule-screen.html';path.write_bytes(data)
                screen=context.new_page();screen.goto(path.as_uri());screen.locator('.schedule-banner img').wait_for()
                check('离线屏幕版首页提醒',screen.locator('.schedule-banner').count()==1 and screen.locator('.schedule-banner img').evaluate('(e)=>e.complete&&e.naturalWidth>0'))
                screen.screenshot(path=str(shots/'schedule-screen.png'),full_page=True)
                screen.close()
                no_banner=[]
                for name,sid,override in [('关闭',session['session_id'],{'mode':'off'}),('旧计划',old_session['session_id'],None)]:
                    data,_=export_schedule_html(vault,session_id=sid,schedule_banner=override)
                    path=evidence/('schedule-'+('off' if override else 'old')+'.html');path.write_bytes(data)
                    blank=context.new_page();blank.goto(path.as_uri());blank.wait_for_function('window.__OMRS_RESULT && !document.getElementById("btnPrint").disabled')
                    check(name+'无提醒零占位',blank.locator('.schedule-banner').count()==0)
                    no_banner.append(blank.evaluate("[...document.querySelectorAll('.col')].map(c=>[...c.children].map(n=>({text:n.textContent.replace(/EXP-\d+/g,'EXP-IDENTITY'),height:n.getBoundingClientRect().height,top:n.offsetTop})))"));blank.close()
                check('关闭提醒恢复原有几何',no_banner[0]==no_banner[1])
                check('无浏览器脚本错误',not errors,errors)
                browser.close()
        except BaseException:
            traceback.print_exc()
            if 'page' in locals():
                try:page.screenshot(path=str(shots/'failure.png'),full_page=True)
                except Exception:pass
            return 1
        finally:
            proc.terminate();proc.wait(timeout=15)
            (evidence/'problem-e2e.json').write_text(json.dumps({'checks':checks,'errors':errors},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':sys.exit(main())
