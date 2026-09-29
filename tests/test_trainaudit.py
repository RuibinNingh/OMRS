"""评测不把漏检当成功，复核持久化和并发边界。"""
import json
from pathlib import Path
import tempfile
import unittest
from omrs import trainaudit as a
from tools.boxdetect.audit import immutable, parse_response, cost
from tools.boxdetect.common import preserve_splits


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'audits/a'
        immutable(self.folder/'audit.json',{'id':'a','cases':[{'id':'q','sample':'s','role':'question'},{'id':'a','sample':'s','role':'answer','structural_error':'missing'}]})
        immutable(self.folder/'q.json',{'state':'done','judgment':{'verdict':'usable'}})
        immutable(self.folder/'a.json',{'state':'missing','judgment':{'verdict':'unusable'}})

    def test_missing_counts_in_denominator(self):
        s=a.summary(self.root,'a');self.assertEqual((s['images'],s['raw_passed'],s['missing_images']),(1,0,1))
        a.save_review(self.root,'a','a',0,'correct','usable')
        self.assertEqual(a.summary(self.root,'a')['reviewed_passed'],0)

    def test_review_cannot_turn_call_error_into_a_pass(self):
        folder=self.root/'audits/error'
        immutable(folder/'audit.json',{'id':'error','cases':[{'id':r,'sample':'s','role':r} for r in ('question','answer')]})
        immutable(folder/'question.json',{'state':'done','judgment':{'verdict':'usable'}})
        immutable(folder/'answer.json',{'state':'error','error':'输出截断'})
        a.save_review(self.root,'error','answer',0,'correct','usable',source='executor')
        report=a.summary(self.root,'error')
        self.assertEqual((report['images'],report['raw_passed'],report['reviewed_passed']),(1,0,0))

    def test_review_history_conflict_and_user_precedence(self):
        a.save_review(self.root,'a','q',0,'correct','unusable',source='user')
        with self.assertRaises(a.Conflict):a.save_review(self.root,'a','q',0,'agree')
        a.save_review(self.root,'a','q',1,'agree',source='executor')
        h=a.reviews(self.root,'a','q');self.assertEqual(len(h),2)
        self.assertEqual(a.effective({'judgment':{'verdict':'usable'}},h),'unusable')
        self.assertEqual(a.result(self.root,'a','q')['judgment']['verdict'],'usable')

    def test_read_does_not_create_review_db(self):
        self.assertEqual(a.reviews(self.root,'a'),[])
        self.assertFalse((self.root/'reviews.sqlite3').exists())

    def test_immutable_and_paths(self):
        with self.assertRaises(FileExistsError):immutable(self.folder/'q.json',{})
        with self.assertRaises(ValueError):a.audit(self.root,'../a')
        (self.root/'audits/escape').symlink_to('/tmp')
        with self.assertRaises(ValueError):a.audit(self.root,'escape')

    def test_parser_truncation_and_inconsistent_verdict(self):
        value={'verdict':'usable','missing_content':[],'extra_content':[],'cut_characters':False,'evidence':'完整字母'}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
        self.assertEqual(parse_response(response),value)
        response['choices'][0]['finish_reason']='length'
        with self.assertRaises(ValueError):parse_response(response)
        response['choices'][0]['finish_reason']='stop';value['cut_characters']=True
        response['choices'][0]['message']['content']=json.dumps(value)
        with self.assertRaises(ValueError):parse_response(response)
        self.assertAlmostEqual(cost({'prompt_tokens':1000,'completion_tokens':1000}),.0015)

    def test_frozen_partitions_and_bridge(self):
        previous={'train':['t'],'val':['v'],'test':['r']}
        split=preserve_splits([['t','newt'],['v','newv'],['r','newr']],previous,1)
        self.assertEqual(split['train'],['newt','t']);self.assertEqual(split['val'],['v'])
        self.assertEqual(split['quarantine'],['newr','newv'])
        with self.assertRaises(ValueError):preserve_splits([['t','v']],previous,1)

