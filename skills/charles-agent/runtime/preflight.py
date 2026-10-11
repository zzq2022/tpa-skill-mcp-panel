# -*- coding: utf-8 -*-
"""
环境预检 - 启动前检查所有依赖和配置

在执行任何 skill 之前，检查：
1. Python 包依赖是否安装
2. 环境变量是否配置
3. 必需目录是否存在
4. API 连通性测试
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# Windows GBK 环境强制使用 UTF-8 输出
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 加载 .env 文件（必须在检查环境变量前加载）
try:
    from dotenv import load_dotenv
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    _env_path = PROJECT_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        print(f"⚠️ 未找到 .env 文件: {_env_path}")
        print("   请参考 .env.example 创建配置文件\n")
except ImportError:
    print("⚠️ python-dotenv 未安装，跳过 .env 加载\n")
    print("   建议: pip install python-dotenv\n")


def check_python_packages() -> Tuple[bool, List[str]]:
    """检查必需的 Python 包是否已安装

    Returns:
        (是否全部通过, 缺失的包列表)
    """
    required_packages = [
        "pandas",
        "numpy",
        "akshare",
        "faiss-cpu",  # 或 faiss-gpu
        "langchain",
        "langchain_community",
        "langchain_openai",
        "openai",
        "pymupdf",
    ]

    missing = []
    for pkg in required_packages:
        try:
            # 特殊处理 faiss
            if pkg == "faiss-cpu":
                try:
                    import faiss
                except ImportError:
                    missing.append(pkg)
            else:
                __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)

    return len(missing) == 0, missing


def check_environment_variables() -> Tuple[bool, List[str]]:
    """检查必需的环境变量是否配置

    必需的环境变量：
    - OPENAI_API_KEY, OPENAI_BASE_URL
    - EMBEDDING_API_KEY, EMBEDDING_BASE_URL

    Returns:
        (是否全部通过, 缺失的环境变量列表)
    """
    missing = []

    # 检查 LLM API Key
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    # 检查 LLM Base URL
    if not os.getenv("OPENAI_BASE_URL"):
        missing.append("OPENAI_BASE_URL")

    # 检查 Embedding API Key
    if not os.getenv("EMBEDDING_API_KEY"):
        missing.append("EMBEDDING_API_KEY")

    # 检查 Embedding Base URL
    if not os.getenv("EMBEDDING_BASE_URL"):
        missing.append("EMBEDDING_BASE_URL")

    return len(missing) == 0, missing


def check_directories() -> Tuple[bool, List[str]]:
    """检查必需的目录结构是否存在

    Returns:
        (是否全部通过, 缺失的目录列表)
    """
    from pathlib import Path

    project_root = Path(__file__).parent.parent
    required_dirs = [
        project_root / "skills",
        project_root / "runtime",
        project_root / "common",
    ]

    missing = []
    for d in required_dirs:
        if not d.exists():
            missing.append(str(d))

    return len(missing) == 0, missing


def test_api_connectivity() -> Tuple[bool, str]:
    """测试 API 连通性

    Returns:
        (是否连通, 错误信息)
    """
    try:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")

        if not api_key or not base_url:
            return False, "LLM API 配置缺失"

        client = OpenAI(api_key=api_key, base_url=base_url)
        # 简单的连通性测试（发送最小请求）
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )

        return True, ""
    except Exception as e:
        return False, f"API 连接失败: {type(e).__name__}: {e}"


def test_embedding_connectivity() -> Tuple[bool, str]:
    """Test the configured embedding endpoint independently from the LLM."""
    try:
        from openai import OpenAI

        api_key = os.getenv("EMBEDDING_API_KEY")
        base_url = os.getenv("EMBEDDING_BASE_URL")
        model = os.getenv("EMBEDDING_BASE_MODEL")
        if not api_key or not base_url or not model:
            return False, "Embedding API 配置缺失"
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.embeddings.create(model=model, input=["connectivity test"])
        if not getattr(response, "data", None):
            return False, "Embedding API 返回空数据"
        return True, ""
    except Exception as e:
        return False, f"Embedding API 连接失败: {type(e).__name__}: {e}"


def _safe_print(*args, **kwargs) -> None:
    try:
        print(*args, **kwargs)
    except (ValueError, OSError):
        pass


def run_preflight_check(verbose: bool = True, check_api: bool = True) -> bool:
    """运行完整的预检流程

    Args:
        verbose: 是否输出详细信息

    Returns:
        是否全部通过
    """
    if verbose:
        _safe_print("🔍 开始环境预检...\n")

    all_passed = True

    # 1. 检查 Python 包
    if verbose:
        _safe_print("1️⃣ 检查 Python 包依赖...")
    pkg_ok, missing_pkgs = check_python_packages()
    if pkg_ok:
        if verbose:
            _safe_print("   ✅ 所有依赖包已安装\n")
    else:
        _safe_print("   ❌ 缺失依赖包:")
        for pkg in missing_pkgs:
            _safe_print(f"      - {pkg}")
        _safe_print(f"\n   建议: pip install {' '.join(missing_pkgs)}\n")
        all_passed = False

    # 2. 检查环境变量
    if verbose:
        _safe_print("2️⃣ 检查环境变量配置...")
    env_ok, missing_vars = check_environment_variables()
    if env_ok:
        if verbose:
            _safe_print("   ✅ 所有环境变量已配置\n")
    else:
        _safe_print("   ❌ 缺失环境变量:")
        for var in missing_vars:
            _safe_print(f"      - {var}")
        _safe_print("\n   建议: 在 .env 文件或系统环境中配置这些变量\n")
        all_passed = False

    # 3. 检查目录结构
    if verbose:
        _safe_print("3️⃣ 检查目录结构...")
    dir_ok, missing_dirs = check_directories()
    if dir_ok:
        if verbose:
            _safe_print("   ✅ 目录结构完整\n")
    else:
        _safe_print("   ❌ 缺失目录:")
        for d in missing_dirs:
            _safe_print(f"      - {d}")
        _safe_print("\n   建议: 检查项目结构是否完整\n")
        all_passed = False

    # 4. 测试 API 连通性（仅在前面检查都通过时）
    if all_passed and check_api:
        if verbose:
            _safe_print("4️⃣ 测试 API 连通性...")
        api_ok, api_error = test_api_connectivity()
        if api_ok:
            if verbose:
                _safe_print("   ✅ API 连接正常\n")
        else:
            _safe_print(f"   ❌ API 连接测试失败: {api_error}\n")
            all_passed = False

        embedding_ok, embedding_error = test_embedding_connectivity()
        if embedding_ok:
            if verbose:
                _safe_print("   ✅ Embedding API 连接正常\n")
        else:
            _safe_print(f"   ❌ Embedding API 连接测试失败: {embedding_error}\n")
            all_passed = False

    # 总结
    if all_passed:
        if verbose:
            _safe_print("✅ 预检通过，环境就绪！\n")
        return True
    else:
        if verbose:
            _safe_print("❌ 预检失败，请修复上述问题后再启动。\n")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Charles Skill 环境预检")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式（仅输出错误）"
    )
    parser.add_argument("--skip-api", action="store_true", help="仅检查本地依赖和配置")
    args = parser.parse_args()

    success = run_preflight_check(verbose=not args.quiet, check_api=not args.skip_api)
    sys.exit(0 if success else 1)
