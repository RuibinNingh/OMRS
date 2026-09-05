"""AI 自动识别（OpenAI 兼容协议）。

仅依赖标准库（urllib + json + re），与项目「无第三方依赖」约定一致。

两种用途（mode）：
- classify：读题目图片，返回【科目 / 分类 / 难度】，用于自动填充表单（不抄题、不解题）。
- answer  ：读答案图片，把答案/解析提取为纯文本。

协议遵循 OpenAI 兼容的 `POST {base}/chat/completions`：
- 消息只用 user 角色，指令 + 图片都放在 user 的 content 里
  （Qwen-VL 等模型推荐不设 System Message，见阿里云百炼文档）。
- 图片以 data URL 通过 `{"type":"image_url","image_url":{"url": ...}}` 传入。

配置读取自 错题/.omrs/config.json（见 common.load_config）：
- ai_base_url  形如 https://api.openai.com/v1 或
              https://dashscope.aliyuncs.com/compatible-mode/v1（末尾可带或不带 /）
- ai_api_key   Bearer 密钥
- ai_model     形如 gpt-4o、qwen-vl-max（需支持图片输入）
"""

import json
import re
import urllib.error
import urllib.request

from .common import MASTERY_HEADERS, load_config, load_csv, mastery_path


def collect_taxonomy(vault: str) -> dict:
    """从 mastery_data.csv 汇总当前的科目/分类/知识点（去重、排序）。"""
    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    subjects, categories, ktags = set(), set(), set()
    categories_by_subject = {}
    for row in rows:
        subject = (row.get("Subject") or "").strip()
        if subject:
            subjects.add(subject)
        category = (row.get("Category") or "").strip()
        if category:
            categories.add(category)
        if subject and category:
            categories_by_subject.setdefault(subject, set()).add(category)
        for tag in (row.get("Knowledge_Tags") or "").split("|"):
            tag = tag.strip()
            if tag:
                ktags.add(tag)
    return {
        "subjects": sorted(subjects),
        "categories": sorted(categories),
        "categories_by_subject": {
            subject: sorted(cats)
            for subject, cats in sorted(categories_by_subject.items())
        },
        "knowledge_tags": sorted(ktags),
    }


def _format_category_tree(taxonomy: dict) -> str:
    """把分类按科目分组展示给模型，避免把不同学科的同名/近义分类混用。"""
    grouped = taxonomy.get("categories_by_subject") or {}
    if not grouped:
        return "（暂无，可自行命名）"
    lines = []
    for subject in taxonomy.get("subjects") or sorted(grouped):
        cats = grouped.get(subject) or []
        if cats:
            lines.append(f"- {subject}: " + "、".join(cats))
    return "\n".join(lines) or "（暂无，可自行命名）"


def _categories_for_subject(taxonomy: dict, subject: str) -> set:
    grouped = taxonomy.get("categories_by_subject") or {}
    return set(grouped.get((subject or "").strip(), []))


def _normalize_subject_category(parsed: dict, taxonomy: dict,
                                hint_subject: str = "",
                                hint_category: str = "") -> tuple:
    """应用用户 hint，并拒绝“已有分类跨科目误用”。"""
    subject = (hint_subject or parsed.get("subject") or "").strip()
    category = (hint_category or parsed.get("category") or "").strip()
    if hint_category:
        return subject, category

    all_categories = set(taxonomy.get("categories") or [])
    subject_categories = _categories_for_subject(taxonomy, subject)
    grouped = taxonomy.get("categories_by_subject") or {}
    category_subjects = {
        item_subject for item_subject, cats in grouped.items() if category in cats
    }
    if category in all_categories and category_subjects and subject not in category_subjects:
        category = ""
    return subject, category


def _ai_config(vault: str, purpose: str = ""):
    """purpose: '' | 'detect' | 'extract' | 'classify'。按用途读 ai_model_<purpose>，缺省回退 ai_model。"""
    cfg = load_config(vault)
    base = (cfg.get("ai_base_url") or "").strip().rstrip("/")
    key = (cfg.get("ai_api_key") or "").strip()
    model = ""
    if purpose:
        model = (cfg.get(f"ai_model_{purpose}") or "").strip()
    model = model or (cfg.get("ai_model") or "").strip()
    return base, key, model


