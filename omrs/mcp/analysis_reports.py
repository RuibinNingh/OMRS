"""受限统计视图和只新建的幂等报告保存。"""
import hashlib
from typing import Annotated, Literal
from pydantic import Field
from mcp.types import ToolAnnotations
from .. import analytics, reports
from .common import RequestError, page
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'get_analytics': 'omrs:read', 'list_reports': 'omrs:read',
          'get_report': 'omrs:read', 'create_report': 'report:create'}


def register(server, vault, require, threaded):
    def get_analytics(view: Literal['overview', 'trends', 'accuracy', 'distributions', 'weak_spots', 'forecast'] = 'overview',
                      subject: str = '', category: str = '', since: str = '', until: str = ''):
        require(vault, 'omrs:read')
        if any(len(v) > 200 for v in (subject, category, since, until)):
            raise ValueError('筛选值过长')
        result = analytics.get_analytics(vault, subject, category, since, until)
        names = {'overview': ['overview', 'subjects', 'categories'], 'trends': ['behavior'],
                 'accuracy': ['accuracy', 'subjects', 'categories'], 'distributions': ['distributions'],
                 'weak_spots': ['weak_spots', 'categories'], 'forecast': ['forecast', 'review_alert']}
        return {'view': view, 'scope': {'subject': subject, 'category': category, 'since': since, 'until': until},
                'generated_at': result['generated_at'],
                'snapshot': '熟练度、薄弱项和预测是当前快照；日期仅筛选练习行为指标',
                **{name: result[name] for name in names[view]}}
    def list_reports(offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=100)] = 50):
        require(vault, 'omrs:read')
        return page(reports.list_reports(vault), offset, limit)
    def get_report(report_id: Annotated[str, Field(min_length=1, max_length=200)],
                   offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=8000)] = 4000):
        require(vault, 'omrs:read')
        meta = next((it for it in reports.list_reports(vault) if it['id'] == report_id), None)
        if not meta:
            raise RequestError('not_found', '报告不存在')
        text = reports.get_report_html(vault, report_id).decode('utf-8')
        end = offset + limit
        return {'report_id': report_id, 'metadata': meta, 'html': text[offset:end], 'total_chars': len(text),
                'content_hash': hashlib.sha256(text.encode()).hexdigest(), 'offset': offset,
                'next_offset': end if end < len(text) else None}
    def create_report(name: Annotated[str, Field(min_length=1, max_length=200)], html: str,
                      request_id: Annotated[str, Field(min_length=1, max_length=128)]):
        token = require(vault, 'report:create')
        return reports.create_mcp_report(vault, name, html, token.client_id, request_id,
                                        lambda: require(vault, 'report:create'))
    for fn in (get_analytics, list_reports, get_report, create_report):
        server.add_tool(threaded(fn), name=fn.__name__, description=TOOL_DESCRIPTIONS[fn.__name__],
                        annotations=ToolAnnotations(readOnlyHint=fn is not create_report, destructiveHint=False,
                                                    idempotentHint=True, openWorldHint=False))
