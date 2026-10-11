"""作业帮题干与答案配对。"""
import json
from .direct import UpstreamError, reject_login_notice

def as_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value

def normalize_questions(value):
    """逐位置读取已解码候选，不递归合并相似题或错配题干与答案。"""
    value = as_json(value)
    if isinstance(value, dict) and 'body' in value:
        value = value['body']
    if isinstance(value, dict) and 'errNo' in value and value['errNo'] not in (0, '0'):
        raise UpstreamError('作业帮未返回答案，请稍后重试或更新本地会话。', kind='protocol')
    if isinstance(value, dict) and 'data' in value and 'question' not in value and 'tidInfo' not in value:
        value = as_json(value['data'])
    if isinstance(value, dict) and isinstance(value.get('answers'), dict):
        pages = value['answers'].get('mainPageInfo') or []
        if any(isinstance(p, str) and not p.lstrip().startswith(('{', '[')) for p in pages):
            raise UpstreamError('响应仍为加密内容。请通过手机桥接获取已解码的结果。', kind='protocol')
    elif isinstance(value, list):
        pages = value
    else:
        pages = [value]
    questions = []

    def collect(page, location):
        page = as_json(page)
        if isinstance(page, list):
            for item in page:
                collect(item, location)
            return
        if not isinstance(page, dict):
            return
        if isinstance(page.get('questionData'), (dict, str)):
            collect(page['questionData'], location)
            return
        if 'tidInfo' in page:
            tid = as_json(page['tidInfo'])
            if isinstance(tid, list):
                # 明确的候选保持独立，不将相似题标成精确匹配。
                for candidate in tid:
                    collect({'queryInfo': page.get('queryInfo', {}), 'tidInfo': candidate}, location)
                return
            if not isinstance(tid, dict):
                return
            question, answers = tid.get('question'), tid.get('answer')
            location = (page.get('queryInfo') or {}).get('locIndex', location)
        else:
            question, answers = page.get('question'), page.get('answer')
            location = page.get('location_index', location)
        if question is not None and answers is not None:
            if isinstance(question, str):
                question = {'content': question, 'picList': []}
            if isinstance(answers, dict):
                answers = [answers]
            elif isinstance(answers, str):
                answers = [{'content': answers, 'picList': [], 'type': 0}]
            if isinstance(question, dict) and isinstance(answers, list):
                query = page.get('queryInfo') or {}
                questions.append({'location_index': location, 'result_index': query.get('resultIndex', len(questions)),
                                  'match_type': query.get('matchType'), 'question': question, 'answer': answers})
            return
        # 兼容正文的外层包装。
        for key in ('data', 'pageData', 'pageDate', 'result'):
            if key in page:
                collect(page[key], location)

    for index, page in enumerate(pages):
        collect(page, index)
    if not questions:
        raise UpstreamError('作业帮未返回可读取的题目。请拍清楚题干，或缩小到一道题重试。', kind='protocol')
    reject_login_notice(questions)
    return questions