def _endpoint(base: str) -> str:
    """根据用户填写的基础地址拼出 chat/completions 端点。

    兼容三种写法：
    - https://api.openai.com/v1                  → 追加 /chat/completions
    - https://api.openai.com/v1/chat/completions → 原样使用
    - https://host/v1/                            → rstrip 后追加
    """
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _clamp_difficulty(value, fallback=5) -> int:
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(1, min(10, num))


def _as_str_list(value) -> list:
    """把模型返回的知识点（数组或分隔字符串）归一化为去重、去 [[]] 的字符串列表。"""
    if isinstance(value, str):
        value = re.split(r"[,，、|]", value)
    if not isinstance(value, (list, tuple)):
        return []
    out, seen = [], set()
    for item in value:
        text = re.sub(r"\[\[|\]\]", "", str(item)).strip().strip('"').strip("'")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _strip_fences(text: str) -> str:
    """去掉整体被 ```lang ... ``` 包裹的围栏，返回纯内容。"""
    if not text:
        return ""
    cleaned = text.strip()
    fence = re.match(r"^```[a-zA-Z0-9]*\s*\n?(.*?)\n?```$", cleaned, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return cleaned


def _extract_json(text: str) -> dict:
    """从模型回复里稳健地抽出 JSON 对象。

    依次尝试：去围栏直接解析 → 截取首个 { 到末个 } 解析 → 失败返回 {}。
    """
    cleaned = _strip_fences(text)
    if not cleaned:
        return {}
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(cleaned[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {}


def _call_model(vault: str, user_text: str, image_data_url: str, max_tokens: int, timeout: int,
                purpose: str = "") -> str:
    """组 OpenAI 兼容请求并返回模型回复的文本内容。错误以 ValueError 抛出。purpose 选择按用途配置的模型。"""
    base, key, model = _ai_config(vault, purpose)
    missing = [name for name, val in (("API 地址", base), ("API Key", key), ("模型", model)) if not val]
    if missing:
        raise ValueError("尚未配置 AI：请在「设置 → AI 自动识别」中填写 " + "、".join(missing))
    if not image_data_url or not isinstance(image_data_url, str):
        raise ValueError("缺少图片数据，请先粘贴或选择一张图片")

    # 指令 + 图片都放在 user 消息里（不设 System Message，兼容 Qwen-VL 推荐用法）
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": user_text},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(base),
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:600]
        except Exception:
            detail = ""
        raise ValueError(f"模型服务返回 HTTP {exc.code}：{detail or exc.reason}")
    except urllib.error.URLError as exc:
        raise ValueError(f"无法连接模型服务（请检查 API 地址 / 网络）：{getattr(exc, 'reason', exc)}")
    except TimeoutError:
        raise ValueError(f"模型服务超时（>{timeout}s），请稍后重试或更换模型")
    except Exception as exc:  # noqa: BLE001 - 兜底，转成可读错误
        raise ValueError(f"调用模型出错：{exc}")

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise ValueError(f"模型返回格式异常，无法解析：{raw[:600]}")

    # 个别供应商把 content 拆成 [{type:text,text:...}] 列表
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return content or ""


def _call_model_multi_image(vault: str, user_text: str, image_data_urls: list, max_tokens: int, timeout: int,
                            purpose: str = "") -> str:
    """支持多张图片的模型调用。图片按顺序排列，文本提示在最后。"""
    base, key, model = _ai_config(vault, purpose)
    missing = [name for name, val in (("API 地址", base), ("API Key", key), ("模型", model)) if not val]
    if missing:
        raise ValueError("尚未配置 AI：请在「设置 → AI 自动识别」中填写 " + "、".join(missing))
    if not image_data_urls or not isinstance(image_data_urls, list) or len(image_data_urls) == 0:
        raise ValueError("缺少图片数据")

    # 构建content数组：先放所有图片，最后放文本
    content_parts = []
    for img_url in image_data_urls:
        if img_url and isinstance(img_url, str):
            content_parts.append({"type": "image_url", "image_url": {"url": img_url}})
    content_parts.append({"type": "text", "text": user_text})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content_parts}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(base),
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:600]
        except Exception:
            detail = ""
        raise ValueError(f"模型服务返回 HTTP {exc.code}：{detail or exc.reason}")
    except urllib.error.URLError as exc:
        raise ValueError(f"无法连接模型服务（请检查 API 地址 / 网络）：{getattr(exc, 'reason', exc)}")
    except TimeoutError:
        raise ValueError(f"模型服务超时（>{timeout}s），请稍后重试或更换模型")
    except Exception as exc:
        raise ValueError(f"调用模型出错：{exc}")

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise ValueError(f"模型返回格式异常，无法解析：{raw[:600]}")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return content or ""


