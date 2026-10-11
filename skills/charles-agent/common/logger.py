# -*- coding: utf-8 -*-
"""
统一日志 - 可配置级别

为所有 skill 提供一致的日志输出格式。
支持 DEBUG、INFO、WARN、ERROR 四个级别。
"""
import sys
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3


class SkillLogger:
    """Skill 统一日志记录器"""

    def __init__(self, skill_name: str, level: LogLevel = LogLevel.INFO):
        """初始化日志记录器

        Args:
            skill_name: skill 或脚本名称（用于日志标识）
            level: 最低日志级别（默认 INFO）
        """
        self.skill_name = skill_name
        self.level = level

    def _log(self, level: LogLevel, message: str):
        """内部日志输出方法

        Args:
            level: 日志级别
            message: 日志消息
        """
        if level.value >= self.level.value:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            prefix = {
                LogLevel.DEBUG: "🔍",
                LogLevel.INFO: "ℹ️",
                LogLevel.WARN: "⚠️",
                LogLevel.ERROR: "❌"
            }[level]
            print(
                f"[{timestamp}] [{self.skill_name}] {prefix} {message}",
                file=sys.stderr
            )

    def debug(self, message: str):
        """输出 DEBUG 级别日志

        Args:
            message: 日志消息
        """
        self._log(LogLevel.DEBUG, message)

    def info(self, message: str):
        """输出 INFO 级别日志

        Args:
            message: 日志消息
        """
        self._log(LogLevel.INFO, message)

    def warn(self, message: str):
        """输出 WARN 级别日志

        Args:
            message: 日志消息
        """
        self._log(LogLevel.WARN, message)

    def error(self, message: str):
        """输出 ERROR 级别日志

        Args:
            message: 日志消息
        """
        self._log(LogLevel.ERROR, message)

    # 兼容别名
    warning = warn
