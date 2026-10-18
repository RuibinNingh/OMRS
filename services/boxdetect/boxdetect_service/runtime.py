"""实际加载的模型、串行推理与可恢复的模型应用。"""
import base64
import binascii
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
from .errors import ApiError
from .model import model_info
from .slicing import slice_plan, merge_strip_boxes


class Runtime:
    def __init__(self, model_dir, config, store, detector_type):
        self.config,self.store,self.detector_type=config,store,detector_type
        self.lock=threading.Lock()
        self.slots=threading.BoundedSemaphore(8)
        self.waiting=0
        self.counter_lock=threading.Lock()
        initial=Path(model_dir).resolve()
        saved=store.get('model_selection',{})
        self.path=Path(saved.get('current',str(initial))).resolve()
        self.metadata,self.detector=self.load(self.path)
        self.revision=saved.get('revision',0)
        self.previous=saved.get('previous')
        self.started=time.time()

    def load(self, path):
        info=model_info(path)
        detector=self.detector_type(path/'model.onnx',conf=float(info['conf']))
        if detector.size!=info['imgsz']: raise ValueError('模型实际输入尺寸与元数据不一致')
        if model_info(path)!=info: raise ValueError('模型在加载期间改变')
        return info,detector

    def status(self):
        return {'service':'boxdetect','protocol':1,'model':self.metadata,'revision':self.revision,
                'paused':self.store.get('paused',False),'waiting':self.waiting,'started_at':self.started,
                'history_retention':self.store.retention(),'limits':{'image_bytes':self.config.max_image_bytes,
                'pixels':self.config.max_pixels,'per_key_per_minute':self.store.get('per_key_per_minute',self.config.detect_per_minute),'concurrency':1,'queue':8}}

    def models(self):
        rows=[{'id':'current','model':self.metadata,'current':True}]
        if self.previous:
            try: rows.append({'id':'previous','model':model_info(Path(self.previous)),'current':False})
            except (ValueError,OSError): pass
        if self.config.models_dir:
            root=Path(self.config.models_dir).resolve()
            if root.is_dir():
                for path in sorted(root.iterdir())[:100]:
                    if not path.is_dir() or path.is_symlink() or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',path.name): continue
                    try:
                        rows.append({'id':path.name,'model':model_info(path),'current':path.resolve()==self.path})
                    except (ValueError,OSError,KeyError): continue
        return rows

    def apply(self, body, actor):
        if set(body)-{'action','model_id','revision','request_id'} or body.get('action') not in ('activate','rollback'):
            raise ApiError('operation_invalid','模型操作不合法')
        rid=body.get('request_id','')
        if not isinstance(rid,str) or not re.fullmatch(r'[a-f0-9]{32}',rid): raise ApiError('operation_invalid','需要安全请求编号')
        fingerprint=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        with self.store.lock,self.store.connect() as db:
            saved=db.execute('SELECT * FROM operations WHERE id=?',(rid,)).fetchone()
            if saved:
                if saved['body_hash']!=fingerprint: raise ApiError('request_conflict','请求编号已用于其他模型操作',409)
                return dict(saved)
        if not self.lock.acquire(blocking=False): raise ApiError('busy','推理或模型操作进行中，请稍后重试',409)
        try:
            if type(body.get('revision')) is not int or body['revision']!=self.revision: raise ApiError('revision_conflict','模型状态已更新，请刷新后操作',409)
            if body['action']=='rollback':
                if not self.previous: raise ApiError('model_missing','没有可恢复的上一模型')
                target=Path(self.previous)
            else:
                ident=body.get('model_id','')
                if not self.config.models_dir or not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ident): raise ApiError('model_missing','只能选择服务器已登记模型')
                root=Path(self.config.models_dir).resolve();target=root/ident
                if target.is_symlink() or target.resolve().parent!=root: raise ApiError('model_missing','模型目录不合法')
            before=self.metadata.copy()
            with self.store.lock,self.store.connect() as db:
                db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?)',(rid,time.time(),body['action'],actor,'running',json.dumps(before),None,None,fingerprint))
            try:
                metadata,detector=self.load(target)
                from PIL import Image
                with Image.new('RGB',(32,32),'white') as test: detector(test)
                selection={'current':str(target.resolve()),'previous':str(self.path),'revision':self.revision+1}
                # 指针、操作回执同事务发布，只有成功持久化后才替换内存模型。
                with self.store.lock,self.store.connect() as db:
                    db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',('model_selection',json.dumps(selection)))
                    db.execute("UPDATE operations SET state='done',after_model=? WHERE id=?",(json.dumps(metadata),rid))
                self.previous=str(self.path);self.path=target.resolve();self.metadata,self.detector=metadata,detector;self.revision+=1
            except Exception:
                with self.store.lock,self.store.connect() as db:
                    db.execute("UPDATE operations SET state='failed',error='模型预检或应用失败，保留原模型' WHERE id=?",(rid,))
            with self.store.lock,self.store.connect() as db:
                return dict(db.execute('SELECT * FROM operations WHERE id=?',(rid,)).fetchone())
        finally: self.lock.release()

    def detect(self, body, key_id, source_ip, peer_ip, *, legacy=False):
        if set(body)-{'image','request_id','source','layout','width','height'}: raise ApiError('body_invalid','框选请求包含未知字段')
        encoded=body.get('image')
        if not isinstance(encoded,str): raise ApiError('image_invalid','需要图片 dataURL')
        rid=body.get('request_id') or __import__('secrets').token_hex(16)
        if not isinstance(rid,str) or not re.fullmatch(r'[a-f0-9]{32}',rid): raise ApiError('request_invalid','请求编号必须为32位十六进制')
        source=body.get('source','legacy' if legacy else 'api')
        if source not in ('inbox','draft','test','api','legacy'): raise ApiError('source_invalid','调用入口不合法')
        digest=hashlib.sha256((encoded+str(legacy)).encode()).hexdigest()
        ident,reused,status=self.store.begin(key_id,rid,digest,source,source_ip,peer_ip,self.metadata)
        if reused is not None: return reused,status
        started=time.monotonic();admitted=False;waiting=False
        try:
            if self.store.get('paused',False): raise ApiError('paused','框选服务已暂停接单',503)
            self.store.rate('detect',key_id,self.store.get('per_key_per_minute',self.config.detect_per_minute))
            if not self.slots.acquire(blocking=False): raise ApiError('busy','框选队列已满，请稍后重试',429)
            admitted=True
            with self.counter_lock: self.waiting+=1
            waiting=True
            with self.lock:
                with self.counter_lock: self.waiting-=1
                waiting=False
                # 排队期间吊销、暂停与换模型均以真正执行时状态为准。
                if self.store.get('paused',False): raise ApiError('paused','框选服务已暂停接单',503)
                if key_id not in ('admin','legacy'):
                    with self.store.lock,self.store.connect() as db:
                        row=db.execute('SELECT 1 FROM api_keys WHERE id=? AND revoked_at IS NULL',(key_id,)).fetchone()
                        if not row: raise ApiError('key_invalid','调用密钥无效或已吊销',401)
                model=self.metadata.copy()
                with self.store.lock,self.store.connect() as db: db.execute('UPDATE requests SET model=? WHERE id=?',(json.dumps(model),ident))
                from PIL import Image
                try:
                    head,raw=encoded.split(',',1)
                    if head not in ('data:image/png;base64','data:image/jpeg;base64','data:image/gif;base64'): raise ValueError()
                    data=base64.b64decode(raw,validate=True)
                    if not data or len(data)>self.config.max_image_bytes: raise ValueError()
                    with Image.open(io.BytesIO(data)) as image:
                        width,height=image.size
                        if image.format not in ('PNG','JPEG','GIF') or width*height>self.config.max_pixels or (not legacy and height/max(width,1)>100): raise ValueError()
                        image.load()
                        mime={'PNG':'image/png','JPEG':'image/jpeg','GIF':'image/gif'}[image.format]
                        self.store.image(ident,data,{'content_type':mime,'width':width,'height':height,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                        outputs=[];parts=[]
                        plan=[(0.,1.)] if legacy else slice_plan(width,height)
                        for y0,y1 in plan:
                            begin=time.monotonic()
                            with image.crop((0,int(y0*height),width,int(y1*height))).convert('RGB') as strip:
                                # 与原客户端 JPEG85 输入一致，保证整图迁移结果可对照。
                                if not legacy:
                                    stream=io.BytesIO();strip.save(stream,'JPEG',quality=85)
                                    with Image.open(io.BytesIO(stream.getvalue())) as decoded: boxes=self.detector(decoded)
                                else: boxes=self.detector(strip)
                            outputs.append({'y0':y0,'y1':y1,'boxes':boxes})
                            parts.append({'y0':y0,'y1':y1,'elapsed_ms':round((time.monotonic()-begin)*1000),'boxes':len(boxes)})
                        boxes=outputs[0]['boxes'] if legacy else merge_strip_boxes(outputs)
                except (ValueError,OSError,binascii.Error,Image.DecompressionBombError):
                    raise ApiError('image_invalid','图片格式、大小或像素不符合要求') from None
                if legacy:
                    result={'boxes':[{'label':b['role'],'bbox_2d':[b['x'],b['y'],min(1.,b['x']+b['w']),min(1.,b['y']+b['h'])],'confidence':b.get('conf',.5)} for b in boxes]}
                else:
                    result={'status':'ok','request_id':rid,'history_id':ident,'boxes':boxes,'width':width,'height':height,'strips':len(parts),'parts':parts,'model':model,'elapsed_ms':round((time.monotonic()-started)*1000)}
                if key_id not in ('admin','legacy'):
                    with self.store.lock,self.store.connect() as db:
                        if not db.execute('SELECT 1 FROM api_keys WHERE id=? AND revoked_at IS NULL',(key_id,)).fetchone():
                            raise ApiError('key_invalid','调用密钥已吊销，结果未返回',401)
                status=200
        except ApiError as error: result={'status':'error','code':error.code,'msg':error.message,'request_id':rid};status=error.status
        except Exception: result={'status':'error','code':'inference_failed','msg':'模型推理失败，请查看服务状态','request_id':rid};status=500
        finally:
            if waiting:
                with self.counter_lock: self.waiting-=1
            if admitted: self.slots.release()
        self.store.finish(ident,result,status,round((time.monotonic()-started)*1000))
        return result,status
