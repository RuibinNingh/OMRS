from .vault_lifecycle import storage, open_sqlite, lease, task, generation
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .common import ATTACHMENTS_DIR, OMRS_DIR, omrs_data_dir, questions_root


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_SCANS = {}
_JOBS = {}
_BACKUP_TOKENS = {}
_LOCK = threading.Lock()


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _sum_size(paths):
    total = 0
    for path in paths:
        try:
            total += os.path.getsize(path)
        except OSError:
            pass
    return total


def _is_inside(path, root):
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    try:
        return os.path.commonpath([root_abs, path_abs]) == root_abs
    except ValueError:
        return False


def _walk_files(root):
    if not os.path.isdir(root):
        return []
    result = []
    for current, _, files in os.walk(root):
        for name in files:
            result.append(os.path.join(current, name))
    return result


def _active_omrs_files(vault):
    data_dir = omrs_data_dir(vault)
    files = []
    excluded = (os.sep + "legacy_backup" + os.sep, os.sep + "backups" + os.sep)
    for path in _walk_files(data_dir):
        normalized = os.path.abspath(path)
        if any(part in normalized for part in excluded):
            continue
        if os.path.splitext(path)[1].lower() == ".zip":
            continue
        files.append(path)
    return files


def _question_non_image_files(vault):
    root = questions_root(vault)
    data_dir = os.path.join(root, OMRS_DIR)
    attachment_dir = os.path.join(root, ATTACHMENTS_DIR)
    files = []
    for path in _walk_files(root):
        if _is_inside(path, data_dir) or _is_inside(path, attachment_dir):
            continue
        files.append(path)
    return files


def _attachment_files(vault):
    return _walk_files(os.path.join(questions_root(vault), ATTACHMENTS_DIR))


def _image_files(vault):
    return [
        path for path in _attachment_files(vault)
        if os.path.splitext(path)[1].lower() in IMAGE_EXTS
    ]


