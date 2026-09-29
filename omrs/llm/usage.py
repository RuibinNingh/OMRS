"""OpenAI 兼容响应的用量归一化。缓存属于输入，思考属于输出。"""


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def normalize_usage(raw, *, estimated_output=None, scope="main", request_id=None, round_id=None):
    """保留旧字段；缺失和异常字段用 None 表示，绝不把未知记为零。"""
    raw = raw if isinstance(raw, dict) else {}
    details = raw.get("prompt_tokens_details") if isinstance(raw.get("prompt_tokens_details"), dict) else {}
    comp = raw.get("completion_tokens_details") if isinstance(raw.get("completion_tokens_details"), dict) else {}
    invalid = False

    def field(obj, key):
        nonlocal invalid
        if key not in obj:
            return None
        value = _count(obj[key])
        if value is None:
            invalid = True
        return value

    input_total = field(raw, "prompt_tokens")
    output_total = field(raw, "completion_tokens")
    if "cached_tokens" in details:
        cache_read = field(details, "cached_tokens")
    else:
        cache_read = field(raw, "prompt_cache_hit_tokens")
    miss = field(raw, "prompt_cache_miss_tokens")
    reasoning = field(comp, "reasoning_tokens")
    if input_total is None and cache_read is not None and miss is not None:
        input_total = cache_read + miss
    if input_total is not None and cache_read is not None and miss is not None and cache_read + miss != input_total:
        invalid = True
    if cache_read is not None and input_total is not None and cache_read > input_total:
        cache_read, invalid = None, True
    if reasoning is not None and output_total is not None and reasoning > output_total:
        reasoning, invalid = None, True
    estimated = output_total is None and estimated_output is not None
    if estimated:
        output_total = _count(estimated_output)
    source = "estimated" if estimated else "provider" if raw else "missing"
    known = input_total is not None and output_total is not None and not estimated and not invalid
    return {"input_total": input_total, "output_total": output_total, "cache_read": cache_read,
            "reasoning_output": reasoning, "known": known, "source": source, "scope": scope,
            "request_id": request_id, "round_id": round_id, "invalid": invalid, "estimated": estimated,
            "prompt": input_total if input_total is not None else 0,
            "completion": output_total if output_total is not None else 0,
            "cached": cache_read if cache_read is not None else 0,
            "reasoning": reasoning if reasoning is not None else 0}
