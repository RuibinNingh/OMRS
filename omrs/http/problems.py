"""问题中心Web适配；沿用全站登录、同源与写锁。"""
import sqlite3
from .. import problems


class ProblemsRoutes:
    def _problems_get(self,path,params):
        try:
            if path=='/api/problems':
                result=problems.search(self.vault_path,**{k:v for k,v in params.items() if k in ('query','status','question_id','limit','cursor','sort','deleted')})
            elif path=='/api/problem':
                result={'problem':problems.get(self.vault_path,params.get('id',''))}
            elif path=='/api/reflections':
                result=problems.reflections(self.vault_path,params.get('question_id',''),params.get('limit',50),params.get('cursor',0))
            elif path=='/api/schedule-banner':
                from ..schedule_banner import settings
                result=settings(self.vault_path)
            elif path=='/api/schedule-reminders':
                from ..schedule_reminders import catalog
                result=catalog(self.vault_path,True,params.get('session_id',''))
            else:
                from ..problem_assets import read
                raw,mime=read(self.vault_path,params.get('name',''))
                self.send_response(200)
                self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(raw)))
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; sandbox")
                self.end_headers()
                self.wfile.write(raw)
                return
            self._json({'status':'ok',**result})
        except (ValueError,RuntimeError) as exc:
            self._json({'status':'error','error':getattr(exc,'code','invalid_request'),'msg':str(exc)},getattr(exc,'status',400))
        except (OSError,sqlite3.Error):
            self._json({'status':'error','msg':'问题数据暂时无法读取，请重试'},503)

    def _problems_post(self,path):
        try:
            body=b'' if hasattr(self,'_prepared_json') else self.rfile.read(self.services.http_io.content_length(self))
            data=self.services.http_io.json_body(self,body)
            if path=='/api/schedule-banner/preview':
                from ..schedule_banner import normalize
                result={'snapshot':normalize(data.get('svg',''))}
            elif path=='/api/schedule-banner':
                from ..schedule_banner import save_settings
                result=save_settings(self.vault_path,data)
            elif path.startswith('/api/schedule-reminders/'):
                from .. import schedule_reminders as reminders
                if path.endswith('/generate'):
                    result=reminders.generate(self.vault_path,data.get('prompt'),data.get('style','steps'))
                elif path.endswith('/create'):
                    result=reminders.create(self.vault_path,data.get('name'),data.get('svg'),data.get('request_id'),
                        source='AI 生成' if data.get('source')=='ai' else '手动导入')
                else:
                    result=reminders.delete(self.vault_path,data.get('id'),data.get('expected_revision'))
            else:
                result=problems.execute(self.vault_path,data.get('action'),data.get('data',{}))
            self._json({'status':'ok',**result})
        except (ValueError,RuntimeError) as exc:
            self._json({'status':'error','error':getattr(exc,'code','invalid_request'),'msg':str(exc)},getattr(exc,'status',400))
        except (OSError,sqlite3.Error):
            self._json({'status':'error','msg':'问题数据暂时无法保存，草稿已保留，请重试'},503)
