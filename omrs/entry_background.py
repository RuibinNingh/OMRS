"""入口锁屏背景的配置、媒体校验与持久化。

入口页在未登录时也会显示当前选中的媒体，因此这里只返回当前活动资源，
并且资源文件名始终由服务端生成，不能由请求直接决定。
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets

from .common import load_config, omrs_data_dir, save_config


MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DEFAULT_BLUR_PX = 0
MIN_BLUR_PX = 0
MAX_BLUR_PX = 32
DEFAULT_STYLE = "gaussian-blur"
DEFAULT_MODE = "black-hole"

# SVG/HTML 不允许作为入口背景，避免把用户上传内容当作同源文档执行。
MEDIA_TYPES = {
    "image/png": ("image", "png"),
    "image/jpeg": ("image", "jpg"),
    "image/webp": ("image", "webp"),
    "image/gif": ("image", "gif"),
    "image/avif": ("image", "avif"),
    "image/bmp": ("image", "bmp"),
    "video/mp4": ("video", "mp4"),
    "video/webm": ("video", "webm"),
    "video/ogg": ("video", "ogv"),
}
ASSET_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def background_dir(vault: str) -> str:
    path = os.path.join(omrs_data_dir(vault), "entry-background")
    os.makedirs(path, exist_ok=True)
    return path


def default_state() -> dict:
    return {"mode": DEFAULT_MODE, "style": DEFAULT_STYLE, "blur_px": DEFAULT_BLUR_PX, "asset": None}


def normalize_state(value) -> dict:
    """Normalize old/malformed config into the public background contract."""
    state = default_state()
    if not isinstance(value, dict):
        return state
    mode = value.get("mode")
    if mode in {DEFAULT_MODE, "custom"}:
        state["mode"] = mode
    style = value.get("style")
    if style == DEFAULT_STYLE:
        state["style"] = style
    try:
        blur = int(value.get("blur_px", DEFAULT_BLUR_PX))
    except (TypeError, ValueError):
        blur = DEFAULT_BLUR_PX
    state["blur_px"] = max(MIN_BLUR_PX, min(MAX_BLUR_PX, blur))
    asset = value.get("asset")
    if isinstance(asset, dict):
        asset_id = str(asset.get("id", ""))
        mime = str(asset.get("mime", "")).lower()
        kind_ext = MEDIA_TYPES.get(mime)
        try:
            size = int(asset.get("bytes", 0))
        except (TypeError, ValueError):
            size = 0
        if ASSET_ID_RE.fullmatch(asset_id) and kind_ext and 0 < size <= MAX_UPLOAD_BYTES:
            state["asset"] = {
                "id": asset_id,
                "kind": kind_ext[0],
                "mime": mime,
                "bytes": size,
            }
    if state["mode"] == "custom" and not state["asset"]:
        # 配置损坏时入口必须仍然可打开，使用黑洞作为安全回退。
        state["mode"] = DEFAULT_MODE
    return state


def load_state(vault: str) -> dict:
    return normalize_state(load_config(vault).get("entry_background"))


def asset_path(vault: str, asset: dict) -> str | None:
    state = normalize_state({"mode": "custom", "asset": asset})
    item = state.get("asset")
    if not item:
        return None
    _, ext = MEDIA_TYPES[item["mime"]]
    path = os.path.join(background_dir(vault), f"{item['id']}.{ext}")
    root = os.path.realpath(background_dir(vault))
    real = os.path.realpath(path)
    if not (real == root or real.startswith(root + os.sep)):
        return None
    return path


def public_state(vault: str) -> dict:
    """Return only the metadata safe to expose to the settings page."""
    state = load_state(vault)
    if state.get("asset"):
        path = asset_path(vault, state["asset"])
        if not path or not _asset_file_matches(path, state["asset"]):
            state["asset"] = None
            if state["mode"] == "custom":
                state["mode"] = DEFAULT_MODE
    return state


def _read_prefix(path: str, size: int = 4096) -> bytes:
    with open(path, "rb") as stream:
        return stream.read(size)


def _detected_mime(prefix: bytes) -> str | None:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix.startswith(b"BM"):
        return "image/bmp"
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp"
    # AVIF 是 ISO-BMFF 容器，品牌位于 ftyp 后；允许常见兼容品牌。
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        brands = {prefix[8:12], prefix[16:20] if len(prefix) >= 20 else b""}
        if brands & {b"avif", b"avis"}:
            return "image/avif"
        if brands & {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"mp4 ", b"M4V ", b"3gp4"}:
            return "video/mp4"
    if prefix.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if prefix.startswith(b"OggS"):
        return "video/ogg"
    return None


def _asset_file_matches(path: str, asset: dict) -> bool:
    try:
        return (os.path.isfile(path)
                and os.path.getsize(path) == int(asset.get("bytes", 0))
                and _detected_mime(_read_prefix(path)) == asset.get("mime"))
    except (OSError, TypeError, ValueError):
        return False


def inspect_upload(path: str, filename: str = "", declared_mime: str = "") -> dict:
    """Validate a temporary upload and return generated metadata.

    The caller owns ``path`` and removes it when validation or persistence fails.
    """
    size = os.path.getsize(path)
    if size <= 0:
        raise ValueError("入口背景文件不能为空")
    if size > MAX_UPLOAD_BYTES:
        raise ValueError("入口背景文件不能超过 200 MB")
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    detected = _detected_mime(_read_prefix(path))
    if detected not in MEDIA_TYPES:
        raise ValueError("不支持的入口背景格式")
    if declared and declared not in {"application/octet-stream", "binary/octet-stream"} and declared != detected:
        raise ValueError("文件类型与内容不一致")
    kind, ext = MEDIA_TYPES[detected]
    asset_id = secrets.token_hex(16)
    return {
        "id": asset_id,
        "kind": kind,
        "mime": detected,
        "bytes": size,
        "ext": ext,
        "sha256": _sha256(path),
        "filename": os.path.basename(filename or f"background.{ext}"),
    }


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _validated_asset(asset_id: str, current: dict, vault: str) -> dict:
    if not ASSET_ID_RE.fullmatch(str(asset_id)):
        raise ValueError("入口背景资源 ID 不合法")
    asset = current.get("asset") if isinstance(current, dict) else None
    if not asset or asset.get("id") != asset_id:
        raise ValueError("入口背景资源不存在")
    path = asset_path(vault, asset)
    if not path or not os.path.isfile(path):
        raise ValueError("入口背景资源文件不存在")
    return dict(asset)


def save_state(vault: str, mode: str, style: str, blur_px, asset_id: str = "", upload: dict | None = None) -> dict:
    """Atomically save selection and optionally install a validated upload."""
    if mode not in {DEFAULT_MODE, "custom"}:
        raise ValueError("入口背景模式不合法")
    if style != DEFAULT_STYLE:
        raise ValueError("入口背景样式不合法")
    try:
        blur = int(blur_px)
    except (TypeError, ValueError):
        raise ValueError("高斯模糊参数必须是整数")
    if blur < MIN_BLUR_PX or blur > MAX_BLUR_PX:
        raise ValueError("高斯模糊参数必须在 0 到 32 之间")
    if upload and mode != "custom":
        raise ValueError("黑洞预设不能同时上传媒体文件")

    old = public_state(vault)
    old_asset = old.get("asset")
    final_asset = None
    final_path = None
    if upload:
        final_asset = {key: upload[key] for key in ("id", "kind", "mime", "bytes")}
        final_path = os.path.join(background_dir(vault), f"{upload['id']}.{upload['ext']}")
        os.replace(upload["path"], final_path)
    elif mode == "custom":
        final_asset = _validated_asset(asset_id, old, vault)

    if mode == "custom" and not final_asset:
        raise ValueError("自定义背景需要先上传媒体")
    state = {"mode": mode, "style": style, "blur_px": blur,
             "asset": final_asset if mode == "custom" else old_asset}
    try:
        save_config(vault, {"entry_background": state})
    except Exception:
        if final_path:
            try:
                os.remove(final_path)
            except OSError:
                pass
        raise

    # 新文件已经成为配置事实后再清理旧文件；切换黑洞不删除旧资源。
    if upload and old_asset and old_asset.get("id") != final_asset.get("id"):
        old_path = asset_path(vault, old_asset)
        if old_path and old_path != final_path:
            try:
                os.remove(old_path)
            except OSError:
                pass
    return public_state(vault)


def media_content(vault: str) -> tuple[str, dict] | None:
    state = public_state(vault)
    if state.get("mode") != "custom" or not state.get("asset"):
        return None
    path = asset_path(vault, state["asset"])
    if not path or not _asset_file_matches(path, state["asset"]):
        return None
    return path, state["asset"]
