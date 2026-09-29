"""助手配置：agent_* 键；地址与密钥留空回退 ai_*，模型不回退。密钥不回显（server.py 的 GET /api/config）。"""
import os

from ..common import load_config, omrs_data_dir
from ..llm.compat import PROFILES, resolve_compat
from ..llm.faux import FauxClient, faux_script_path
from ..llm.openai_compat import OpenAICompatClient

LIMIT_DEFAULTS = {"rounds": 25, "calls": 40, "writes": 20, "concurrent": 1}
MSG_CAP = 60
CONFIRM_TTL_SECONDS = 600
RESULT_CHAR_CAP = 6000


def limits(cfg=None):
    """预算只能在配置里调小，不能调大。"""
    cfg = cfg if cfg is not None else load_config_safe()
    user = cfg.get("agent_limits") if isinstance(cfg.get("agent_limits"), dict) else {}
    out = dict(LIMIT_DEFAULTS)
    for key, default in LIMIT_DEFAULTS.items():
        try:
            value = int(user.get(key, default))
        except (TypeError, ValueError):
            continue
        out[key] = max(1, min(default, value))
    return out


def load_config_safe(vault=None):
    return load_config(vault) if vault else {}


def settings(vault):
    cfg = load_config(vault)
    faux = faux_script_path()
    compat_name = str(cfg.get("agent_compat") or "custom")
    compat = resolve_compat(compat_name, cfg.get("agent_compat_overrides") if isinstance(
        cfg.get("agent_compat_overrides"), dict) else None)
    base = str(cfg.get("agent_base_url") or "").strip() or str(cfg.get("ai_base_url") or "").strip()
    key = str(cfg.get("agent_api_key") or "").strip() or str(cfg.get("ai_api_key") or "").strip()
    model = "faux" if faux else str(cfg.get("agent_model") or "").strip()
    missing = [] if faux else [n for n, v in (("API 地址", base), ("API Key", key), ("模型", model)) if not v]
    return {
        "enabled": bool(cfg.get("agent_enabled")),
        "configured": not missing,
        "missing": missing,
        "faux": bool(faux),
        "model": model,
        "base_host": _host(base) if not faux else "本地假模型",
        "compat": compat,
        "vision": bool(cfg.get("agent_vision")),
        "draft_mode": cfg.get("draft_mode") if cfg.get("draft_mode") in ("silent", "confirm") else "silent",
        "draft_crop_mode": cfg.get("draft_crop_mode") if cfg.get("draft_crop_mode") in ("ask", "auto", "manual") else "ask",
        "draft_force_crop": bool(cfg.get("draft_force_crop")),
        "limits": limits(cfg),
        "debug_log": bool(cfg.get("agent_debug_log")),
        "_base": base,
        "_key": key,
    }


def _host(url):
    from urllib.parse import urlsplit
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def make_client(vault, s=None):
    s = s or settings(vault)
    if s["faux"]:
        return FauxClient(faux_script_path())
    debug = os.path.join(omrs_data_dir(vault), "logs", "agent-llm.jsonl") if s["debug_log"] else None
    return OpenAICompatClient(s["_base"], s["_key"], s["model"], s["compat"], timeout=120, debug_path=debug)


def validate_agent_config(data: dict):
    """POST /api/config 里的 agent_* 校验。faux 只能由进程环境变量开启，配置接口拒绝。"""
    compat = data.get("agent_compat")
    if compat is not None and compat not in PROFILES:
        raise ValueError("agent_compat 只能是 " + "、".join(PROFILES))
    if str(data.get("agent_model") or "").strip().lower() == "faux":
        raise ValueError("假模型只能由进程环境变量开启")
    if "agent_limits" in data and not isinstance(data["agent_limits"], dict):
        raise ValueError("agent_limits 必须是对象")
    if "draft_mode" in data and data["draft_mode"] not in ("silent", "confirm"):
        raise ValueError("draft_mode 只能是 silent 或 confirm")
    for key in ("agent_enabled", "agent_vision", "agent_debug_log"):
        if key in data and not isinstance(data[key], bool):
            raise ValueError(f"{key} 必须为布尔值")
