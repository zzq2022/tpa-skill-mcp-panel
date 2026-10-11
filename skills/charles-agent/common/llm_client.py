# -*- coding: utf-8 -*-
"""
LLM 调用辅助 - 跨 skill 复用

从 LLM 响应对象中提取文本内容的通用工具。
支持多种响应格式：对象属性、字典、列表等。
"""


def message_content(response) -> str:
    """从 LLM 响应中提取文本内容。

    Args:
        response: LLM API 返回的响应对象，可能是：
            - 具有 .content 属性的对象
            - 包含 "content" 键的字典
            - 响应对象的列表（取最后一个）
            - 其他可转换为字符串的对象

    Returns:
        str: 提取的文本内容

    Examples:
        >>> from common.llm_client import message_content
        >>> response = {"content": "这是LLM的回复"}
        >>> message_content(response)
        '这是LLM的回复'
    """
    if hasattr(response, "content"):
        return str(response.content)
    if isinstance(response, dict):
        return response.get("content", str(response))
    if isinstance(response, list) and response:
        return message_content(response[-1])
    return str(response)
