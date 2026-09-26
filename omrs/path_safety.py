"""Keep question writes and moves inside the question tree."""

import os

from .common import questions_root


def safe_component(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}不能为空")
    value = value.strip()
    if value in {".", ".."} or any(ch in value for ch in ("/", "\\", "\0")) or os.path.isabs(value):
        raise ValueError(f"{label}不能包含路径或路径分隔符")
    if len(value) >= 2 and value[1] == ":":
        raise ValueError(f"{label}不能是盘符路径")
    return value


def safe_question_path(vault, path):
    root = os.path.realpath(questions_root(vault))
    target = os.path.realpath(path)
    if os.path.commonpath((root, target)) != root:
        raise ValueError("题目文件路径不在错题目录内")
    return path


def safe_question_directory(vault, subject, category):
    subject = safe_component(subject, "科目")
    category = safe_component(category, "分类")
    path = os.path.join(questions_root(vault), subject, category)
    safe_question_path(vault, path)
    return path, subject, category
