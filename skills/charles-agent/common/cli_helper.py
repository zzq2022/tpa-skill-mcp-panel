# -*- coding: utf-8 -*-
"""
CLI 帮助文档生成器。
"""


class CLIHelper:
    """旧版 CLI 助手兼容类

    支持原接口：
      cli = CLIHelper(script_name=..., description=..., examples=[...])
      cli.description, cli.format_examples()
    """

    def __init__(self, script_name: str, description: str, examples: list = None):
        self.script_name = script_name
        self.description = description
        self.examples = examples or []

    def format_examples(self) -> str:
        """格式化示例列表为帮助文档 epilog 字符串"""
        if not self.examples:
            return ""
        lines = ["示例用法:"]
        for i, ex in enumerate(self.examples, 1):
            lines.append(f"\n  {i}. {ex}")
        return "\n".join(lines)
