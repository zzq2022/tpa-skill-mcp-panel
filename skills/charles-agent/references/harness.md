# Harness 视角

本 Skill 不只是一段静态提示词，而是一个以投研为核心的小型 Harness 状态机。它系统性回答以下六个核心问题：

| Harness 维度 | Charles 解决的投研问题 | 工程设计手段 |
|---|---|---|
| **1. 上下文管理** | 模型在各阶段到底看到了什么 | 阶段化加载 `references/` 与子 `SKILL.md`，避免上下文蔓延与注意力稀释 |
| **2. 工具系统** | 怎么处理多源投研输入/输出 | 财报 PDF / CSV / 行情 / 新闻 / 统一 JSON 信封与 Markdown 研报 |
| **3. 执行编排** | 复杂的五步法下一步该做什么 | Phase 0~8 状态机、Phase 3 Checkpoint 1 硬门禁、Step 1~5 契约驱动 |
| **4. 状态与长期记忆** | 跨阶段决策与数据如何保持 | `source/source.md`、`plan/plan.md`、`data/`、`analysis/`、`review/` 物理落盘 |
| **5. 评估与门禁** | 如何知道各步产物是否合格 | Phase 2 内联自查；Phase 4~7 文件依赖与信封校验；Phase 8 终审质检 |
| **6. 约束与降级** | 数据缺失或受限时如何处理 | 契约信封返回 `partial` / `unavailable` 并记录缺口，禁止伪造数据 |

---

## 状态文件是长期记忆

Agent 在长会话中**不得仅依赖聊天上下文记忆关键决策**。所有跨阶段决策与中间数据必须落盘至任务工作区：

```text
workspaces/<task_id>/
├── source/                          # Phase 1: 标的证券/公司元数据或源文件底座
│   └── source.md
├── plan/                            # Phase 2: 规划文件（Brief/Scope/Outline/Artifacts 四段合一）
│   └── plan.md
├── data/                            # Phase 4: Step 1 数据采集层（由 read-pdf / sentiment 原生生成）
│   ├── financial_data/              # 结构化财务报表 CSV (由 fetch_financial_data.py 输出)
│   ├── financial_reports/           # 财报 PDF 原件 (由 fetch_financial_data.py 输出)
│   ├── parsed/                      # 财报解析文本 (由 parse_pdf_basic.py 输出)
│   ├── vector_db/                   # FAISS 向量库 (由 build_index.py 输出)
│   └── news/                        # 新闻 JSON (由 news_fetcher.py 输出)
├── analysis/                        # Phase 5~7: 中间分析层
│   ├── logic_chain.md               # Step 2 因果链推理
│   ├── <stock>_ratio.json           # Step 3 财务比率分析 (由 ratio_analysis.py 输出)
│   ├── <stock>_peer.json            # Step 3 同业对比分析 (由 peer_compare.py 输出)
│   └── <stock>_sentiment.json       # Step 4 情绪与事件 (由 sentiment_scorer.py 输出)
├── review/                          # Phase 8: 质检层
│   └── final-review.md              # 终审质检报告
└── output/                          # Phase 8: 交付层（由 write-report 原生生成）
    ├── <stock>_analysis.json        # five_step_analysis.py 汇总信封
    └── reports/
        └── <stock>_投资研究报告.md    # report_generator.py 最终研报
```

> **回读铁律**：每进入一个新 Phase，若需要前序阶段结论，必须先**回读对应的状态文件**，严禁凭记忆重新臆测。
