---
name: stock-price
description: "Use when fetching A-share quotes, K-line history, or technical market data for a named symbol."
---

# stock-price

## Goal

获取目标证券带明确数据时间截面（`as_of`）、周期和来源的行情 evidence artifact。

## Input

- **证券代码**：带市场后缀的标准化代码（如 `600519.SH`、`000001.SZ`）。
- **行情参数**：K 线周期（如 `1d`）与获取条数。
- **运行依赖**：本地已启动并登录的 MiniQMT 客户端，以及当前环境中的 `xtquant`。

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本。已登记 CLI 的依赖或数据源不可用时返回 `unavailable`，不得临时接入任何未登记接口。
- **环境隔离**：CLI 独立加载项目根目录 `.env`。

## Internal workflow

### 1. 参数核验（Parameter Verification）
- **操作**：验证股票代码格式（必须包含 `.SH`/`.SZ` 后缀）、K 线周期与有效请求条数。
- **完成准则**：参数合法完整；若代码格式错误，返回 `unavailable`。

### 2. 行情获取（Fetch K-Line）
- **操作**：运行 `get_kline.py` 获取目标标的行情数据。
- **完成准则**：成功接收包含时间戳、开高低收（OHLC）及成交量（Volume）的数据集。

### 3. 指标提炼与证据标定（Evidence Extraction）
- **操作**：基于最新有效记录计算最新价格、区间涨跌幅与成交额变化，并标注真实数据时间戳（`as_of`）与数据源。
- **完成准则**：生成包含结构化行情指标与数据时间说明的 `evidence` artifact，交回根 Skill 用于预期差分析。

## Output

标准结果信封中登记 `evidence` artifact，关键字段包含：
- 证券代码与名称。
- 数据时间截面（`as_of`）与 K 线周期。
- 最新价格、开高低收（OHLC）、成交量（Volume）与涨跌幅。
- 数据来源（MiniQMT/xtquant）与时效状态。

## Failure handling

- **`unavailable`**：MiniQMT 客户端未登录、`xtquant` 依赖缺失或代码无效，且无可用已登记备用接口。
- **`partial`**：成功获取历史 K 线，但最新记录时间戳落后于当前交易时点（需明确披露时延）。
- **`failed`**：数据源连接异常或脚本执行崩溃。
- **约束**：所有行情数据必须以实际接口返回为准，禁止使用静态伪造或过期行情冒充实时数据。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#stock-price)，也可运行 `get_kline.py --help`。