CLASSIFY_TEMPLATE = """你是错题分类助手。请根据图片中的题目%s，判断它的【科目】【分类】【难度】【相关知识点】【标记】，用于自动填充录入表单。不要转写题目原文，也不要解题。

已有科目：%s
已有分类（按科目分组；每个分类只属于它所在的科目）：
%s
已有知识点：%s
已有标记：%s

要求：
1. 先判断 subject，再判断 category。若 subject 属于「已有科目」，必须原样使用已有科目名。
2. category 必须严格属于所选 subject：只能从「已有分类」里该 subject 行下面选择。禁止把其他科目的分类拿来使用；即使分类名看起来很贴切，也不能跨科目借用。
3. 若所选 subject 下没有贴切的已有 category，才为该 subject 新建一个简洁分类名；不要从其他 subject 下面挑相近分类。
4. difficulty 为 1-10 的整数（10 最难），按题目综合难度估计。
5. knowledge_tags 为本题考查的知识点数组（0-4 个，按重要性排序）。**只能从上面的「所选科目下的已有分类」和「已有知识点」中原样挑选，禁止创造、改写或拆分出任何新词**；知识点可与分类重叠，若所选 category 属于所选科目的已有分类，通常也应作为其中一个 knowledge_tag。没有合适的已有项时，返回空数组 []。
6. labels 为建议的标记数组（0-3 个）。**只能从上面的「已有标记」中原样挑选**，根据题目特点选择（如：易错、计算失误、考前必看、重点题型等）。没有合适的已有标记时，返回空数组 []。
7. 只输出一个 JSON 对象，不要任何解释文字、也不要用 Markdown 代码块包裹。键固定如下：
{"subject": "", "category": "", "difficulty": 5, "knowledge_tags": [], "labels": []}"""


# 不限定知识点时使用：优先复用已有项，没有贴切的才允许新建。
CLASSIFY_TEMPLATE_OPEN = """你是错题分类助手。请根据图片中的题目%s，判断它的【科目】【分类】【难度】【相关知识点】【标记】，用于自动填充录入表单。不要转写题目原文，也不要解题。

已有科目：%s
已有分类（按科目分组；每个分类只属于它所在的科目）：
%s
已有知识点：%s
已有标记：%s

要求：
1. 先判断 subject，再判断 category。若 subject 属于「已有科目」，必须原样使用已有科目名。
2. category 必须严格属于所选 subject：只能从「已有分类」里该 subject 行下面选择。禁止把其他科目的分类拿来使用；即使分类名看起来很贴切，也不能跨科目借用。
3. 若所选 subject 下没有贴切的已有 category，才为该 subject 新建一个简洁分类名；不要从其他 subject 下面挑相近分类。
4. difficulty 为 1-10 的整数（10 最难），按题目综合难度估计。
5. knowledge_tags 为本题考查的知识点数组（0-4 个，按重要性排序）。**优先从上面的「所选科目下的已有分类」「已有知识点」里挑选**；只有当确实没有贴切的已有项时，才用简洁、规范的名称新建（避免生僻缩写、避免把一个知识点拆成多个）。知识点可与分类重叠，若所选 category 属于所选科目的已有分类，通常也应作为其中一个 knowledge_tag。
6. labels 为建议的标记数组（0-3 个）。**只能从上面的「已有标记」中原样挑选**，根据题目特点选择（如：易错、计算失误、考前必看、重点题型等）。没有合适的已有标记时，返回空数组 []。
7. 只输出一个 JSON 对象，不要任何解释文字、也不要用 Markdown 代码块包裹。键固定如下：
{"subject": "", "category": "", "difficulty": 5, "knowledge_tags": [], "labels": []}"""


