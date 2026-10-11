#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniQMT K 线数据获取脚本
通过 xtquant 获取指定股票的 K 线数据，输出 JSON
"""

import sys
import json
from pathlib import Path

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("get_kline", level=LogLevel.INFO)

# 快速失败：xtquant不可用时立即退出，避免挂起
try:
    import xtquant
except ImportError:
    result = {
        "status": "unavailable",
        "module": "stock-price",
        "summary": {},
        "artifacts": [],
        "sources": [],
        "warnings": [],
        "errors": ["xtquant is not installed or MiniQMT is not available"],
        "next_actions": ["install xtquant and ensure MiniQMT is running"]
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)  # 不是错误退出，是正常的unavailable状态


def get_kline_data(stock_code, period='1d', start_date='', end_date='', count=100):
    """
    获取 MiniQMT K 线数据

    Args:
        stock_code: 股票代码，如 '000001.SZ'
        period: 周期，支持 '1m','5m','15m','30m','1h','1d','1w','1mon'
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
        count: 获取条数
    """
    try:
        import pandas as pd
        from xtquant import xtdata
    except ImportError as e:
        return {"error": f"缺少依赖: {e}"}

    try:
        xtdata.connect()
        # 1. 先下载历史数据（增量更新）
        xtdata.download_history_data(
            stock_code,
            period=period,
            start_time=start_date if start_date else '19900101',
            end_time=end_date if end_date else '',
            incrementally=True
        )

        # 2. 获取市场数据
        data = xtdata.get_market_data_ex(
            field_list=['open', 'high', 'low', 'close', 'volume', 'amount'],
            stock_list=[stock_code],
            period=period,
            start_time=start_date,
            end_time=end_date,
            count=count
        )

        if not data or stock_code not in data:
            return {"error": f"未获取到 {stock_code} 的数据"}
        df = data[stock_code]
        if df is None or len(df) == 0:
            return {"error": f"{stock_code} 无数据"}

        # 3. 数据处理
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df['date'] = df['time'].dt.strftime('%Y-%m-%d')
            df['datetime'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            df.index = pd.to_datetime(df.index)
            df['date'] = df.index.strftime('%Y-%m-%d')
            df['datetime'] = df.index.strftime('%Y-%m-%d %H:%M:%S')

        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].round(3)

        records = df.to_dict('records')
        records = [{"date": r.get("date", ""), "open": float(r.get("open", 0)),
                   "high": float(r.get("high", 0)), "low": float(r.get("low", 0)),
                   "close": float(r.get("close", 0)), "volume": int(r.get("volume", 0)),
                   "amount": float(r.get("amount", 0))} for r in records]

        return {
            "stock_code": stock_code,
            "period": period,
            "data_count": len(records),
            "data": records[-50:] if len(records) > 50 else records
        }
    except Exception as e:
        return {"error": f"获取失败: {str(e)}"}


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="get_kline.py",
        description="MiniQMT K 线数据获取脚本 - 通过 xtquant 获取股票 K 线数据",
        examples=[
            "python get_kline.py --stock 000001.SZ",
            "python get_kline.py --stock 600519.SH --period 1d --count 200",
            "python get_kline.py --stock 000858.SZ --period 1w --count 52",
        ]
    )

    import argparse
    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stock", required=True, help="股票代码（如 000001.SZ, 600519.SH）")
    parser.add_argument("--period", default="1d", help="K 线周期（默认: 1d，支持: 1m,5m,15m,30m,1h,1d,1w,1mon）")
    parser.add_argument("--count", type=int, default=100, help="获取条数（默认: 100）")
    args = parser.parse_args()

    try:
        logger.info(f"获取 {args.stock} 的 {args.period} K 线数据（{args.count} 条）")

        data = get_kline_data(args.stock, period=args.period, count=args.count)

        if "error" in data:
            raise SkillError(
                operation="获取 K 线数据",
                reason=data["error"],
                next_action="请确保 xtquant 已安装且 MiniQMT 正在运行"
            )

        result = {
            "status": "success",
            "module": "stock-price",
            "summary": {
                "stock_code": data["stock_code"],
                "period": data["period"],
                "data_count": data["data_count"]
            },
            "artifacts": [],
            "sources": [{"type": "market-data", "provider": "xtquant", "stock_code": args.stock}],
            "warnings": [],
            "errors": [],
            "next_actions": []
        }

        logger.info(f"成功获取 {data['data_count']} 条 K 线数据")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="获取 K 线数据",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查 xtquant 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
