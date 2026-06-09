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
    for row in rows:
        subject = (row.get("Subject") or "").strip()
        if subject:
            subjects.add(subject)
        category = (row.get("Category") or "").strip()
        if category:
            categories.add(category)
        for tag in (row.get("Knowledge_Tags") or "").split("|"):
            tag = tag.strip()
            if tag:
                ktags.add(tag)
    return {
        "subjects": sorted(subjects),
        "categories": sorted(categories),
        "knowledge_tags": sorted(ktags),
    }


def _ai_config(vault: str):
    cfg = load_config(vault)
    base = (cfg.get("ai_base_url") or "").strip().rstrip("/")
    key = (cfg.get("ai_api_key") or "").strip()
    model = (cfg.get("ai_model") or "").strip()
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


def _call_model(vault: str, user_text: str, image_data_url: str, max_tokens: int, timeout: int) -> str:
    """组 OpenAI 兼容请求并返回模型回复的文本内容。错误以 ValueError 抛出。"""
    base, key, model = _ai_config(vault)
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


CLASSIFY_TEMPLATE = """你是错题分类助手。请只根据图片中的题目，判断它的【科目】【分类】【难度】【相关知识点】，用于自动填充录入表单。不要转写题目原文，也不要解题。

已有科目：%s
已有分类：%s
已有知识点：%s

要求：
1. subject / category 尽量从上面「已有」列表里选最贴切的；确实没有合适项时才用一个简洁名称新建。
2. difficulty 为 1-10 的整数（10 最难），按题目综合难度估计。
3. knowledge_tags 为本题考查的知识点数组（0-4 个，按重要性排序）。**只能从上面的「已有分类」和「已有知识点」中原样挑选，禁止创造、改写或拆分出任何新词**；知识点可与分类重叠，若所选 category 属于「已有分类」，通常也应作为其中一个 knowledge_tag。没有合适的已有项时，返回空数组 []。
4. 只输出一个 JSON 对象，不要任何解释文字、也不要用 Markdown 代码块包裹。键固定如下：
{"subject": "", "category": "", "difficulty": 5, "knowledge_tags": []}"""


# 不限定知识点时使用：优先复用已有项，没有贴切的才允许新建。
CLASSIFY_TEMPLATE_OPEN = """你是错题分类助手。请只根据图片中的题目，判断它的【科目】【分类】【难度】【相关知识点】，用于自动填充录入表单。不要转写题目原文，也不要解题。

已有科目：%s
已有分类：%s
已有知识点：%s

要求：
1. subject / category 尽量从上面「已有」列表里选最贴切的；确实没有合适项时才用一个简洁名称新建。
2. difficulty 为 1-10 的整数（10 最难），按题目综合难度估计。
3. knowledge_tags 为本题考查的知识点数组（0-4 个，按重要性排序）。**优先从上面的「已有分类」「已有知识点」里挑选**；只有当确实没有贴切的已有项时，才用简洁、规范的名称新建（避免生僻缩写、避免把一个知识点拆成多个）。知识点可与分类重叠，若所选 category 属于「已有分类」，通常也应作为其中一个 knowledge_tag。
4. 只输出一个 JSON 对象，不要任何解释文字、也不要用 Markdown 代码块包裹。键固定如下：
{"subject": "", "category": "", "difficulty": 5, "knowledge_tags": []}"""


ANSWER_PROMPT = (
    "请提取图片中这道题的【答案 / 解析】，并整理为清晰的纯文本。"
    "可保留必要的步骤与换行，公式可用 $...$ 表示。"
    "只输出答案内容本身，不要复述题目，也不要任何多余说明或 Markdown 代码块。"
)


def classify_question(vault: str, image_data_url: str, timeout: int = 90,
                      hint_subject: str = "", hint_category: str = "",
                      restrict_tags: bool = None) -> dict:
    """读题目图片，返回 {subject, category, difficulty, knowledge_tags}。

    hint_subject / hint_category：用户在表单里已填的科目/分类。若给出，会随提示词
    发给模型并要求**原样沿用、不要改动**，模型据此判断难度与知识点（更准更一致）。

    restrict_tags：是否把 knowledge_tags 限定在「已有分类 ∪ 已有知识点」内。
    - True ：用严格提示词，并对结果硬过滤（模型造的新词一律剔除）。
    - False：用宽松提示词，允许在没有贴切已有项时新建知识点（仅做归一化 + 上限 4 个）。
    - None ：读 config.json 的 `ai_restrict_tags`（默认 True），与设置页开关对应。
    """
    if restrict_tags is None:
        restrict_tags = bool(load_config(vault).get("ai_restrict_tags", True))
    taxonomy = collect_taxonomy(vault)
    template = CLASSIFY_TEMPLATE if restrict_tags else CLASSIFY_TEMPLATE_OPEN
    user_text = template % (
        "、".join(taxonomy["subjects"]) or "（暂无，可自行命名）",
        "、".join(taxonomy["categories"]) or "（暂无，可自行命名）",
        "、".join(taxonomy["knowledge_tags"]) or "（暂无）",
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
            "并据此判断其余字段（难度、知识点）。"
        )
    content = _call_model(vault, user_text, image_data_url, max_tokens=600, timeout=timeout)
    parsed = _extract_json(content)
    tags = _as_str_list(parsed.get("knowledge_tags", []))
    if restrict_tags:
        # 硬约束：相关知识点只能取自「已有分类 ∪ 已有知识点」，模型若造新词一律剔除
        allowed = set(taxonomy["categories"]) | set(taxonomy["knowledge_tags"])
        tags = [tag for tag in tags if tag in allowed]
    else:
        # 允许新建：仅按提示词约定限制数量（已去重 / 去 [[]] 由 _as_str_list 处理）
        tags = tags[:4]
    return {
        "mode": "classify",
        "subject": str(parsed.get("subject", "")).strip(),
        "category": str(parsed.get("category", "")).strip(),
        "difficulty": _clamp_difficulty(parsed.get("difficulty", 5)),
        "knowledge_tags": tags,
        "restrict_tags": restrict_tags,
        "raw": "" if parsed else content.strip(),
    }


def extract_answer(vault: str, image_data_url: str, timeout: int = 90) -> dict:
    """读答案图片，把答案/解析提取为纯文本，返回 {answer}。"""
    content = _call_model(vault, ANSWER_PROMPT, image_data_url, max_tokens=2000, timeout=timeout)
    return {"mode": "answer", "answer": _strip_fences(content)}


def recognize_question(vault: str, image_data_url: str, mode: str = "classify", timeout: int = 90,
                       hint_subject: str = "", hint_category: str = "",
                       restrict_tags: bool = None) -> dict:
    """统一入口：mode='classify' 填科目/分类/难度/知识点（可带 hint，restrict_tags 控制是否
    限定已有知识点，None=读 config）；mode='answer' 提取答案文本。"""
    if mode == "answer":
        return extract_answer(vault, image_data_url, timeout=timeout)
    return classify_question(vault, image_data_url, timeout=timeout,
                             hint_subject=hint_subject, hint_category=hint_category,
                             restrict_tags=restrict_tags)