ANSWER_PROMPT = """请忠实转录图片中这道题所有可见的【答案和解析】。这是内容提取任务，不是解题、总结或改写任务。

要求：
1. 完整提取最终答案，以及图片中已有的解析、详解、推导、计算步骤、选项说明和结论。
2. 如果图片中同时有答案和解析，两部分都必须保留；绝对不能只输出最终答案，也不能概括、压缩或省略解析。
3. 按图片中的原有顺序和层次输出，保留分点、段落与必要换行；数学公式可整理为 $...$ 或 $$...$$。
4. 如果图片最开头带有对应题目的题号（如 `11.`、`11、`、`11．`、`（11）`），只去掉这个开头题号，不要输出它；答案或解析正文内部的步骤编号、分点编号和选项编号必须保留。
5. 不要自行补充图片中没有的推理。若图片中确实只有答案而没有解析，才只输出答案。
6. 不要单独复述题目正文，但解析中原本引用的题目条件应照常保留。
7. 只输出提取到的答案与解析正文，不要添加评价、说明或 Markdown 代码块。"""


QUESTION_TEXT_PROMPT = (
    "请提取图片中这道题的【题目正文】，整理为清晰的纯文本。"
    "保留必要的题干、条件、选项、图表说明与换行；数学公式可用 $...$ 或 $$...$$ 表示。"
    "如果图片最开头有题号（如 11.、11、或（11）），只去掉这个开头题号，不要输出它；题目正文、选项编号和正文内部编号必须保留。"
    "只输出题目内容本身，不要解题，不要补充答案、解析、分类建议或多余说明，也不要使用 Markdown 代码块。"
)


_LEADING_QUESTION_NUMBER_RE = re.compile(
    r"^\s*(?:(?:第\s*)?\d{1,4}\s*[.．、,，:：)）]|[（(]\s*\d{1,4}\s*[)）])\s*"
)


def _clean_extracted_text(text: str, role: str) -> str:
    """去围栏，并去掉题目/答案最开头的对应题号。

    只匹配整段开头，避免误删答案解析中「1. 第一步」等内部编号。
    答案模式还要求题号后紧跟答案/解析标题，避免把解析本身的首个步骤编号当成题号。
    """
    cleaned = _strip_fences(text)
    if not cleaned:
        return ""
    if role == "answer":
        match = re.match(
            r"^\s*(?:(?:第\s*)?\d{1,4}\s*[.．、,，:：)）]|[（(]\s*\d{1,4}\s*[)）])\s*"
            r"(?=(?:答案|解析|解答|证明|作答|解|solution)\b|[A-DＡ-Ｄ](?:\s|$))",
            cleaned,
            re.IGNORECASE,
        )
    else:
        match = _LEADING_QUESTION_NUMBER_RE.match(cleaned)
    return cleaned[match.end():].lstrip() if match else cleaned


