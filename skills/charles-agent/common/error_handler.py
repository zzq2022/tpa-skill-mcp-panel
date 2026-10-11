# -*- coding: utf-8 -*-
"""
统一错误处理 - 三要素格式（What / Why / How）

为所有 skill 提供一致的错误报告格式，包含：
1. What: 正在执行什么操作
2. Why: 失败的根本原因
3. How: 用户如何解决（下一步行动）
"""
import json
from typing import Optional


class SkillError(Exception):
    """Skill 执行错误基类 - 包含结构化错误信息"""

    def __init__(
        self,
        operation: str,
        reason: str,
        next_action: str,
        details: Optional[dict] = None
    ):
        """初始化 SkillError

        Args:
            operation: 正在执行的操作描述
            reason: 失败的根本原因
            next_action: 建议用户采取的下一步行动
            details: 可选的详细错误信息（字典格式）
        """
        self.operation = operation
        self.reason = reason
        self.next_action = next_action
        self.details = details or {}
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """格式化错误消息 - 三要素清晰展示"""
        msg = f"""
❌ 操作失败: {self.operation}

原因: {self.reason}

建议: {self.next_action}
"""
        if self.details:
            msg += f"\n详细信息:\n{json.dumps(self.details, ensure_ascii=False, indent=2)}"
        return msg

    def to_json(self) -> dict:
        """返回 JSON 格式错误信息

        Returns:
            dict: 包含 status, operation, reason, next_action, details 的字典
        """
        return {
            "status": "failed",
            "operation": self.operation,
            "reason": self.reason,
            "next_action": self.next_action,
            "details": self.details
        }


def format_error_message(error: Exception) -> str:
    """将异常格式化为统一的三要素错误字符串

    Args:
        error: 任意异常对象，SkillError 会保留结构化信息，其他异常会被包装

    Returns:
        str: 统一格式化的错误消息
    """
    if isinstance(error, SkillError):
        return error.format_message()
    skill_error = SkillError(
        operation="执行脚本",
        reason=f"未预期的错误: {type(error).__name__}: {error}",
        next_action="请检查日志或联系开发者",
        details={
            "exception_type": type(error).__name__,
            "exception_str": str(error)
        }
    )
    return skill_error.format_message()
