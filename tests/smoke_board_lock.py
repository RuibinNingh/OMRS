"""Run: python3 -B tests/smoke_board_lock.py (requires Playwright + Chromium).
Real isolated HTTP/UI/export regression; no production requests or writes.
Paper records in this test represent simulated printing, not a physical printer.
"""
import copy, functools, json, pathlib, socketserver, sys, tempfile, threading, urllib.request
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).resolve().parents[1]; label='standalone'
sys.path.insert(0,str(root))
from omrs.boards import create_board, get_board, record_printed, update_board
from omrs.creation import create_question
from omrs.server import OMRSHandler

def read_board(vault, bid):
    value = get_board(vault, bid)
    assert value is not None, "Test board must exist"
    return value

class QuietHandler(OMRSHandler):
    def log_message(self,fmt,*args): pass

with tempfile.TemporaryDirectory(prefix='omrs-lock-http-vault-') as vault, sync_playwright() as pw:
    first=create_question(vault,subject='数学',category='代数',difficulty=5,question_text='旧纸面测试题 $a+b$')
    new=create_question(vault,subject='数学',category='代数',difficulty=5,question_text='新追加测试题 $c+d$')
    board=create_board(vault,'锁定续印浏览器回归',[first['uid']]); bid=board['id']
    QuietHandler.vault_path=vault
    server=socketserver.TCPServer(('127.0.0.1',0),QuietHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    browser=pw.chromium.launch()
    context=browser.new_context(viewport={'width':1440,'height':1000})
    errors=[]
    def export_layout(mode):
        response=context.request.post(base+'/api/export',data={'format':'board','board_id':bid,'mode':mode})
        assert response.ok,(response.status,response.text()[:200])
        view=context.new_page(); view.on('pageerror',lambda e:errors.append(str(e)))
        view.set_content(response.text(),wait_until='load')
        view.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
        layout=view.evaluate('window.OMRS_LAYOUT')
        return view,layout
    try:
        initial_page,layout=export_layout('all')
        assert len(layout['items'])==1 and layout['pages']==1
        record_printed(vault,bid,'all',layout)
        update_board(vault,bid,print={'locked':True})
        initial=read_board(vault,bid)['printed']
        page=context.new_page(); page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base,wait_until='load'); page.wait_for_function("typeof boardAddToBoard === 'function'")
        page.evaluate("async id => { switchTab('board'); await boardReloadData(); await boardLoad(id); window.__confirmCalls=[]; window.uiConfirm=async (...args)=>{window.__confirmCalls.push(args);return false;}; }",bid)
        page.evaluate("async args => { await boardAddToBoard(args.id,[args.uid],{silent:true}); }",{'id':bid,'uid':new['uid']})
        after=read_board(vault,bid)
        calls=page.evaluate('window.__confirmCalls')
        assert not calls, f'Adding an unprinted question must not prompt for reprint: {calls}'
        assert after['printed']==initial and len(after['items'])==2
        assert after['printed_summary']['new_count']==1
        page.evaluate("async uid=>{await boardSetItemGap(uid,5);await boardFlushSave();}",new['uid'])
        assert read_board(vault,bid)['printed']==initial
        assert page.evaluate('window.__confirmCalls.length')==0
        page.evaluate("async()=>{await boardApplyPrintField('note_ratio',45);await boardFlushSave();}")
        assert page.evaluate('window.__confirmCalls.length')==1,'Real paper layout edit must still require confirmation'
        assert read_board(vault,bid)['printed']==initial,'Cancel must preserve record'
        assert read_board(vault,bid)['print']['note_ratio']==0.5,'Cancel must not change setting'
        page.evaluate("()=>{BOARD_PRINT_MODE='new';boardRender();}")
        page.wait_for_function("document.querySelector('[data-board-primary]')?.textContent.includes('补印新增 1 题')")
        action=page.locator('[data-board-primary]').inner_text()
        increment_page,increment=export_layout('new')
        assert increment['mode']=='new' and len(increment['items'])==1
        assert increment['items'][0]['idx']==2
        segment=increment['items'][0]['segments'][0]
        assert segment['page']==initial['cursor']['page']
        assert abs(segment['top']-initial['cursor']['y'])<=1.0
        assert increment_page.locator('.page.partial .ghost').count()==1
        increment_page.emulate_media(media='print')
        assert increment_page.locator('.ghost').evaluate("e=>getComputedStyle(e).backgroundColor")=='rgba(0, 0, 0, 0)'
        assert errors==[], errors
        result={'base_url':base,'actual_chromium_layout':True,'lock_add_without_confirmation':True,'unprinted_gap_preserves_paper':True,'cancel_layout_change_preserves_paper':True,'ui_primary':action,'incremental_questions':len(increment['items']),'index':increment['items'][0]['idx'],'old_cursor':initial['cursor'],'new_segment_top':segment['top'],'transparent_printed_area':True,'page_errors':errors}
        out=pathlib.Path('/tmp')/f'omrs-lock-{label}-browser.json'; out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        context.close(); browser.close(); server.shutdown(); server.server_close(); thread.join()