def classify_question(vault: str, image_data_url: str, timeout: int = 90,
                      hint_subject: str = "", hint_category: str = "",
                      restrict_tags: bool = None, answer_image: str = "") -> dict:
    """读题目图片（可选答案图片），返回 {subject, category, difficulty, knowledge_tags, labels}。

    hint_subject / hint_category：用户在表单里已填的科目/分类。若给出，会随提示词
    发给模型并要求**原样沿用、不要改动**，模型据此判断难度与知识点（更准更一致）。

    answer_image：可选的答案图片，如果提供，AI会同时分析题目和答案来更准确判断分类和标记。

    restrict_tags：是否把 knowledge_tags 限定在「已有分类 ∪ 已有知识点」内。
    - True ：用严格提示词，并对结果硬过滤（模型造的新词一律剔除）。
    - False：用宽松提示词，允许在没有贴切已有项时新建知识点（仅做归一化 + 上限 4 个）。
    - None ：读 config.json 的 `ai_restrict_tags`（默认 True），与设置页开关对应。
    """
    if restrict_tags is None:
        restrict_tags = bool(load_config(vault).get("ai_restrict_tags", True))
    taxonomy = collect_taxonomy(vault)

    # 获取已有标记
    # ``list_label_defs`` is the public labels API; keep archived definitions
    # out of the prompt (the helper already filters them, but retaining the
    # guard keeps this call safe for compatible/custom implementations).
    from .labels import list_label_defs
    existing_labels = [
        label["name"] for label in list_label_defs(vault)
        if not label.get("archived")
    ]

    answer_hint = "和答案" if answer_image and answer_image.strip() else ""
    template = CLASSIFY_TEMPLATE if restrict_tags else CLASSIFY_TEMPLATE_OPEN
    user_text = template % (
        answer_hint,
        "、".join(taxonomy["subjects"]) or "（暂无，可自行命名）",
        _format_category_tree(taxonomy),
        "、".join(taxonomy["knowledge_tags"]) or "（暂无）",
        "、".join(existing_labels) or "（暂无）",
    )
    hints = []
    if hint_subject and hint_subject.strip():
        hints.append(f"科目=「{hint_subject.strip()}」")
    if hint_category and hint_category.strip():
        hints.append(f"分类=「{hint_category.strip()}」")
    if hints:
        user_text += (
            "\n\n用户在表单中已指定：" + "、".join(hints)
            + "。这些已指定的值请**原样沿用、不要改动**（即按它们填回对应字段），"
            "并据此判断其余字段（难度、知识点、标记）。"
        )

    # 如果有答案图片，构建多图消息
    if answer_image and answer_image.strip():
        content = _call_model_multi_image(vault, user_text, [image_data_url, answer_image],
                                         max_tokens=600, timeout=timeout, purpose="classify")
    else:
        content = _call_model(vault, user_text, image_data_url, max_tokens=600, timeout=timeout, purpose="classify")

    parsed = _extract_json(content)
    subject, category = _normalize_subject_category(
        parsed, taxonomy, hint_subject=hint_subject.strip(), hint_category=hint_category.strip()
    )
    tags = _as_str_list(parsed.get("knowledge_tags", []))
    if restrict_tags:
        # 硬约束：相关知识点只能取自「所选科目的已有分类 ∪ 已有知识点」。
        # 未识别出科目时保留历史行为，允许使用全库已有分类。
        subject_categories = _categories_for_subject(taxonomy, subject)
        allowed_categories = subject_categories if subject else set(taxonomy["categories"])
        allowed = allowed_categories | set(taxonomy["knowledge_tags"])
        tags = [tag for tag in tags if tag in allowed]
    else:
        # 允许新建：仅按提示词约定限制数量（已去重 / 去 [[]] 由 _as_str_list 处理）
        tags = tags[:4]

    # 处理标记：只保留已有标记中的
    labels = _as_str_list(parsed.get("labels", []))
    existing_labels_set = set(existing_labels)
    labels = [label for label in labels if label in existing_labels_set][:3]

    return {
        "mode": "classify",
        "subject": subject,
        "category": category,
        "difficulty": _clamp_difficulty(parsed.get("difficulty", 5)),
        "knowledge_tags": tags,
        "labels": labels,
        "restrict_tags": restrict_tags,
        "raw": "" if parsed else content.strip(),
    }


def extract_answer(vault: str, image_data_url: str, timeout: int = 90) -> dict:
    """读答案图片，把答案/解析提取为纯文本，返回 {answer}。"""
    content = _call_model(vault, ANSWER_PROMPT, image_data_url, max_tokens=2000, timeout=timeout)
    return {"mode": "answer", "answer": _clean_extracted_text(content, "answer")}


