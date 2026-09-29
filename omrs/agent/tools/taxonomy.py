"""独立创建分类：确认后写目录和锚点，不产生题目 Ledger commit。"""
from ...taxonomy import category_path, create_category


def preview(ctx, args):
    _, subject, category = category_path(ctx["vault"], args["subject"], args["category"])
    return {"subject": subject, "category": category,
            "message": "确认后永久创建分类目录和锚点；此操作不支持按运行自动撤销。"}


def run(ctx, args):
    result = create_category(ctx["vault"], args["subject"], args["category"])
    return {"result": result, "summary": f"{result['subject']} / {result['category']}",
            "wrote": result["wrote"]}


SPECS = [("create_category", "confirm", "独立创建永久分类。仅在用户明确要求新建分类时调用；创建需用户确认。",
          {"type": "object", "required": ["subject", "category"], "additionalProperties": False,
           "properties": {"subject": {"type": "string", "minLength": 1},
                          "category": {"type": "string", "minLength": 1}}}, run, preview)]
