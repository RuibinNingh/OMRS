"""完整正文、批量读题和学习时间线；不恢复或回填历史内容。"""
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import Image
from mcp.types import ToolAnnotations

from .. import content_history, drafts, ledger, projections, stats
from ..agent.tools import read
from ..agent.tools.common import sections_of, snippet
from ..common import split_sections
from ..question_images import read_draft_image
from .common import RequestError, date_bounds, page, within_date

SCOPES = {name: 'omrs:read' for name in ('get_questions', 'get_question_content',
          'get_draft_image', 'get_question_history', 'get_learning_history')}


def question_content(vault, uid, section='题目', version='', offset=0, limit=4000, expected_hash=''):
    if offset < 0 or not 1 <= limit <= 8000:
        raise ValueError('正文分页范围不合法')
    row = content_history.projection_row(vault, uid=uid, include_archived=True)
    if version:
        try:
            versions = content_history.content_versions(vault, uid=uid)
        except RuntimeError:
            raise RequestError('not_found', '题目不存在') from None
        if not any(v['hash'] == version and v['available'] for v in versions['versions']):
            raise RequestError('not_found', '该题没有可读取的这个正文版本')
        content = ledger.get_blob(vault, version)
        if content is None or ledger.blob_hash(content) != version:
            raise RequestError('content_conflict', '正文版本校验失败')
    else:
        if not row:
            raise RequestError('not_found', '题目不存在')
        if offset and not expected_hash:
            raise ValueError('当前正文的后续页必须提供 expected_hash')
        try:
            content = content_history.read_question_file(vault, row)
        except OSError:
            raise RequestError('not_found', '题目正文文件不可读取') from None
    current_hash = ledger.blob_hash(content)
    if expected_hash and expected_hash != current_hash:
        raise RequestError('content_conflict', '正文已变化，请从第一页重新读取')
    if section == '正文':
        text = content
    elif section in ('题目', '答案', '错因'):
        text = sections_of(content)[section]
    elif section == '备注':
        text = split_sections(content).get('备注', '').strip()
    else:
        raise ValueError('未知正文分节')
    end = offset + limit
    from ..common import parse_yaml_frontmatter
    from ..question_update import note_of
    meta = parse_yaml_frontmatter(content)
    note = note_of(content)
    return {'uid': uid, 'question_id': meta.get('_omrs_id', ''), 'difficulty': int(meta.get('难度', 5)),
            'note': note[:limit], 'note_total_chars': len(note), 'note_truncated': len(note) > limit,
            'section': section, 'version': version or 'current',
            'content_hash': current_hash, 'content': text[offset:end], 'total_chars': len(text),
            'offset': offset, 'next_offset': end if end < len(text) else None}


def questions(vault, uids, detail=False):
    if not 1 <= len(uids) <= 20 or any(not u.strip() or len(u) > 200 for u in uids):
        raise ValueError('uids 必须是 1 到 20 个非空编号')
    items = []
    for uid in uids:
        try:
            item = read.get_question({'vault': vault}, {'uid': uid})['result']
            if not detail:
                item = {k: v for k, v in item.items() if k not in ('sections', 'records')}
                row = content_history.projection_row(vault, uid=uid.strip())
                item['summary'] = snippet(sections_of(content_history.read_question_file(vault, row))['题目'], '')
            items.append(item)
        except (ValueError, OSError):
            items.append({'uid': uid, 'error': {'code': 'not_found', 'message': '题目不存在或正文不可读取'}})
    return {'items': items, 'total': len(items)}


def question_history(vault, uid, view='reviews', offset=0, limit=50):
    if view == 'content_versions':
        try:
            result = content_history.content_versions(vault, uid=uid, offset=offset, limit=limit, reverse=True)
        except RuntimeError:
            raise RequestError('not_found', '题目不存在') from None
        versions = result.pop('versions')
        return {**result, 'view': view, 'items': versions}
    if not content_history.projection_row(vault, uid=uid):
        raise RequestError('not_found', '题目不存在')
    return {'uid': uid, 'view': view, **stats.get_question_records_page(vault, uid, offset, limit)}


