"""题库分类目录与锚点的唯一创建入口。"""
from .vault_lifecycle import storage, open_sqlite
import os
import re
import tempfile

from . import locking
from .common import questions_root
from .path_safety import safe_question_directory, safe_question_path


@storage
def category_path(vault, subject, category):
    """统一名称：折叠空白并拒绝 Markdown/文件系统控制字符和保留目录。"""
    for value in (subject, category):
        if isinstance(value, str) and re.search(r"[\x00-\x1f]", value):
            raise ValueError("分类名称包含控制字符")
    names = [" ".join(value.split()) if isinstance(value, str) else value for value in (subject, category)]
    for value in names:
        if isinstance(value, str) and (value == ".omrs" or re.search(r'[\[\]<>:"?*|\x00-\x1f]', value)):
            raise ValueError("分类名称包含保留字或非法符号")
    return safe_question_directory(vault, *names)


@storage
def create_category(vault, subject, category):
    """创建零题分类；重复调用不改已有锚点，失败不报告成功。"""
    with locking.write_lock():
        directory, subject, category = category_path(vault, subject, category)
        subject_dir = os.path.dirname(directory)
        subject_anchor = safe_question_path(vault, os.path.join(subject_dir, f"{subject}.md"))
        category_anchor = safe_question_path(vault, os.path.join(directory, f"{category}.md"))
        # 所有目标先预检。现有符号链接即使仍在题库内也不能充当锚点。
        for path in (subject_dir, directory, subject_anchor, category_anchor):
            if os.path.islink(path):
                raise ValueError("分类路径不能使用符号链接")
        for path in (subject_anchor, category_anchor):
            if os.path.exists(path) and not os.path.isfile(path):
                raise ValueError("分类锚点不是普通文件")
        created = not os.path.exists(category_anchor)
        subject_created = not os.path.exists(subject_anchor)
        os.makedirs(directory, exist_ok=True)
        content = None
        linked = False
        index_updated = False
        try:
            if subject_created:
                _create_once(subject_anchor, f"# {subject}\n")
            link = f"[[{category}]]"
            with open(subject_anchor, "r", encoding="utf-8") as file:
                content = file.read()
            linked = link not in content
            if linked:
                _replace(subject_anchor, content.rstrip() + f"\n- {link}\n")
                index_updated = True
            # 完整内容先写临时文件，再原子建锚点；最后一步失败不会留下被词表读取的半文件。
            if created:
                _create_once(category_anchor, f"# {category}\n")
        except Exception as error:
            try:
                if subject_created and os.path.isfile(subject_anchor):
                    os.unlink(subject_anchor)
                elif index_updated and content is not None:
                    _replace(subject_anchor, content)
                if os.path.isdir(directory) and not os.listdir(directory):
                    os.rmdir(directory)
                if os.path.isdir(subject_dir) and not os.listdir(subject_dir):
                    os.rmdir(subject_dir)
            except OSError as rollback_error:
                raise RuntimeError(f"分类创建失败且回滚不完整：{rollback_error}") from error
            raise
        return {"subject": subject, "category": category, "created": created,
                "wrote": created or subject_created or linked}


def _create_once(path, content):
    fd, temp = tempfile.mkstemp(prefix=".taxonomy-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
        try:
            os.link(temp, path)
        except FileExistsError:
            return False
        return True
    finally:
        if os.path.exists(temp):
            try:
                os.unlink(temp)
            except OSError:
                pass


def _replace(path, content):
    fd, temp = tempfile.mkstemp(prefix=".taxonomy-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@storage
def directory_categories(vault):
    """只读取题库内有锚点的分类，不跟随符号链接。"""
    root = questions_root(vault)
    found = {}
    if not os.path.isdir(root):
        return found
    for subject in os.scandir(root):
        if subject.name == ".omrs":
            continue
        if not subject.is_dir(follow_symlinks=False):
            continue
        try:
            category_path(vault, subject.name, "占位")
        except ValueError:
            continue
        for category in os.scandir(subject.path):
            if not category.is_dir(follow_symlinks=False):
                continue
            try:
                path, _, _ = category_path(vault, subject.name, category.name)
            except ValueError:
                continue
            anchor = os.path.join(path, f"{category.name}.md")
            if os.path.isfile(anchor) and not os.path.islink(anchor):
                found.setdefault(subject.name, set()).add(category.name)
    return found
