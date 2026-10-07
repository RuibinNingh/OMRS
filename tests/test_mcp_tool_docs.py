"""文档元数据不能改变现有工具参数的接受范围。"""
import tempfile
import unittest
from unittest.mock import patch

try:
    from omrs.mcp.server import build_server
except ImportError:
    build_server = None


def validation_schema(value):
    """去掉说明、示例及无校验作用的空字段声明，比较实际约束。"""
    if isinstance(value, list):
        return [validation_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    clean = {key: validation_schema(item) for key, item in value.items()
             if key not in ('description', 'examples')}
    if 'properties' in clean:
        clean['properties'] = {key: item for key, item in clean['properties'].items() if item}
        if not clean['properties']:
            clean.pop('properties')
    return clean


@unittest.skipIf(build_server is None, '缺少可选 MCP 依赖')
class MCPToolDocsTests(unittest.TestCase):
    def test_descriptions_preserve_validation_contracts(self):
        with tempfile.TemporaryDirectory(prefix='omrs-mcp-tool-docs-') as vault:
            with patch('omrs.mcp.server.apply_parameter_docs'):
                original = {t.name: validation_schema(t.parameters)
                            for t in build_server(vault)._tool_manager.list_tools()}
            documented = {t.name: validation_schema(t.parameters)
                          for t in build_server(vault)._tool_manager.list_tools()}
        self.assertEqual(documented, original)
