"""SQLite 活动配置与 config.json 镜像；调参和投影同事务发布。"""
import hashlib
import json
import math
import os
import time
import uuid

from .ledger import connect, canonical_json, append_commit_in_db
from .locking import write_lock
from .vault_lifecycle import lease, fsync_dir, atomic_json


class ConfigMirrorConflict(RuntimeError):
    status = 409
    code = "config_mirror_conflict"


def _hash(config):
    return hashlib.sha256(canonical_json(config).encode()).hexdigest()


def _file_config(vault):
    from .common import CONFIG_DEFAULTS, config_path
    path = config_path(vault)
    if not os.path.exists(path):
        return dict(CONFIG_DEFAULTS)
    with open(path, encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("配置必须是 JSON 对象")
    return {**CONFIG_DEFAULTS, **raw}


def normalized_tuning(config):
    from .common import DEFAULT_TUNING
    values = config.get("tuning", {})
    if not isinstance(values, dict):
        raise ValueError("tuning 必须是对象")
    merged = dict(DEFAULT_TUNING)
    for key, value in values.items():
        if key not in merged:
            raise ValueError(f"未知算法参数：{key}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"算法参数 {key} 必须是有限数字")
        merged[key] = value
    integers = {"high_score_threshold", "kill_streak", "ef_cold_attempts", "leech_fail_threshold"}
    for key in integers:
        if type(merged[key]) is not int:
            raise ValueError(f"算法参数 {key} 必须是整数")
    for key in ("decay_mastery_factor", "decay_base", "priority_days_divisor", "kill_streak", "leech_fail_threshold"):
        if merged[key] <= 0:
            raise ValueError(f"算法参数 {key} 必须大于零")
    if not 0 <= merged["high_score_threshold"] <= 10 or merged["ef_cold_attempts"] < 0:
        raise ValueError("分数阈值或冷启动次数超出范围")
    for key in ("proficiency_factor", "revive_decay_threshold"):
        if not 0 < merged[key] <= 1:
            raise ValueError(f"算法参数 {key} 必须在 (0,1] 范围")
    if not 0 <= merged["kill_demote_factor"] <= 1 or merged["revive_tier_multiplier"] < 1:
        raise ValueError("降级系数或复燃倍率超出范围")
    for key in merged:
        if merged[key] < 0:
            raise ValueError(f"算法参数 {key} 不能为负")
    return merged


def validate(config):
    try:
        json.dumps(config, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("配置必须为可序列化的 JSON，不能含非有限数字") from exc
    normalized_tuning(config)
    from .common import validate_draft_config
    from .agent.config import validate_agent_config
    validate_draft_config(config)
    validate_agent_config(config)
    for key in ("allow_external", "ai_restrict_tags", "ai_thinking", "train_try_collect", "inbox_auto_on_upload"):
        if key in config and type(config[key]) is not bool:
            raise ValueError(f"{key} 必须是布尔值")
    for key in ("ai_api_key", "ai_model", "ai_model_detect", "ai_model_extract", "ai_model_classify", "train_dir", "inbox_local_detect_url"):
        if key in config and not isinstance(config[key], str):
            raise ValueError(f"{key} 必须是字符串")
    if config.get("inbox_detect_provider", "vlm") not in ("vlm", "local_http"):
        raise ValueError("未知框选提供方")
    for key, minimum in (("inbox_blind_every", 0), ("inbox_discard_keep_days", 1)):
        if key in config and (type(config[key]) is not int or config[key] < minimum):
            raise ValueError(f"{key} 必须是不小于 {minimum} 的整数")
    value = config.get("inbox_auto_ready_conf", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("inbox_auto_ready_conf 必须在 [0,1] 范围")
    if "http_legacy_upload_mib" in config and (type(config["http_legacy_upload_mib"]) is not int or not 2 <= config["http_legacy_upload_mib"] <= 8192):
        raise ValueError("http_legacy_upload_mib 必须是 2 到 8192 的整数")
    if "http_json_mib" in config and (type(config["http_json_mib"]) is not int or not 1 <= config["http_json_mib"] <= 8192):
        raise ValueError("http_json_mib 必须是 1 到 8192 的整数")
    from .security import normalize_lan_cidrs
    normalize_lan_cidrs(config.get("lan_pin_exempt_cidrs", []))


def read(vault):
    with lease(vault), connect(vault) as db:
        row = db.execute("SELECT config_json FROM active_config WHERE id=1").fetchone()
        return json.loads(row[0]) if row else _file_config(vault)


def _write_mirror(vault, config):
    from .common import config_path
    path = config_path(vault)
    temporary = path + "." + uuid.uuid4().hex + ".tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        fsync_dir(os.path.dirname(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _finish_mirror(vault, config, revision):
    with connect(vault) as db:
        # 文件写入与版本复查共享跨进程SQLite写事务，旧发布者不能覆盖新镜像。
        db.execute("BEGIN IMMEDIATE")
        active = db.execute("SELECT * FROM active_config WHERE id=1").fetchone()
        if active is None:
            raise RuntimeError("活动配置不存在，不能发布镜像")
        superseded = active["revision"] != revision
        config, revision = json.loads(active["config_json"]), active["revision"]
        result = {"revision": revision, "mirror_pending": bool(active["mirror_pending"])}
        if superseded:
            result["superseded"] = True
        from .common import config_path
        path = config_path(vault)
        if not active["mirror_pending"] and os.path.exists(path):
            return result
        db.execute("UPDATE active_config SET mirror_pending=1 WHERE id=1")
        try:
            conflict = False
            if os.path.exists(path):
                try:
                    conflict = _hash(_file_config(vault)) not in (
                        active["mirror_hash"], active["previous_mirror_hash"])
                except (ValueError, UnicodeError):
                    # 发布后手改成非法JSON仍是镜像冲突，不能误报数据库未提交。
                    conflict = True
            if conflict:
                atomic_json(path + ".active-conflict.json", config)
                return {**result, "mirror_pending": True, "mirror_conflict": True}
            _write_mirror(vault, config)
        except OSError:
            return {**result, "mirror_pending": True}
        db.execute("UPDATE active_config SET mirror_pending=0,previous_mirror_hash='' WHERE id=1 AND revision=?", (revision,))
        return {**result, "mirror_pending": False}


def public_status(vault):
    """设置页只读发布版本与重算回执，不返回秘密配置。"""
    return _public_state(vault)


def public_config(vault):
    """配置字段、版本和回执同一快照读取；秘密只返回是否已配置。"""
    return _public_state(vault, include_config=True)


def _public_state(vault, include_config=False):
    from .projection_runtime import policy_hash
    with lease(vault), connect(vault) as db:
        db.execute("BEGIN")
        active = db.execute("SELECT * FROM active_config WHERE id=1").fetchone()
        config = json.loads(active["config_json"]) if active else _file_config(vault)
        effective = normalized_tuning(config)
        saved = db.execute("SELECT value FROM storage_meta WHERE key='config.recalculation'").fetchone()
        summary = json.loads(saved[0]) if saved else {"status": "not_recorded"}
        status = {"revision": active["revision"] if active else 0,
                "mirror_pending": bool(active["mirror_pending"]) if active else False,
                "tuning_effective": effective, "policy_hash": policy_hash(effective),
                "recalculation": summary}
        if not include_config:
            return status
        for name in ("ai_api_key", "agent_api_key"):
            config[name + "_configured"] = bool(config.pop(name, None))
        config.pop("pin_hash", None)
        config.pop("salt", None)
        return {**config, **status}


def _publication_status(vault, mirror):
    current = public_status(vault)
    if current["revision"] == mirror["revision"]:
        for key in ("superseded", "mirror_conflict"):
            if key in mirror:
                current[key] = mirror[key]
    else:
        current["superseded"] = True
    return current


def save(vault, patch, replace=False):
    from .common import CONFIG_DEFAULTS
    from .projection_runtime import full_project, _publish_meta, _snapshot, policy_hash, invalidate
    if not isinstance(patch, dict):
        raise ValueError("配置必须是 JSON 对象")
    with lease(vault), write_lock():
        with connect(vault) as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT * FROM active_config WHERE id=1").fetchone()
            previous = json.loads(active["config_json"]) if active else _file_config(vault)
            candidate = {**CONFIG_DEFAULTS, **patch} if replace else {**previous, **patch}
            validate(candidate)
            tuning, old_tuning = normalized_tuning(candidate), normalized_tuning(previous)
            revision = active["revision"] if active else 0
            if active and candidate == previous:
                db.commit()
                mirror = _finish_mirror(vault, candidate, revision) if active["mirror_pending"] else {"revision": revision, "mirror_pending": False}
                return _publication_status(vault, mirror)
            revision += 1
            old_mirror = _hash(_file_config(vault))
            changed_keys = sorted(k for k in candidate if candidate.get(k) != previous.get(k))
            tuning_changed = tuning != old_tuning
            state = None
            if not active or tuning_changed:
                started = time.perf_counter()
                state = full_project(vault, db, tuning)
                from .ledger import PROJECTOR_VERSION
                summary = {"status": "complete", "revision": revision,
                    "questions": db.execute("SELECT COUNT(*) FROM question_projection").fetchone()[0],
                    "feedbacks": db.execute("SELECT COUNT(*) FROM history_projection").fetchone()[0],
                    "seconds": round(time.perf_counter() - started, 6),
                    "policy_hash": policy_hash(tuning), "projection_version": PROJECTOR_VERSION}
                db.execute("INSERT OR REPLACE INTO storage_meta(key,value) VALUES('config.recalculation',?)",
                           (canonical_json(summary),))
                if db.execute("SELECT 1 FROM commits LIMIT 1").fetchone():
                    info = append_commit_in_db(db, "api", "config.tuning_update", "更新算法参数并重算历史", {
                        "config_revision": revision, "tuning": tuning, "changed_keys": changed_keys,
                        "recalculation": summary})
                    state["last_seq"] = info["seq"]
                _publish_meta(db, state, policy_hash(tuning))
                db.execute("DELETE FROM snapshots")
                _snapshot(db, state, policy_hash(tuning))
            elif db.execute("SELECT 1 FROM commits LIMIT 1").fetchone():
                # 配置值可能含密钥；Ledger 只记录键名及发布版本。
                info = append_commit_in_db(db, "api", "config.update", "更新运行配置", {
                    "config_revision": revision, "changed_keys": changed_keys})
            db.execute("INSERT OR REPLACE INTO active_config VALUES(1,?,?,?,?,?)", (revision, canonical_json(candidate), _hash(candidate), 1, old_mirror))
        if state is not None:
            invalidate(vault)
        mirror = _finish_mirror(vault, candidate, revision)
        return _publication_status(vault, mirror)


def initialize(vault):
    """监听前调用：先恢复未完成镜像，再导入正常手改配置。"""
    with lease(vault), write_lock():
        with connect(vault) as db:
            active = db.execute("SELECT * FROM active_config WHERE id=1").fetchone()
        if not active:
            return save(vault, _file_config(vault), replace=True)
        current = json.loads(active["config_json"])
        from .common import config_path
        if not os.path.exists(config_path(vault)):
            result = _finish_mirror(vault, current, active["revision"])
            if result["mirror_pending"]:
                raise RuntimeError("配置镜像无法恢复，尚未启动服务")
            return result
        if active["mirror_pending"]:
            result = _finish_mirror(vault, current, active["revision"])
            if result.get("mirror_conflict"):
                raise ConfigMirrorConflict("配置手改与待同步镜像冲突；已保留文件和活动配置，请核对后再启动")
            if result["mirror_pending"]:
                raise RuntimeError("配置镜像无法恢复，尚未启动服务")
            return result
        actual = _hash(_file_config(vault))
        if actual != active["mirror_hash"]:
            return save(vault, _file_config(vault), replace=True)
        return {"revision": active["revision"], "mirror_pending": False}