def learning_history(vault, subject='', uid='', since='', until='', before_seq=None, limit=50):
    """SQL 游标按筛选和 seq 读取事实页，修正状态使用当前有界读模型。"""
    bounds = date_bounds(since, until)
    state = projections.rebuild_projection(vault)
    wanted_qid = state['uid_to_question_id'].get(uid) if uid else None
    if uid and not wanted_qid:
        return {'items': [], 'next_before_seq': None}
    def matches(value):
        qid = value.get('question_id') or state['uid_to_question_id'].get(value.get('uid_at_that_time') or value.get('uid'))
        q = state['questions'].get(qid, {})
        return (not uid or qid == wanted_qid) and (not subject or (value.get('subject') or q.get('subject')) == subject)
    clauses, arguments = [], []
    if before_seq is not None:
        clauses.append("c.seq<?")
        arguments.append(before_seq)
    for operator, bound in ((">=", bounds[0]), ("<", bounds[1])):
        if bound:
            clauses.append(f"julianday(c.created_at){operator}julianday(?)")
            arguments.append(bound.isoformat())
    effective_json = "COALESCE(t.payload_json,c.payload_json)"
    if uid:
        clauses.append(f"(EXISTS(SELECT 1 FROM json_tree({effective_json}) j WHERE j.key='question_id' AND j.value=?) OR EXISTS(SELECT 1 FROM session_projection sp,json_tree(sp.items_json) j WHERE sp.session_id=json_extract(c.payload_json,'$.session_id') AND j.key='question_id' AND j.value=?))")
        arguments.extend((wanted_qid, wanted_qid))
    if subject:
        clauses.append(f"(EXISTS(SELECT 1 FROM json_tree({effective_json}) j WHERE j.key IN ('subject','Subject','科目') AND j.value=?) OR EXISTS(SELECT 1 FROM json_tree({effective_json}) j JOIN question_projection qp ON qp.question_id=j.value WHERE j.key='question_id' AND qp.subject=?) OR EXISTS(SELECT 1 FROM session_projection sp,json_tree(sp.items_json) j JOIN question_projection qp ON qp.question_id=j.value WHERE sp.session_id=json_extract(c.payload_json,'$.session_id') AND j.key='question_id' AND qp.subject=?))")
        arguments.extend((subject, subject, subject))
    query = "SELECT c.* FROM commits c LEFT JOIN commits t ON t.commit_id=json_extract(c.payload_json,'$.target_commit_id')"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY c.seq DESC"
    items = []
    with ledger.connect(vault) as db:
        for raw in db.execute(query, arguments):
            c = ledger._row_to_commit(raw)
            if before_seq is not None and c['seq'] >= before_seq:
                continue
            if not within_date(c['created_at'], bounds):
                continue
            payload = c['payload'] or {}
            target_row = db.execute('SELECT * FROM commits WHERE commit_id=?', (payload.get('target_commit_id'),)).fetchone() if payload.get('target_commit_id') else None
            target = ledger._row_to_commit(target_row) if target_row else None
            effective_payload = (target or c)['payload'] or {}
            ctype = (target or c)['commit_type']
            summaries = projections._history_payload_summary(payload, c['commit_type'])
            if ctype == 'review.batch_submit':
                feedbacks = effective_payload.get('feedbacks') or effective_payload.get('reviews') or []
                if target and 'target_review_index' in payload:
                    feedbacks = [(payload['target_review_index'], feedbacks[payload['target_review_index']])] if 0 <= payload['target_review_index'] < len(feedbacks) else []
                else:
                    feedbacks = list(enumerate(feedbacks))
                selected = []
                for index, fb in feedbacks:
                    effective = projections._effective_review(state, (target or c)['commit_id'], index, fb)
                    if not matches(effective or fb):
                        continue
                    key = f"{(target or c)['commit_id']}:{index}"
                    selected.append({**{k: (effective or fb).get(k) for k in ('question_id', 'uid_at_that_time', 'subject', 'question_summary', 'is_correct', 'sub_score')},
                                     'review_index': index, 'retracted': effective is None,
                                     'replaced': key in state['review_replacements'],
                                     'session_retracted': (effective_payload.get('session_id') or fb.get('session_id')) in state['retracted_sessions']})
                if not selected:
                    continue
                summaries['feedbacks'] = selected
            elif subject or uid:
                values = [effective_payload, effective_payload.get('question') or {}, effective_payload.get('before') or {}, effective_payload.get('after') or {}]
                values += effective_payload.get('questions') or effective_payload.get('items') or []
                sid = effective_payload.get('session_id') or (effective_payload.get('session') or {}).get('session_id')
                if sid and sid in state['sessions']:
                    import json
                    values += [u if isinstance(u, dict) else {'uid': u} for u in json.loads(state['sessions'][sid].get('UIDs') or '[]')]
                if not any(matches(v) for v in values if isinstance(v, dict)):
                    continue
            items.append({'seq': c['seq'], 'commit_id': c['commit_id'], 'created_at': c['created_at'],
                          'source': c['source'], 'commit_type': c['commit_type'],
                          'summary': projections._commit_summary(c), 'payload': summaries,
                          'session_retracted': payload.get('session_id') in state['retracted_sessions']})
            if len(items) > limit:
                break
    more = len(items) > limit
    items = items[:limit]
    return {'items': items, 'next_before_seq': items[-1]['seq'] if items and more else None}


