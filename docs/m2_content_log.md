# M2 内容联调记录（Issue #73）

> Owner: C-Prod (@IST00) — 与 A-Agent (@Nekooo915) 协同
> 状态：第一次实测完成，待 A 端 ``--debug-match`` 上线后补完触发率章节

## 0. 背景

Issue #73 验收要求：

> 与 A 一起跑 `try_qa_session.py` 至少 5 次（5 学段各一次），把 召回数 / 触发率 / 改进前后输出 记录到 `docs/m2_content_log.md`

由于 A 端 `scripts/try_qa_session.py --debug-match` 选项尚未上线（issue #73 内的小依赖），C 端**先独立完成召回率验证**，触发率章节预留待补。本文件实测数据由
`backend/scripts/check_misconception_recall.py`（本 PR 新增）一次性产出，可重复运行复现。

复现命令：

```bash
cd backend
uv run python scripts/check_misconception_recall.py
# 或机器可读版：
uv run python scripts/check_misconception_recall.py --json
```

---

## 1. 召回率验证（任务 1）

### 1.1 验收口径

| 指标 | 目标线 | 数据源 |
|---|---|---|
| 每节课命中迷思 | ≥ 3 条 | `rag.misconceptions.match_misconceptions(subject, stage_id, key_points, topic)` |
| 每学段平均命中 | ≥ 3 条/节 | 该学段全部 lesson_samples 平均 |

### 1.2 实测结果（2026-04-28，全 15 份教案）

```
文件                                     学段        学科     命中    达标
biology_j3_genetics.md                   j_upper    生物     4      ✅
chemistry_h1_redox.md                    h          化学    10      ✅
chinese_p1_pinyin.md                     p_lower    语文     3      ✅
chinese_p3_poetry.md                     p_middle   语文     0      ❌
chinese_p5_metaphor.md                   p_upper    语文     2      ❌
english_j1_present_tense.md              j_lower    英语    10      ✅
history_j2_opium_war.md                  j_lower    历史     5      ✅
history_j3_xinhai.md                     j_upper    历史     1      ❌
math_h2_derivative.md                    h          数学     8      ✅
math_j3_quadratic.md                     j_upper    数学     1      ❌
math_p2_addition.md                      p_lower    数学     1      ❌
math_p3_fraction.md                      p_middle   数学     4      ✅
math_p5_area.md                          p_upper    数学     2      ❌
physics_j2_force.md                      j_lower    物理     3      ✅
politics_h1_economy.md                   h          政治     3      ✅
```

### 1.3 每学段平均命中

| 学段 | N（节） | 平均命中 | 是否达标 ≥ 3 | 备注 |
|---|---|---|---|---|
| `h` | 3 | **7.00** | ✅ | 化学 / 数学 / 政治 学科迷思库密度高 |
| `j_lower` | 3 | **6.00** | ✅ | 英语 / 物理 / 历史 联动顺畅 |
| `j_upper` | 3 | 2.00 | ❌ | 数学单科有效命中弱 |
| `p_lower` | 2 | 2.00 | ❌ | 小学迷思库总量偏低（chi+math 共 19 条） |
| `p_middle` | 2 | 2.00 | ❌ | 小学语文 0 条 p_middle 迷思 |
| `p_upper` | 2 | 2.00 | ❌ | 小学迷思库 stage 偏置 p_upper 但命中弱 |

**总体平均**：3.80 条 / 份；**达标教案**：9 / 15。

### 1.4 失败案例归因（按降序）

#### A. 数据稀疏型（最严重）

- `chinese_p3_poetry.md` (p_middle, 0 hits)
  - **根因**：`data/misconceptions/chinese_primary.json` 当前 0 条 p_middle 迷思（4 条 p_upper + 本 PR 新增 3 条 p_lower）
  - **建议跟进**：M2 后期补 3-5 条 p_middle 语文迷思（古诗朗读 / 字词运用 / 写作习惯）

- `math_p2_addition.md` (p_lower, 1 hit)
  - **根因**：`math_primary.json` 中 p_lower 条目仅 4 条且重 piaget 守恒概念，与教案 key_points "数的合成 / 加号意义" 直接覆盖度低
  - **建议跟进**：补 2-3 条 p_lower 数学迷思（数感 / 加法策略）

#### B. key_points 词面不命中型

- `history_j3_xinhai.md` (j_upper, 1 hit) — meta `key_points` 含 "三民主义"，但召回脚本只命中 `history_modern_cn_04`；`洋务运动` 这个 secondary key 在 lesson 内是对照说明而非主题，未在 `key_points` 中出现
  - **建议跟进**：把 secondary key（如 "洋务运动 / 戊戌变法"）加进 `key_points` 即可补到 ≥ 2 命中（实测见 PR-B chinese_p1_pinyin 的扩 key_points 做法）

