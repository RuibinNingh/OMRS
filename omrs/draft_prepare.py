"""助手与外部 MCP 共用的草稿内容准备规则。"""


def merge_answer_text_runs(blocks):
    """答案块只在图片处断开；合并模型按段落拆出的相邻文字块。"""
    normalized = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.get("section") != "答案" or block.get("kind") != "text":
            normalized.append(dict(block))
            i += 1
            continue
        run = [block]
        i += 1
        while i < len(blocks) and blocks[i].get("section") == "答案" and blocks[i].get("kind") == "text":
            run.append(blocks[i])
            i += 1
        if len(run) == 1:
            normalized.append(dict(run[0]))
            continue
        merged = dict(run[0])
        merged["text"] = "\n\n".join(str(item.get("text") or "").strip() for item in run)
        notes = [str(item.get("note") or "").strip() for item in run if str(item.get("note") or "").strip()]
        if notes:
            merged["note"] = "\n".join(dict.fromkeys(notes))
        normalized.append(merged)
    return normalized