if __name__=='__main__':unittest.main()


class RunnerTests(unittest.TestCase):
    def test_retry_cache_resume_budget_and_truncation(self):
        import io
        import urllib.error
        from unittest.mock import patch
        from tools.boxdetect.audit import run
        from tools.boxdetect.common import sha256, atomic_json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'audits/a';(out/'images').mkdir(parents=True)
            (out/'images/i.png').write_bytes(b'fake');(out/'prompt.txt').write_text('测试提示')
            immutable(out/'audit.json',{'id':'a','prompt_sha256':sha256(out/'prompt.txt'),'cases':[{'id':'c','sample':'s','role':'answer','original':'i','crop':'i','source_sha256':'a','crop_sha256':sha256(out/'images/i.png')}],'resources':{'i':'i.png'}})
            cfg=root/'cfg.json';cfg.write_text(json.dumps({'agent_model':'deepseek-flash','agent_base_url':'https://invalid.example/v1','agent_api_key':'test-secret'}))
            value={'verdict':'usable','missing_content':[],'extra_content':[],'cut_characters':False,'evidence':'完整'}
            response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],'usage':{'prompt_tokens':100,'completion_tokens':100}}
            with patch('urllib.request.urlopen',side_effect=[urllib.error.HTTPError('x',429,'busy',{},None),io.BytesIO(json.dumps(response).encode())]) as call, patch('time.sleep'):
                run(out,cfg);self.assertEqual(call.call_count,2)
                run(out,cfg);self.assertEqual(call.call_count,2)
            self.assertEqual(json.loads((root/'content-round-1.json').read_text())['requests'],2)
            self.assertEqual(len(list((out/'attempts').glob('*.json'))),2)
            self.assertNotIn('test-secret',(out/'c.json').read_text())
            # 另一评测复用相同输入；不消耗请求预算。
            import shutil
            other=root/'audits/b';shutil.copytree(out,other);(other/'c.json').unlink()
            with patch('urllib.request.urlopen') as call:
                run(other,cfg);call.assert_not_called()
            self.assertEqual(json.loads((other/'c.json').read_text())['state'],'cached')
            (other/'images/i.png').write_bytes(b'changed')
            with patch('urllib.request.urlopen') as call, self.assertRaises(ValueError):run(other,cfg)
            call.assert_not_called()
            (other/'images/i.png').write_bytes(b'fake')
            (other/'c.json').unlink();meta=json.loads((other/'audit.json').read_text());meta['cases'][0]['source_sha256']='changed';atomic_json(other/'audit.json',meta)
            atomic_json(root/'content-round-1.json',{'requests':300,'cost_usd':0,'unknown_usage':0})
            with patch('urllib.request.urlopen') as call, self.assertRaises(RuntimeError):
                run(other,cfg)
            call.assert_not_called()