def extract_question_text(vault: str, image_data_url: str, timeout: int = 90) -> dict:
    """读题目图片，只提取题目正文，返回 {question_text}。"""
    content = _call_model(vault, QUESTION_TEXT_PROMPT, image_data_url, max_tokens=2000, timeout=timeout)
    return {"mode": "question_text", "question_text": _clean_extracted_text(content, "question")}


def recognize_question(vault: str, image_data_url: str, mode: str = "classify", timeout: int = 90,
                       hint_subject: str = "", hint_category: str = "",
                       restrict_tags: bool = None, answer_image: str = "") -> dict:
    """统一入口：mode='classify' 填科目/分类/难度/知识点/标记（可带 hint，restrict_tags 控制是否
    限定已有知识点，None=读 config；可选 answer_image 提供答案图片以更准确分析）；
    mode='answer' 提取答案文本；mode='question_text' 提取题目文本。"""
    if mode == "answer":
        return extract_answer(vault, image_data_url, timeout=timeout)
    if mode in {"question_text", "question"}:
        return extract_question_text(vault, image_data_url, timeout=timeout)
    return classify_question(vault, image_data_url, timeout=timeout,
                             hint_subject=hint_subject, hint_category=hint_category,
                             restrict_tags=restrict_tags, answer_image=answer_image)


# ────────────────────────── 收件箱：框选 / 带可转性判断的提取 ──────────────────────────

DETECT_PROMPT = """这是一张错题相关的图片（%s）。请定位图中每道题的【题目区域】和【答案/解析区域】。

要求：
1. 题目区域：题干、选项、题图所在的矩形；答案区域：答案、解析、推导所在的矩形。UI 装饰（导航栏、标签页、广告、视频卡片、评论）一律不要。
2. 若图中有多道题，用 card 区分（同一道题的题目与答案 card 相同，从 1 起）。
3. bbox_2d 为 [x1, y1, x2, y2]，使用 0-1000 的相对坐标（左上角 0,0；右下角 1000,1000）。
4. 只输出 JSON 数组，不要解释、不要 Markdown 代码块：
[{"label": "question", "card": 1, "bbox_2d": [x1, y1, x2, y2], "confidence": 0.9}, {"label": "answer", "card": 1, "bbox_2d": [x1, y1, x2, y2], "confidence": 0.9}]
找不到某类区域就省略它；整张图什么都没有则输出 []。"""

_LAYOUT_HINT = {
    "zuoyebang": "作业帮 App 截图：题目在顶部「识别题目」卡片里，答案在下方「答案」标题之后；中间的「本题精讲」「相关视频」是广告，不要框",
    "photo": "教材 / 试卷拍照，可能有多道题和几何图形，题图要包含在题目区域内",
    "plain": "已裁好的题图，通常整张图就是题目",
    "other": "来源未知",
}

JUDGE_SUFFIX = """

另外请判断这块内容【能否忠实地转成纯文本 + LaTeX】：含几何图形、函数图像、手写、复杂版式（无法用 Markdown 表格表示的表格）时为不可转。
最终只输出一个 JSON 对象，不要 Markdown 代码块：
{"convertible": true, "reason": "一句话说明依据（如：纯文字+公式 / 含几何图形）", "text": "转录后的正文；不可转时可为空字符串"}"""


