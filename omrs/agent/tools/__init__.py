"""OMRS 工具注册表。权限级别见 omrs/agent/policy.py；不注册的能力模型无从调用。"""
from . import drafts, read, write


class ToolDef:
    def __init__(self, name, level, description, schema, run, preview=None):
        self.name, self.level, self.description, self.schema = name, level, description, schema
        self.run, self.preview = run, preview

    def openai_schema(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.schema}}


class Registry:
    def __init__(self, tools):
        self._tools = {t.name: t for t in tools}

    def get(self, name):
        return self._tools.get(name)

    def schemas(self):
        return [t.openai_schema() for t in self._tools.values()]

    def names(self):
        return list(self._tools)

    def levels(self):
        return {t.name: t.level for t in self._tools.values()}


def build_registry(settings=None):
    tools = [ToolDef(*spec) for spec in read.SPECS + drafts.SPECS + write.SPECS]
    return Registry(tools)
