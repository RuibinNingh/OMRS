"""厂商兼容配置：只收与常用厂商有关的几项开关，写成数据（内置配置 + 用户覆写）。"""

DEFAULTS = {
    "reasoning_fields": ["reasoning_content", "reasoning", "reasoning_text"],  # 从哪些增量字段读思考内容
    "send_reasoning_back": False,     # 带工具调用的 assistant 消息是否回传思考内容
    "tool_result_name": False,        # 工具结果消息是否必须带 name
    "max_tokens_field": "max_tokens",  # max_tokens 或 max_completion_tokens
    "system_role": "system",          # system 或 developer
    "stream_usage": True,             # 是否发送 stream_options.include_usage
    "strict_tools": False,            # 工具 schema 是否带 strict
    "context_window": 65536,          # 上下文窗口（tokens），只用于界面上的用量计
}

PROFILES = {
    "openai": {"max_tokens_field": "max_completion_tokens", "context_window": 128000},
    "dashscope": {"reasoning_fields": ["reasoning_content"], "context_window": 131072},
    "deepseek": {"reasoning_fields": ["reasoning_content"], "send_reasoning_back": True, "context_window": 65536},
    "custom": {},
}


def resolve_compat(name: str, overrides=None) -> dict:
    name = name if name in PROFILES else "custom"
    merged = {**DEFAULTS, **PROFILES[name], "name": name}
    for key, value in (overrides or {}).items():
        if key in DEFAULTS and type(value) is type(DEFAULTS[key]):
            merged[key] = value
    return merged