class AuditHTTPTests(unittest.TestCase):
    from tests.test_trainpanel import PanelTests
    setUp=PanelTests.setUp
    start_http=PanelTests.start_http
    write=PanelTests.write

    def test_routes_origins_conflicts_and_registered_images(self):
        import http.client
        self.write('audits/a/audit.json',{'id':'a','cases':[{'id':'c','sample':'s','role':'answer','original':'i'}],'resources':{'i':'i.png'}})
        self.write('audits/a/c.json',{'state':'done','judgment':{'verdict':'usable'}})
        image=self.root/'audits/a/images/i.png';image.parent.mkdir();image.write_bytes(b'image')
        port=self.start_http()
        def req(method,path,body=None,headers=None):
            conn=http.client.HTTPConnection('127.0.0.1',port)
            conn.request(method,path,json.dumps(body) if body is not None else None,headers or {})
            r=conn.getresponse();data=r.read();conn.close();return r.status,data
        self.assertEqual(req('GET','/api/trainpanel/audits')[0],200)
        self.assertEqual(req('GET','/api/trainpanel/audit-image?id=a&resource=i')[1],b'image')
        for url in ('/api/trainpanel/audit?id=..','/api/trainpanel/audit-image?id=a&resource=../c.json'):
            self.assertEqual(req('GET',url)[0],400)
        body={'audit':'a','case':'c','revision':0,'action':'correct','verdict':'unusable'}
        self.assertEqual(req('POST','/api/trainpanel/review',body,{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(req('POST','/api/trainpanel/review',body)[0],200)
        self.assertEqual(req('POST','/api/trainpanel/review',body)[0],409)
        self.assertEqual(req('GET','/api/trainpanel/reviews?id=a&case=c')[0],200)


class TrainingBoundaryTests(unittest.TestCase):
    def test_cgroup_remaining_wins_over_host_and_root_is_unlimited(self):
        from unittest.mock import patch
        from tools.boxdetect.train import memory_available
        gib=1024**3
        def read(path,*args,**kwargs):
            name=str(path)
            if name=='/proc/meminfo':return 'MemAvailable: 20000000 kB\n'
            if name=='/proc/self/cgroup':return '0::/test\n'
            if name=='/sys/fs/cgroup/test/memory.max':return str(5*gib)
            if name=='/sys/fs/cgroup/test/memory.current':return str(3*gib)
            raise FileNotFoundError(name)
        with patch.object(Path,'read_text',read),patch.object(Path,'exists',return_value=False):
            self.assertEqual(memory_available(),2*gib)

    def test_registered_chat_ready_data_and_conflicting_annotations(self):
        from omrs.inbox import register_chat_training
        from tests.test_annotate import make_png
        from tools.boxdetect.build_dataset import inspect_sources
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            raw=make_png(40,80);sha=hashlib.sha256(raw).hexdigest()
            boxes=[{'id':'q','section':'题目','box':dict(x=0,y=0,w=1,h=.4),'box_origin':'manual'},
                   {'id':'a','section':'答案','box':dict(x=0,y=.5,w=1,h=.4),'box_origin':'ai_edited'}]
            register_chat_training(temp,sha,raw,'d1',boxes)
            rows,excluded=inspect_sources(temp)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],'chat')
            register_chat_training(temp,sha,raw,'d2',boxes)
            rows,excluded=inspect_sources(temp);self.assertEqual(len(rows),1)
            self.assertTrue(any('去重' in e['reason'] for e in excluded))
            boxes[0]['box']['h']=.3
            register_chat_training(temp,sha,raw,'d2',boxes)
            rows,excluded=inspect_sources(temp);self.assertEqual(rows,[])
            self.assertTrue(all('冲突' in e['reason'] for e in excluded))

    def test_reweight_rejects_nontrain_and_preserves_validation(self):
        from tools.boxdetect.reweight import build
        from tools.boxdetect.common import atomic_json,sha256
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);dataset=root/'datasets/d';dataset.mkdir(parents=True)
            atomic_json(dataset/'manifest.json',{'version':'d','splits':{'train':['t'],'val':['v'],'test':[]},'samples':[
                {'id':'t','split':'train','strips':[{'name':'t'}]},{'id':'v','split':'val','strips':[{'name':'v'}]}]})
            folder=root/'audits/a'
            meta={'id':'a','split':'test','manifest_sha256':sha256(dataset/'manifest.json'),'cases':[{'id':'c','sample':'t','role':'answer','structural_error':'extra'}]}
            atomic_json(folder/'audit.json',meta);atomic_json(folder/'c.json',{'state':'done','judgment':{'verdict':'usable'}})
            a.save_review(root,'a','c',0,'agree',source='executor')
            with self.assertRaises(ValueError):build(dataset,folder,root/'weighted')
            meta['split']='train';atomic_json(folder/'audit.json',meta)
            result=build(dataset,folder,root/'weighted')
            self.assertEqual(result['weighted_strips'],2)
            weighted=json.loads((root/'weighted/manifest.json').read_text())
            self.assertEqual(weighted['splits']['val'],['v'])
            self.assertEqual(weighted['samples'][1]['sampling_weight'],1)