def register(server, vault, require, threaded):
    def get_questions(uids: Annotated[list[str], Field(min_length=1, max_length=20)], detail: bool = False):
        require(vault, 'omrs:read')
        return questions(vault, uids, detail)
    def get_question_content(uid: Annotated[str, Field(min_length=1, max_length=200)],
                             section: Literal['题目', '答案', '错因', '备注', '正文'] = '题目', version: str = '',
                             offset: Annotated[int, Field(ge=0)] = 0,
                             limit: Annotated[int, Field(ge=1, le=8000)] = 4000, expected_hash: str = ''):
        require(vault, 'omrs:read')
        return question_content(vault, uid.strip(), section, version, offset, limit, expected_hash)
    def get_draft_image(draft_id: Annotated[str, Field(min_length=1, max_length=200)],
                        image_index: Annotated[int, Field(ge=0, strict=True)]) -> Image:
        require(vault, 'omrs:read')
        raw, fmt = read_draft_image(vault, draft_id, image_index)
        require(vault, 'omrs:read')
        return Image(data=raw, format=fmt)
    def get_question_history(uid: Annotated[str, Field(min_length=1, max_length=200)],
                             view: Literal['reviews', 'content_versions'] = 'reviews',
                             offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=100)] = 50):
        require(vault, 'omrs:read')
        return question_history(vault, uid.strip(), view, offset, limit)
    def get_learning_history(subject: str = '', uid: str = '', since: str = '', until: str = '',
                             before_seq: Annotated[int, Field(ge=1)] | None = None,
                             limit: Annotated[int, Field(ge=1, le=100)] = 50):
        require(vault, 'omrs:read')
        if any(len(v) > 200 for v in (subject, uid, since, until)):
            raise ValueError('筛选值过长')
        return learning_history(vault, subject, uid, since, until, before_seq, limit)
    for fn, title in ((get_questions, '按输入顺序批量读取最多 20 题；默认摘要，可选 detail。'),
                      (get_question_content, '分页读取完整当前正文或已登记历史版本；当前后续页必须携带 expected_hash。'),
                      (get_draft_image, '按 get_draft.source_images 下标读取一张原生完整草稿图，不裁剪或转码。'),
                      (get_question_history, '分页读取有效练习记录或已登记正文版本，只查询不恢复。'),
                      (get_learning_history, '按科目、UID、日期和 before_seq 查询 Ledger 学习及变更时间线，含当前修正状态。')):
        server.add_tool(threaded(fn), name=fn.__name__, description=title,
                        structured_output=False if fn is get_draft_image else None,
                        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
