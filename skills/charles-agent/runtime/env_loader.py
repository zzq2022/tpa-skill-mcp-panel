#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared, silent environment loader for child skills."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_from_root() -> Path | None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return None
    load_dotenv(env_path)
    return env_path
