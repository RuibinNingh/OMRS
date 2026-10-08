"""外部标记整理：技术准备与整批网页提案，模型没有批准能力。"""
from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations
from ..label_plan_prepare import candidates, list_labels as listing, stage
from ..label_plan_review import propose_mcp, authorize_source
from .tool_docs import TOOL_DESCRIPTIONS

SCOPES = {'list_labels':'omrs:read','get_labeling_candidates':'omrs:read',
          'stage_label_plan':('omrs:read','label:write'),'propose_label_plan':('omrs:read','label:write')}
PREPARE_TOOLS = {'stage_label_plan'}


def register(server,vault,require,threaded,web_url):
    def list_labels(cursor:str='',limit:Annotated[int,Field(ge=1,le=20)]=10):
        require(vault,SCOPES['list_labels'])
        return listing(vault,cursor,limit)
    def get_labeling_candidates(scope:dict[str,object]|None=None,label_ids:list[str]|None=None,
                                cursor:str='',limit:Annotated[int,Field(ge=1,le=20)]=20):
        require(vault,SCOPES['get_labeling_candidates'])
        return candidates(vault,scope,label_ids,cursor,limit)
    def stage_label_plan(fragment_id:Annotated[str,Field(min_length=1,max_length=100)],payload:dict[str,object],
                         plan_id:str='',expected_version:Annotated[int,Field(ge=0)]=0):
        token=require(vault,SCOPES['stage_label_plan'])
        authorize_source(vault,'mcp',token.client_id,payload)
        return stage(vault,'mcp',token.client_id,fragment_id,payload,plan_id,expected_version)
    def propose_label_plan(plan_id:Annotated[str,Field(min_length=1,max_length=100)],
                           expected_version:Annotated[int,Field(ge=1)],request_id:Annotated[str,Field(min_length=1,max_length=128)]):
        token=require(vault,SCOPES['propose_label_plan'])
        return propose_mcp(vault,token.client_id,request_id,plan_id,expected_version,web_url)
    for fn in (list_labels,get_labeling_candidates,stage_label_plan,propose_label_plan):
        server.add_tool(threaded(fn),name=fn.__name__,description=TOOL_DESCRIPTIONS[fn.__name__],
                        annotations=ToolAnnotations(readOnlyHint=fn.__name__ in ('list_labels','get_labeling_candidates'),
                           destructiveHint=False,idempotentHint=True,openWorldHint=False))
