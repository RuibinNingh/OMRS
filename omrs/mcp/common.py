"""MCP 领域契约：稳定错误、分页、请求身份和摘要。"""
import datetime
import hashlib
import json


class RequestError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def request_identity(key_id, tool, request_id, payload):
    if not isinstance(request_id, str) or not 1 <= len(request_id.strip()) <= 128:
        raise ValueError('request_id 必须是 1 到 128 个字符')
    request_id = request_id.strip()
    if any(ord(ch) < 32 or ch in '?#/\\' for ch in request_id):
        raise ValueError('request_id 包含不允许的字符')
    return fingerprint([key_id, tool, request_id]), fingerprint(payload)


def page(items, offset=0, limit=50):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('offset 必须非负，limit 必须为 1 到 100')
    end = offset + limit
    return {'items': items[offset:end], 'total': len(items), 'offset': offset,
            'next_offset': end if end < len(items) else None}


def date_bounds(since='', until=''):
    """日期为含首尾的日界线；时间戳为含起点、不含终点。"""
    def parse(value, end=False):
        if not value:
            return None
        try:
            if len(value) == 10:
                day = datetime.date.fromisoformat(value)
                if end:
                    day += datetime.timedelta(days=1)
                return datetime.datetime.combine(day, datetime.time(), datetime.timezone.utc)
            stamp = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
            return stamp.replace(tzinfo=datetime.timezone.utc) if stamp.tzinfo is None else stamp
        except (ValueError, TypeError):
            raise ValueError('日期必须是 YYYY-MM-DD 或 ISO-8601 时间') from None
    left, right = parse(since), parse(until, True)
    if left and right and left >= right:
        raise ValueError('起始日期必须早于结束边界')
    return left, right


def within_date(value, bounds):
    if not any(bounds):
        return True
    try:
        stamp = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False
    left, right = bounds
    return (left is None or stamp >= left) and (right is None or stamp < right)