def parse_detect_output(text: str, image_width: int = 0, image_height: int = 0) -> list:
    """把模型的定位输出解析成归一化框 [{role, card, x, y, w, h, conf}]。

    兼容三种坐标：Qwen3-VL 的 0-1000 相对坐标（默认）；Qwen2.5-VL 风格的绝对像素
    （任一坐标 > 1000 且给了图片尺寸时按像素换算）；0-1 小数。"""
    cleaned = _strip_fences(text or "")
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        arr = json.loads(cleaned[start:end + 1])
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    boxes = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox_2d") or item.get("bbox") or item.get("box")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            continue
        try:
            x1, y1, x2, y2 = [float(v) for v in bbox]
        except (TypeError, ValueError):
            continue
        if max(x1, y1, x2, y2) <= 1.0:
            sx = sy = 1.0
        elif max(x1, y1, x2, y2) > 1000 and image_width and image_height:
            sx, sy = 1.0 / image_width, 1.0 / image_height
        else:
            sx = sy = 1.0 / 1000.0
        x1, x2 = sorted((x1 * sx, x2 * sx))
        y1, y2 = sorted((y1 * sy, y2 * sy))
        x1, y1 = max(0.0, min(1.0, x1)), max(0.0, min(1.0, y1))
        x2, y2 = max(0.0, min(1.0, x2)), max(0.0, min(1.0, y2))
        if x2 - x1 <= 0.005 or y2 - y1 <= 0.005:
            continue
        label = str(item.get("label") or item.get("role") or "question").strip().lower()
        role = "answer" if label.startswith(("answer", "答案", "解析")) else "question"
        try:
            card = max(1, int(item.get("card", 1) or 1))
        except (TypeError, ValueError):
            card = 1
        try:
            conf = float(item.get("confidence", item.get("conf", 0.7)) or 0.7)
        except (TypeError, ValueError):
            conf = 0.7
        boxes.append({"role": role, "card": card, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1,
                      "conf": max(0.0, min(1.0, conf))})
    return boxes


def detect_regions(vault: str, image_data_url: str, layout: str = "other", timeout: int = 120) -> list:
    """读整图（或长图条带），返回归一化题目/答案框。模型不支持定位时返回 []。"""
    prompt = DETECT_PROMPT % _LAYOUT_HINT.get(layout, _LAYOUT_HINT["other"])
    content = _call_model(vault, prompt, image_data_url, max_tokens=800, timeout=timeout, purpose="detect")
    return parse_detect_output(content)


def extract_region(vault: str, image_data_url: str, role: str = "question", judge: bool = True,
                   timeout: int = 120) -> dict:
    """读一个裁剪区域，转录文本；judge=True 时同时判断能否转文本。

    返回 {convertible, reason, text}。模型没按 JSON 返回时，把全文当作 text、convertible=True。"""
    base_prompt = ANSWER_PROMPT if role == "answer" else QUESTION_TEXT_PROMPT
    if judge:
        prompt = base_prompt + JUDGE_SUFFIX
    else:
        prompt = base_prompt
    content = _call_model(vault, prompt, image_data_url, max_tokens=4000, timeout=timeout, purpose="extract")
    if not judge:
        return {"convertible": True, "reason": "", "text": _clean_extracted_text(content, role)}
    parsed = _extract_json(content)
    if not parsed or "text" not in parsed:
        return {"convertible": True, "reason": "模型未按 JSON 返回，按可转处理", "text": _clean_extracted_text(content, role)}
    return {
        "convertible": bool(parsed.get("convertible", True)),
        "reason": str(parsed.get("reason") or ""),
        "text": _clean_extracted_text(str(parsed.get("text") or ""), role),
    }


def detect_regions_local(url: str, image_data_url: str, layout: str = "other",
                         image_width: int = 0, image_height: int = 0, timeout: int = 60) -> list:
    """本地检测服务 provider（`local_http`）：训好的 YOLO / ONNX 服务按与 detect 单元一致的协议返回框。

    请求：`POST <url>`，JSON `{image: dataURL, layout, width, height}`。
    响应：JSON 数组 `[{label, card, bbox_2d:[x1,y1,x2,y2], confidence}]`，或对象 `{boxes:[…]}`。
    坐标可以是 0–1000 相对、0–1 小数或绝对像素（给了 width/height 时），与 VLM 输出同样经
    parse_detect_output 归一化。主程序保持零依赖，只用 urllib。"""
    url = (url or "").strip()
    if not url:
        raise ValueError("尚未配置本地检测服务地址（inbox_local_detect_url）")
    body = json.dumps({"image": image_data_url, "layout": layout, "width": image_width, "height": image_height},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"本地检测服务返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"连不上本地检测服务：{exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValueError("本地检测服务未返回 JSON") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("boxes") or parsed.get("regions") or []
    if not isinstance(parsed, list):
        raise ValueError("本地检测服务返回格式不对：需要数组或 {boxes:[…]}")
    return parse_detect_output(json.dumps(parsed), image_width, image_height)
