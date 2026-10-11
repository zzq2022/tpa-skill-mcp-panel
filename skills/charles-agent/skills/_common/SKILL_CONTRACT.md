# 子 Skill 交接契约

根 Skill 负责跨 Skill 顺序；子 Skill 只负责自己的内部流程。子 Skill 通过明确的结果信封和 artifact 路径交接，不依赖后台状态文件或 stdout 中猜测出的路径。

## Result envelope

每次子 Skill 执行返回：

```json
{
  "status": "success|partial|unavailable|failed",
  "module": "read-pdf",
  "summary": {},
  "artifacts": [],
  "sources": [],
  "warnings": [],
  "errors": [],
  "next_actions": []
}
```

状态含义：

- `success`：必需输入、目标期间和声明产物完整。
- `partial`：至少有一个有效产物，但存在数据、期间或证据缺口。
- `unavailable`：缺少输入、环境能力或证据，未形成有效产物。
- `failed`：CLI 或内部处理失败，且没有可交付结果。

## Artifact record

每个 artifact 至少声明：

```json
{
  "path": "analysis/financial/metrics.json",
  "type": "evidence|analysis|comparison|report|index|data",
  "subject": "目标对象",
  "period": "2025FY",
  "status": "available|partial|unavailable",
  "description": "产物内容和用途"
}
```

路径必须真实存在并可由宿主读取。下游先验证类型、对象、期间和状态，再决定复用；不能仅凭文件名推断兼容性。

## Evidence record

关键事实使用以下字段：

```json
{
  "claim": "可验证陈述",
  "locator": "文件、PDF页码或URL",
  "field": "原始字段或null",
  "period": "报告期或null",
  "as_of": "数据时间或null",
  "formula": "派生公式或null",
  "source_type": "filing|market|consensus|news",
  "confidence": "high|medium|low"
}
```

财务数值必须有 `period`；行情、估值和新闻必须有 `as_of`；派生数值必须有 `field` 和 `formula`。`locator` 不能只指向临时日志。

## Handoff rules

1. 子 Skill 输出后，宿主记录结果信封和实际 artifact 路径。
2. 下游只消费状态为 `success` 或可明确降级使用的 `partial` artifact。
3. 对象、期间或数据口径不一致时不得复用。
4. `unavailable` 和 `failed` 不提供推测性替代数据，只给出可执行的 `next_actions`。
5. 日志用于排错，不作为 evidence 或成功状态来源。

## Runtime configuration

读取环境配置的子 Skill CLI 必须在自身进程启动时自行加载 Skill 根目录 `.env`，不能依赖预检或上一个 CLI 进程传递环境变量。调用方无需生成包装脚本或手工导出配置；操作系统中已存在的环境变量优先于 `.env`。

## Retrieval record

`read-pdf` 的结果信封在 `summary` 中登记：

```json
{
  "retrieval_mode": "rag|direct|direct-fallback",
  "index_artifact": "data/vector_db|null",
  "queries_executed": 0
}
```

- `rag`：已登记兼容索引，并通过 `query_report.py` 生成 evidence。
- `direct`：任务仅要求精确页码、精确字段或精确原文，直接读取原始 artifact。
- `direct-fallback`：RAG 构建或查询失败后的受限直读；必须保留错误，结果最多为 `partial`。

五步法、完整研报或跨章节分析只有在 `retrieval_mode=rag`、`index_artifact` 非空且 `queries_executed > 0` 时，信息差才可为 `available`。

## Workspace isolation & Immutability

1. **源码只读**：`skills/`、`common/`、`runtime/`、`scripts/` 目录严禁写操作，禁止创建临时脚本或修改现有代码。
2. **工作区隔离**：所有 artifacts、中间数据与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。
3. **状态契约**：异常或缺失时直接在结果信封中返回对应状态与错误，严禁现场改代码。

## Safety

- 不读取或输出 `.env`、API Key、凭据和访问令牌。
- 不将其他公司、其他期间或过期行情冒充目标数据。
- 不引用不可交付的临时绝对路径作为唯一来源。
- CLI 参数和示例以 [CLI 参数参考](../../docs/CLI_REFERENCE.md) 或脚本 `--help` 为准。
