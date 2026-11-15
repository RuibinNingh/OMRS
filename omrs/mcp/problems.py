"""外部MCP问题工具；独立scope与网页审核，复用原生领域事务。"""
from mcp.types import ToolAnnotations
from .. import problems as domain, problem_review
from .tool_docs import TOOL_DESCRIPTIONS

READ=('omrs:read','problem:read')
WRITE=(*READ,'problem:write')
SCOPES={name:WRITE for name in domain.ACTIONS}
SCOPES.update({name:READ for name in ('search_problems','get_problem','get_reflections')})


def register(server,vault,require,threaded,web_url):
    def search_problems(query:str='',status:str='',question_id:str='',limit:int=50,cursor:str=''):
        require(vault,READ)
        return domain.search(vault,query,status,question_id,limit,cursor)
    def get_problem(id:str):
        require(vault,READ)
        return domain.get(vault,id)
    def get_reflections(question_id:str,limit:int=50,cursor:str=''):
        require(vault,READ)
        return domain.reflections(vault,question_id,limit,cursor)
    def propose(name,data):
        token=require(vault,WRITE)
        return problem_review.propose(vault,token.client_id,name,data,web_url)
    def create_problem(title:str,request_id:str,description_md:str='',question_ids:list[str]|None=None,subject:str=''):
        return propose('create_problem',dict(title=title,request_id=request_id,description_md=description_md,question_ids=question_ids or [],subject=subject))
    def update_problem(id:str,expected_revision:int,request_id:str,title:str|None=None,description_md:str|None=None,status:str|None=None,reason:str=''):
        return propose('update_problem',{k:v for k,v in locals().items() if k!='propose' and v is not None})
    def link_problem_questions(id:str,expected_revision:int,question_ids:list[str],request_id:str):
        return propose('link_problem_questions',dict(id=id,expected_revision=expected_revision,question_ids=question_ids,request_id=request_id))
    def unlink_problem_questions(id:str,expected_revision:int,question_ids:list[str],request_id:str):
        return propose('unlink_problem_questions',dict(id=id,expected_revision=expected_revision,question_ids=question_ids,request_id=request_id))
    def add_reflection_entry(question_id:str,content_md:str,request_id:str,problem_ids:list[str]|None=None,recurrence_of:str='',occurred_at:str=''):
        return propose('add_reflection_entry',dict(question_id=question_id,content_md=content_md,request_id=request_id,problem_ids=problem_ids or [],recurrence_of=recurrence_of,occurred_at=occurred_at))
    def revise_reflection_entry(id:str,expected_revision:int,request_id:str,reason:str,content_md:str|None=None,withdrawn:bool|None=None):
        return propose('revise_reflection_entry',{k:v for k,v in locals().items() if k!='propose' and v is not None})
    def add_problem_asset(data_base64:str,request_id:str):
        return propose('add_problem_asset',dict(data_base64=data_base64,request_id=request_id))
    for fn in (search_problems,get_problem,get_reflections,create_problem,update_problem,link_problem_questions,unlink_problem_questions,add_reflection_entry,revise_reflection_entry,add_problem_asset):
        server.add_tool(threaded(fn),name=fn.__name__,description=TOOL_DESCRIPTIONS[fn.__name__],annotations=ToolAnnotations(readOnlyHint=fn.__name__ not in domain.ACTIONS,destructiveHint=False,idempotentHint=True,openWorldHint=False))
