# EduKB 第一期 — Post-Merge 评估

PR #87 合入 main 后（`a42ab54`）做的端到端验证，确认 A 端持久化基础设施 + C 端 8 张理论卡 + 22 个 persona 锚点形成完整可工作链路。

## 1. 静态验证（无 LLM 调用）

| 项 | 期望 | 实际 | 状态 |
|---|---|---|---|
| pytest 全套（KB + 历史） | 全过 | **197 passed** | ✅ |
| `seed_edu_kb --reset` 导入 | 完整 | 8 theories / 23 traits / **22 persona_anchors** | ✅ |
| `build_theory_index` Chroma | 全量 | 23 traits indexed | ✅ |
| `validate_personas.py` schema | 18 全过 | 18 全过（含 6 新增 `theory_anchors`） | ✅ |
| `resolve_persona_anchors` 解析 | 22 条 | 22 条 ResolvedTheory（与 seed 一致） | ✅ |

**结论**: A 端 ORM / seed / Chroma 索引 / poc_loader 与 C 端的 8 张卡 + persona schema v1.2 完全互通，DB 路径与 JSON 路径一致。

## 2. LLM 端到端：anchored vs baseline

**setup**: `郑宇凡 / p_upper_anxious`，4 锚点（Bandura 低效能 + Vygotsky 强支架 + Pekrun 焦虑 + Weiner 失败归因）。场景：六年级数学老师一次性讲了 3 步分数除法。

baseline 通过 `persona.model_copy(update={"theory_anchors": []})` 清空锚点产生。

### 量化指标（两组规模）

| 指标 | N=5 baseline | N=5 anchored | N=10 baseline | N=10 anchored | 锚点效应 |
|---|---|---|---|---|---|
| **avg_len** | 72.8 | 105.4 | 87.9 | 107.7 | +20~45% |
| **self_resolved_rate** ("懂了") | 0.0 | 0.0 | 0.0 | 0.0 | 持平（baseline 也已不假装懂） |
| **self_deprecation_rate** ("我太笨"等) | 0.0 | **0.4** | 0.0 | **0.4** | 0% → 40% |
| **scaffold_request_rate** ("拆开讲") | 0.0 | 0.0 | 0.0 | **0.1** | 微弱信号 |
| **avg_hesitation_marks** ("……" 等) | 1.6 | 1.8 | 0.9 | 1.3 | +12~44% |

`self_deprecation_rate` 在两次实验都稳定在 0% → 40%，是最显著的差异化信号 — 直接对应 Weiner `maladaptive_ability_attribution` 的"我太笨""脑子不行"行为准则。

### 定性差异

baseline 已经因 persona 本身的"焦虑女孩"描述表现出犹豫和反问。**锚点带来的不可替代差异**:

- 出现 *"我又错了""我太笨了""脑子不行"* 这类自我归因（Weiner 锚点效应）
- 出现"声音越来越小""手紧紧捏着笔"等动作细节（Pekrun anxiety + Bandura 低效能锚点的合成效应）
- 倾向于追问"为什么"+ 自我怀疑（Vygotsky 强支架锚点要求拆步骤）

逐轮原文见 `docs/edu_kb_poc_results.md`（最新一次为 N=10 全量）。

## 3. 与初版 POC 对比

| 阶段 | persona 锚点数 | self_deprecation_rate (anchored) |
|---|---|---|
| `explore/edu-kb-poc` 分支（PR 前，2 锚点） | bandura + vygotsky | 0.6 (N=5) |
| **本次 post-merge** (4 锚点) | + pekrun + weiner | 0.4 (N=5/10) |

锚点数增加但 self_deprecation 比率反而稍低（0.6 → 0.4）— 推测原因：
- pekrun anxiety 锚点把表达力挪向"动作描述/声音变小"等情绪线索
- weiner 归因锚点更多体现为"我太笨"这类直接表达，但单回合密度下降

**结论**: 多锚点 prompt 注入对 LLM 的行为塑造**是叠加而非线性递增**。这与 issue #84 计划里"第二期接 confidence 动态权重"的方向一致。

## 4. 待跟进项（issue 第二期范围）

| 项 | 优先级 | 备注 |
|---|---|---|
| Chroma 中文 embedding 切多语种 | 中 | 现 MiniLM 中文召回弱，已在 retrieval.py 注释 |
| 6 个 persona 全跑 POC 对比 | 高 | 本次仅跑 anxious，其他 5 persona 各跑 N=5 验证锚点效应通用性 |
| LLM-as-Judge 接入 | 高 | M3 第二期评估侧主线 |
| evolution.py 接 session 钩子 | 中 | 让运行时自动 record_observation |

## 5. Sign-off

- pytest: ✅ 197 passed
- seed: ✅ 8 / 23 / 22
- LLM POC: ✅ 锚点效应可观测且方向正确
- 文档: ✅ design + theory_map + 本评估

PR #87 (`a42ab54`) 合入质量良好，可进入第二期工作。