- `math_j3_quadratic.md` (j_upper, 1 hit)
  - **建议跟进**：把"对称轴 / 顶点公式 / 二次方程的根"等高频迷思关键词加进 key_points

- `chinese_p5_metaphor.md` (p_upper, 2 hits)
  - 已命中 2 条（修辞主题），距 ≥3 差 1 条，可补"标志词依赖" / "修辞误用"近义关键词

#### C. 设计性原因（非缺陷）

- 部分小学教案的 `key_points` 是**操作性目标**（如 "能借助注释和插图理解诗句意思"），与迷思库的**概念性条目**（如 "把'回'字理解为回家"）词面距离远，bigram overlap 给分低。建议:
  - 长期：在 meta.md 里**额外维护一组 `match_keywords`** 字段，专为召回设计，与 `key_points` 解耦
  - 短期：把高频迷思的关键名词手动并入 `key_points`

### 1.5 改进路线（M2 后期）

- [ ] **数据层**：补 ≥ 5 条 p_middle 语文迷思 + ≥ 3 条 p_lower 数学迷思（issue #73 范围外，可单开 issue）
- [ ] **匹配层**：扩 5 份失败教案的 `key_points`，让"匹配关键词"语义化（不影响 LLM 抽取目标，仅作召回用）
- [ ] **策略层**：评估是否在 `match_misconceptions` 引入 stage-邻近 fallback（如 p_middle 找不到时退到 p_upper）

### 1.6 改进前后对比示意

以 `history_j2_opium_war.md` 为例（本 PR 中已实操过这一改进）：

| 阶段 | key_points 设计 | hits |
|---|---|---|
| 初稿 | "鸦片战争爆发的原因 / 《南京条约》 / 半殖民地半封建" | 1 |
| 改进 | + "（英国工业革命扩张需求）" + "（半殖民地半封建社会）" | **3** |

**结论**：在不改动迷思库的前提下，仅微调 `key_points` 措辞使其包含迷思 `topic` 的高频关键词，就能从 1 → 3 hits。这是低成本的"匹配层"改进。

---

## 2. 触发率验证（任务 1，依赖 A 端）

### 2.1 验收口径

> 在 5 个学段 × 每学段 5 轮 1v1 对话样本中，至少 30% 的对话出现 `category=stuck_misconception` 的问题（即学生真的拿迷思在问）

### 2.2 现状

A 端的 `backend/scripts/try_qa_session.py` 当前**未实现 `--debug-match` 选项**（实测 `Select-String -Path try_qa_session.py -Pattern 'debug-match'` 无命中）。该选项需在每轮对话后打印：

- 当前学生 utterance 的迷思命中条数
- LLM 抽取出的 `category` 字段（特别是 `stuck_misconception`）
- 学生 persona / topic / 触发的迷思 id

### 2.3 待补

待 A 端补 `--debug-match` 后，本节将填入：

| 学段 | persona | 课题 | 5 轮中触发 stuck_misconception 的轮数 | 触发率 |
|---|---|---|---|---|
| `p_lower` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |
| `p_middle` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |
| `p_upper` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |
| `j_lower` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |
| `j_upper` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |
| `h` | _待跑_ | _待跑_ | _待跑_ / 5 | _待跑_ |

期望：≥ 30% 的对话出现 `category=stuck_misconception`。

### 2.4 协调建议

- C 端已在 PR-A `feat/c-prod-qa-examples-v3` 中给每学段 ask_examples 加入显式 `[懂了]` 反思场景，理论上能拉高 LLM 抽取出 `stuck_misconception` 的概率（few-shot 示例引导）
- A 端需提供 `--debug-match` + （可选）`--export-jsonl` 把每轮 debug 信息持久化，方便 C 端事后统计

---

## 3. 跟进 / Open Items

| ID | 内容 | Owner | 优先级 |
|---|---|---|---|
| FU-1 | A 端补 `try_qa_session.py --debug-match` | A-Agent | P0（issue #73 验收依赖） |
| FU-2 | 补 ≥ 5 条 p_middle 语文迷思 / ≥ 3 条 p_lower 数学迷思 | C-Prod | P1 |
| FU-3 | 扩 5 份失败教案 key_points 提升召回（详见 1.4） | C-Prod | P1 |
| FU-4 | 在 meta.md 引入独立 `match_keywords` 字段（设计层改进） | C-Prod 提议 + A-Agent 实现 | P2 |
| FU-5 | 评估 `match_misconceptions` stage-邻近 fallback 策略 | A-Agent | P2 |

---

## 附录 A：完整 JSON 实测数据

可通过下列命令产出（覆盖本文件 1.2/1.3）:

```bash
cd backend
uv run python scripts/check_misconception_recall.py --json > ../docs/m2_recall_snapshot.json
```

执行时间：每次约 2 秒（不依赖 LLM / 网络）。可纳入 CI smoke 检查。