@storage
def _append_audit(vault, action, detail):
    record = {"time": _now(), "action": action, **detail}
    path = os.path.join(omrs_data_dir(vault), "optimization_log.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def dependency_status():
    status = {
        "pillow": {"available": False, "version": "", "error": ""},
        "jpegtran": {"available": False, "path": ""},
    }
    try:
        from PIL import Image  # noqa: F401
        status["pillow"] = {
            "available": True,
            "version": getattr(Image, "__version__", ""),
            "error": "",
        }
    except Exception as exc:
        status["pillow"]["error"] = str(exc)
    jpegtran = shutil.which("jpegtran")
    if jpegtran:
        status["jpegtran"] = {"available": True, "path": jpegtran}
    return status


def ensure_image_dependencies_interactive():
    status = dependency_status()
    if status["pillow"]["available"]:
        return status
    if os.name != "nt":
        return status
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        should_install = messagebox.askyesno(
            "OMRS 图片优化依赖缺失",
            "图片优化需要 Pillow。是否现在自动执行 python -m pip install --upgrade Pillow？\n\n"
            "选择“否”也会继续启动，但图片优化功能不可用。",
        )
        if should_install:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"])
                status = dependency_status()
                if status["pillow"]["available"]:
                    messagebox.showinfo("OMRS 图片优化", "Pillow 已安装，图片优化功能可用。")
                else:
                    messagebox.showwarning("OMRS 图片优化", "安装完成但仍无法导入 Pillow，图片优化功能可能不可用。")
            except Exception as exc:
                messagebox.showerror(
                    "OMRS 图片优化不可用",
                    f"自动安装 Pillow 失败：{exc}\n\n服务会继续启动，但图片优化功能不可用。",
                )
        else:
            messagebox.showwarning("OMRS 图片优化不可用", "服务会继续启动，但图片优化功能不可用。")
        root.destroy()
    except Exception:
        pass
    return status


def _public_job(job):
    if not job:
        return None
    public = dict(job)
    result = public.get("result")
    if isinstance(result, dict):
        public["result"] = {
            key: value for key, value in result.items()
            if key not in ("candidates", "files_full")
        }
    return public


@storage
def storage_summary(vault):
    data_files = _active_omrs_files(vault)
    question_files = _question_non_image_files(vault)
    attachment_files = _attachment_files(vault)
    images = [path for path in attachment_files if os.path.splitext(path)[1].lower() in IMAGE_EXTS]
    non_images = [path for path in attachment_files if os.path.splitext(path)[1].lower() not in IMAGE_EXTS]
    with _LOCK:
        active_job = _public_job(next((job for job in _JOBS.values() if job.get("status") in ("queued", "running")), None))
        last_job = _public_job(next(reversed(_JOBS.values()), None) if _JOBS else None)
    return {
        "status": "ok",
        "dependencies": dependency_status(),
        "sizes": {
            "data_chain": {"bytes": _sum_size(data_files), "files": len(data_files)},
            "question_files": {"bytes": _sum_size(question_files), "files": len(question_files)},
            "question_images": {"bytes": _sum_size(attachment_files), "files": len(attachment_files)},
        },
        "images": {
            "count": len(images),
            "bytes": _sum_size(images),
            "other_attachment_files": len(non_images),
        },
        "active_job": active_job,
        "last_job": last_job,
    }


def _png_optimized_copy(src, tmp_path):
    from PIL import Image, ImageChops

    with Image.open(src) as img:
        img.load()
        original = img.copy()
        original_mode = img.mode
        original_size = img.size
        img.save(tmp_path, format="PNG", optimize=True, compress_level=9)
    with Image.open(tmp_path) as optimized:
        optimized.load()
        if optimized.size != original_size or optimized.mode != original_mode:
            raise ValueError("PNG 优化后尺寸或模式变化")
        diff = ImageChops.difference(original, optimized)
        if diff.getbbox() is not None:
            raise ValueError("PNG 优化后像素变化")


def _jpeg_optimized_copy(src, tmp_path):
    jpegtran = shutil.which("jpegtran")
    if not jpegtran:
        raise ValueError("当前环境不支持无损 JPG 压缩（缺少 jpegtran）")
    subprocess.check_call(
        [jpegtran, "-copy", "all", "-optimize", "-outfile", tmp_path, src],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _candidate_for_file(path, root):
    ext = os.path.splitext(path)[1].lower()
    old_size = os.path.getsize(path)
    fd, tmp = tempfile.mkstemp(suffix=ext or ".img")
    os.close(fd)
    try:
        if ext == ".png":
            if not dependency_status()["pillow"]["available"]:
                return None, "缺少 Pillow，无法无损优化 PNG"
            _png_optimized_copy(path, tmp)
        elif ext in (".jpg", ".jpeg"):
            _jpeg_optimized_copy(path, tmp)
        else:
            return None, f"暂不支持 {ext or '未知格式'} 的无损压缩"
        new_size = os.path.getsize(tmp)
        if new_size >= old_size:
            return None, "已是较优体积"
        return {
            "path": path,
            "rel_path": _rel(path, root),
            "old_size": old_size,
            "new_size": new_size,
            "saving": old_size - new_size,
            "type": ext.lstrip("."),
        }, None
    except Exception as exc:
        return None, str(exc)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@storage
def scan_compression(vault):
    root = questions_root(vault)
    files = _image_files(vault)
    job_id = "scanjob-" + uuid.uuid4().hex[:12]
    job = {
        "status": "queued",
        "kind": "scan",
        "job_id": job_id,
        "created_at": _now(),
        "total": len(files),
        "processed": 0,
        "current_file": "",
        "done": False,
        "result": None,
        "errors": [],
    }
    with _LOCK:
        _JOBS[job_id] = job
    thread = threading.Thread(target=_run_quick_scan_job, args=(vault, job_id, files, generation(vault)), daemon=True)
    thread.start()
    return {"status": "ok", "job": job}


def _run_quick_scan_job(vault, job_id, files, expected_generation=None):
    with task(vault, expected_generation):
        return _run_quick_scan_job_current(vault, job_id, files)


def _run_quick_scan_job_current(vault, job_id, files):
    root = questions_root(vault)
    started = time.time()
    deps = dependency_status()
    potential = []
    skipped = {}
    ext_counts = {}
    image_bytes = 0
    _set_job(job_id, status="running", started_at=_now())
    for path in files:
        index = len(potential) + sum(skipped.values()) + 1
        rel_path = _rel(path, root)
        _set_job(job_id, current_file=rel_path, processed=index - 1)
        ext = os.path.splitext(path)[1].lower()
        ext_counts[ext or "unknown"] = ext_counts.get(ext or "unknown", 0) + 1
        try:
            old_size = os.path.getsize(path)
        except OSError:
            skipped["文件无法读取"] = skipped.get("文件无法读取", 0) + 1
            _set_job(job_id, processed=index)
            continue
        image_bytes += old_size
        reason = None
        if ext == ".png":
            if not deps["pillow"]["available"]:
                reason = "缺少 Pillow，无法无损优化 PNG"
        elif ext in (".jpg", ".jpeg"):
            if not deps["jpegtran"]["available"]:
                reason = "缺少 jpegtran，无法无损优化 JPG"
        else:
            reason = f"暂不支持 {ext or '未知格式'} 的无损压缩"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
        else:
            potential.append({
                "path": path,
                "rel_path": rel_path,
                "old_size": old_size,
                "type": ext.lstrip("."),
            })
        _set_job(job_id, processed=index)
    scan_id = "scan-" + uuid.uuid4().hex[:12]
    result = {
        "status": "ok",
        "exact": False,
        "scan_id": scan_id,
        "created_at": _now(),
        "duration_seconds": round(time.time() - started, 2),
        "scanned_files": len(files),
        "candidate_count": len(potential),
        "potential_count": len(potential),
        "potential_bytes": sum(item["old_size"] for item in potential),
        "compressible_bytes": None,
        "original_bytes": image_bytes,
        "candidates": potential[:200],
        "skipped": skipped,
        "ext_counts": ext_counts,
        "errors": [],
    }
    with lease(vault), _LOCK:
        _SCANS[scan_id] = {**result, "files_full": potential, "expires_at": time.time() + 3600}
    _set_job(job_id, status="completed", done=True, completed_at=_now(), current_file="", result=result)
    _append_audit(vault, "quick_scan", {
        "scan_id": scan_id,
        "scanned_files": len(files),
        "potential_count": len(potential),
        "potential_bytes": result["potential_bytes"],
        "skipped": skipped,
    })


def create_backup_export(vault):
    from .backup_store import create_backup
    path, filename, token, frozen = create_backup(vault)
    size = os.path.getsize(path)
    with _LOCK:
        _BACKUP_TOKENS[token] = {"created_at": time.time(), "filename": filename, "bytes": size,
                                 "frozen_seconds": frozen, "vault": os.path.realpath(vault)}
    _append_audit(vault, "backup.export", {"filename": filename, "bytes": size,
                                           "frozen_seconds": frozen, "token": token[-8:]})
    return path, filename, token


def prepare_backup_import(vault, payload, filename="backup.zip"):
    from .backup_store import prepare_import
    return prepare_import(vault, payload, filename)


def restore_backup(vault, restore_id, confirm=False):
    from .backup_store import restore
    return restore(vault, restore_id, confirm)


def _valid_backup_token(token):
    with _LOCK:
        data = _BACKUP_TOKENS.get(token)
    return bool(data and time.time() - data["created_at"] < 4 * 3600)


@storage
def start_compression(vault, scan_id, backup_token, confirm=False):
    if not confirm:
        raise ValueError("压缩图片需要 confirm=true")
    # 备份不再强制：用户可在「服务设置」自行导出备份，但压缩不依赖有效令牌。
    # backup_token 仍接受（API 形状不变），仅用于审计，不作为前置条件。
    with _LOCK:
        if any(job.get("status") in ("queued", "running") for job in _JOBS.values()):
            raise ValueError("已有压缩任务正在运行")
        scan = _SCANS.get(scan_id)
    if not scan:
        raise ValueError("scan_id 不存在或已过期，请重新扫描")
    files = scan.get("files_full") or []
    if not files:
        raise ValueError("没有可进入深扫压缩的图片")
    job_id = "job-" + uuid.uuid4().hex[:12]
    job = {
        "status": "queued",
        "job_id": job_id,
        "scan_id": scan_id,
        "created_at": _now(),
        "total": len(files),
        "processed": 0,
        "candidate_count": 0,
        "saved_bytes": 0,
        "checked_bytes": 0,
        "phase": "deep_scan_compress",
        "current_file": "",
        "errors": [],
        "done": False,
    }
    with _LOCK:
        _JOBS[job_id] = job
    thread = threading.Thread(target=_run_compression_job, args=(vault, job_id, files, generation(vault)), daemon=True)
    thread.start()
    return {"status": "ok", "job": job}


def _compress_one(vault, path, ext):
    # 复制只占短租约；压缩计算在题库外进行，旧任务不能在恢复后写新目录。
    from .locking import write_lock
    directory = tempfile.mkdtemp(prefix="omrs-image-opt-")
    try:
        source, result = os.path.join(directory, "source" + ext), os.path.join(directory, "result" + ext)
        with lease(vault):
            shutil.copyfile(path, source)
            before = hashlib.sha256(open_bytes(source)).hexdigest()
            old_size = os.path.getsize(source)
        if ext == ".png":
            _png_optimized_copy(source, result)
        elif ext in (".jpg", ".jpeg"):
            _jpeg_optimized_copy(source, result)
        else:
            raise ValueError(f"暂不支持 {ext} 的无损压缩")
        new_size = os.path.getsize(result)
        if new_size >= old_size:
            return old_size, new_size, False
        with lease(vault), write_lock():
            if hashlib.sha256(open_bytes(path)).hexdigest() != before:
                raise ValueError("压缩期间图片已变化，未覆盖")
            temporary = path + "." + uuid.uuid4().hex + ".omrs-opt.tmp"
            try:
                shutil.copyfile(result, temporary)
                with open(temporary, "rb") as file:
                    os.fsync(file.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return old_size, new_size, True
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def open_bytes(path):
    with open(path, "rb") as file:
        return file.read()


def _set_job(job_id, **updates):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(updates)


def _run_compression_job(vault, job_id, files, expected_generation=None):
    with task(vault, expected_generation):
        return _run_compression_job_current(vault, job_id, files)


def _run_compression_job_current(vault, job_id, files):
    _set_job(job_id, status="running", started_at=_now())
    root = questions_root(vault)
    saved_total = 0
    checked_bytes = 0
    candidate_count = 0
    skipped = {}
    errors = []
    for index, item in enumerate(files, 1):
        rel_path = item["rel_path"]
        path = os.path.abspath(item["path"])
        _set_job(job_id, current_file=rel_path, processed=index - 1)
        if not _is_inside(path, root) or not os.path.isfile(path):
            errors.append(f"{rel_path}: 文件不存在或路径越界")
            _set_job(job_id, processed=index, errors=errors[-20:])
            continue
        ext = os.path.splitext(path)[1].lower()
        try:
            old_size, new_size, replaced = _compress_one(vault, path, ext)
            checked_bytes += old_size
            if replaced:
                candidate_count += 1
                saved_total += old_size - new_size
            else:
                skipped["已是较优体积"] = skipped.get("已是较优体积", 0) + 1
        except Exception as exc:
            errors.append(f"{rel_path}: {exc}")
        _set_job(
            job_id,
            processed=index,
            candidate_count=candidate_count,
            saved_bytes=saved_total,
            checked_bytes=checked_bytes,
            skipped=skipped,
            errors=errors[-20:],
        )
    status = "completed_with_errors" if errors else "completed"
    _set_job(
        job_id,
        status=status,
        done=True,
        completed_at=_now(),
        current_file="",
        processed=len(files),
        candidate_count=candidate_count,
        saved_bytes=saved_total,
        checked_bytes=checked_bytes,
        skipped=skipped,
        errors=errors[-50:],
    )
    _append_audit(vault, "compress", {
        "job_id": job_id,
        "files": len(files),
        "candidate_count": candidate_count,
        "saved_bytes": saved_total,
        "skipped": skipped,
        "errors": errors[:20],
    })


def get_job(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        return dict(job)
