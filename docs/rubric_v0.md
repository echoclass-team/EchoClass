# 答疑陪练评估 Rubric v0

> **状态**：v0 正式版（机读，A 端 EvaluatorAgent 直接消费）
> **版本号**：`v0`（对应 `data/rubrics/v0.json`）
> **作者**：C-Prod
> **关联 Issue**：#122 [W1][M3-0-Rubric] Rubric v0 JSON schema 与设计文档（C）
> **关联文档**：`docs/eval_rubric_draft.md`（v0.5 草案，含 3 个试评分样本）/ `docs/edu_kb_design.md` / `docs/edu_kb_theory_map.md`

---

## 0. 文档定位

本文档与 `data/rubrics/v0.json` 是一对：

- **`v0.json`** 是机读契约 — `EvaluatorAgent` 在 prompt 构造期 `json.load` 后注入到系统消息中，作为评分规则
- **本 `rubric_v0.md`** 是设计依据 — 解释每个维度为什么这样切分、为什么选这两条理论锚点、级别描述里那些"专有词汇"（Pekrun、Posner、Vygotsky 等）来自哪条 `data/edu_theories/<id>.json`

下游消费者：

- **A-Agent**：直接 `json.load(data/rubrics/v0.json)` 喂入 EvaluatorAgent prompt；`tests/test_evaluator.py::test_rubric_load` 验收
- **B-Full**：依据维度 id（`MR/KC/RR/TQ/SS`）渲染雷达图与评分卡片；`evidence_field_template` 决定证据回溯 UI
- **C-Prod**：v0 暴露问题后迭代到 v1（开新 issue `[M3-C-Rubric-v1]`）

---

## 1. 与 v0.5 草案的关系

| 文件 | 用途 | 颗粒度 |
|---|---|---|
| `docs/eval_rubric_draft.md` (v0.5) | M2 内部讨论 + LLM-Judge prompt 种子 | 5 维 × 4-5 子指标 × 5 级 anchor + 3 个试评分样本（766 行） |
| `data/rubrics/v0.json` (v0) | M3 EvaluatorAgent 硬依赖 | 5 维 × 5 级 anchor，**子指标合并到级别描述**，便于 LLM-Judge 单次输出结构化 JSON |
| `docs/rubric_v0.md` (本文档) | v0.json 的设计依据与理论锚点引用 | 5 维 × 设计动机 × 理论引用 |

> **不是降级，是收敛**：v0 在 v0.5 基础上做"机读化"——把维度内的多个子指标（如 MR-1 命中率 / MR-3 干预精准度）合并到 0-4 级的统一描述中，避免 LLM-Judge 一次输出 20+ 个分数引发可靠性问题。试评分阶段验证：5 维 × 5 级的颗粒度足够区分高低水平（详见 v0.5 第 6 节 3 个样本）。

---

## 2. 五维度概览

| 维度 id | 中文名 | 取数层 | 核心问题 | 理论锚点 |
|---|---|---|---|---|
| `MR` | 迷思破除 | L1+L2+L3 | 该破的迷思被有效破除了吗？ | Posner 概念改变 / Chi 迷思三类型 |
| `KC` | 重点覆盖 | L1+L2+L3 | 教学目标讲到位了吗？语言适配学段了吗？ | Vygotsky ZPD / Piaget 认知阶段 |
| `RR` | 解决率 | L1+L2 | 真懂还是虚假懂了？ | Bandura 自我效能 / Weiner 归因 |
| `TQ` | 师范生提问质量 | L3 | 是"问回去"还是"答下去"？ | Vygotsky ZPD（脚手架） |
| `SS` | 学生满意度 | L1+L2+L3 | 学生消化 + 情绪 + 动机三者俱全吗？ | Pekrun 学业情绪 / Deci-Ryan SDT |

> **取数层**：L1 = `QASession.summary()` 直接读；L2 = `dialog.history` 派生；L3 = LLM-Judge。详见 `docs/eval_rubric_draft.md` §2。

---

## 3. 维度详解 · 设计依据

### 3.1 MR · 迷思破除（Misconception Resolution）

**为什么独立成维**：1v1 答疑陪练区别于普通对话练习的核心价值，就是练师范生**识别并破除学生错误前概念**的能力。EchoClass 的虚拟学生人设里专门设计了 `misconception_tendencies` 字段，本维度直接评估这一能力是否被激活。

**理论锚点**：

| 理论 | 文件 | 操作化用途 |
|---|---|---|
| **Posner 概念改变 4 步模型** | `data/edu_theories/posner_conceptual_change.json` | 提供"老师讲解正确答案 ≠ 学生放弃迷思"的根本判据。0 分锚点引用 trait `pre_accommodation` 中的 `"若老师只是讲解正确答案而不指出错误前提，会礼貌点头但内心仍然不信"`；4 分锚点要求满足"识别 + 反例 + 类比 + 复述变式"四件套，对应 trait `post_accommodation` 中"在变式题中能稳定使用新概念，不再回退"。 |
| **Chi 迷思三类型** | `data/edu_theories/chi_misconception_categories.json` | 提供"不同类型的迷思需要不同矫正策略"的颗粒度。在 LLM-Judge 输出 evidence 时，可标注被破除的迷思属于 belief revision / mental model / categorical shift 中的哪一类。 |

**为什么不用 Vygotsky**：迷思破除是"对错前提的诊断 + 矫正"，与 ZPD 的"难度匹配 + 支架"是不同的认知动作。Vygotsky 留给 KC 与 TQ。

### 3.2 KC · 重点覆盖（Key-points Coverage）

**为什么独立成维**：教学目标覆盖率是教研评估的传统主线指标，但 EchoClass 在覆盖率之上额外要求**语言适配学段**（小学不能讲"通分"、高中不能停在"差不多就行"），这是 1v1 陪练独有的训练点。

**理论锚点**：

| 理论 | 文件 | 操作化用途 |
|---|---|---|
| **Vygotsky ZPD** | `data/edu_theories/vygotsky_zpd.json` | 4 分锚点要求"每个难点都有学段适配的脚手架（具体例子 → 半抽象表征 → 形式表达）"，直接引用 trait `needs_high_scaffolding.operational_rules[2]`：`"若老师直接给抽象规则…通常听不懂；需要从具体例子切入"`。 |
| **Piaget 认知发展阶段** | `data/edu_theories/piaget_cognitive_stages.json` | 提供"学段红线"的理论基线：p_lower 学生处于具体运算期前期，不能用形式化代数；h 学生进入形式运算期，可使用抽象符号。0 分锚点的"语言明显跨学段"判据来自这里。 |

> ⚠️ 注：`piaget_cognitive_stages.json` 中 `applies_to.rubric=false`，但本维度的"学段语言适配"判据本质上需要 Piaget 学段边界。建议 v1 阶段把 Piaget 的 `applies_to.rubric` 改为 true（已在 `docs/edu_kb_theory_map.md` §1 中标注 `Piaget → KC`，与本维度对齐）。

### 3.3 RR · 解决率（Resolution Rate）

**为什么独立成维**：师范生最容易陷入的陷阱是**虚假高解决率**——学生说 [懂了] 老师就放过，看上去解决率很高，实际学生并未真懂。本维度通过 `self_resolve / teacher_marked / abandoned` 三类来源的**健康分布**来识别这种"伪解决"。

**理论锚点**：

| 理论 | 文件 | 操作化用途 |
|---|---|---|
| **Bandura 自我效能感** | `data/edu_theories/bandura_self_efficacy.json` | 4 分锚点要求"学生在 resolved 对话中表现出 Bandura 高自我效能信号（主动尝试新题）"——区分"老师讲完学生听明白"与"学生愿意自己上手做"。trait `low_self_efficacy.operational_rules` 给出低效能的 6 条可观察行为，作为 0 分锚点反例。 |
| **Weiner 归因理论** | `data/edu_theories/weiner_attribution.json` | 4 分锚点要求学生归因到"策略而非天赋"（适应性归因）。trait `maladaptive_ability_attribution` 描述"我太笨了"的不当归因——若学生在 resolved 末轮仍说"我天生不会"，则不能算高质量解决。 |

**为什么 self_resolve 是甜区指标而非越高越好**：Bandura 高自我效能的健康标志是"愿意自己确认 + 主动延伸"，但**过早的 [懂了]**（self_resolve > 90%）实际上是 Weiner 防御性归因的体现（"我快点说懂了避免继续被问"）。所以 RR 的 self_resolve 占比是一个 U 形曲线，甜区在 40-70%。

### 3.4 TQ · 师范生提问质量（Teacher Question Quality）

**为什么独立成维**：本维度全部 L3（LLM-Judge），评估师范生作为"操作者"的核心教学语言能力。这是与传统试卷无法考察的能力。

**理论锚点**：

| 理论 | 文件 | 操作化用途 |
|---|---|---|
| **Vygotsky ZPD（脚手架）** | `data/edu_theories/vygotsky_zpd.json` | 4 分锚点要求"对 needs_high_scaffolding 学生分子问题、needs_low_scaffolding 学生跳步点拨"——直接引用本理论的两个 trait 作为评分判据。0 分锚点的"对所有学生说一样的话"违反 trait 的核心 operational_rule"对一步到位的解释难以吸收，需要老师把问题拆成 2-3 个更小的子问题逐步引导"。 |

**为什么只挂一个理论**：TQ 是高度集中在"脚手架"这一行为类别的维度，单一理论锚点反而让评分更聚焦。LLM-Judge 在评分时，重点判断师范生的提问是否符合 Vygotsky `needs_high_scaffolding` / `needs_low_scaffolding` 的对应行为模式。

### 3.5 SS · 学生满意度（Student Satisfaction）

**为什么独立成维**：从虚拟学生视角看一节课的成败。学生消化（认知）+ 情绪（pekrun）+ 动机（deci-ryan）三件事缺一不可，单看认知会漏掉"老师讲懂了但把学生骂哭了"这类极端反例。

**理论锚点**：

| 理论 | 文件 | 操作化用途 |
|---|---|---|
| **Pekrun 学业情绪 CV 理论** | `data/edu_theories/pekrun_academic_emotions.json` | 提供学生末轮情绪标签（calm / enjoyment / neutral / frustrated / hopelessness）的标准类别，以及它们如何关联到 control-value 评估。0 分锚点要求"末轮情绪以 frustrated / hopelessness 为主"，4 分要求"calm + 主动总结"。 |
| **Deci-Ryan 自我决定理论** | `data/edu_theories/deci_ryan_sdt.json` | 评估老师对学生**自主性需求**（autonomy）的满足程度。4 分锚点引用"老师全程使用 Deci-Ryan 自主性支持语言（'你想试试用切蛋糕还是切披萨？'）"，0 分锚点的"老师用控制语气压制学生（'你听我说就行'）"违反自主性需求。 |

---

## 4. EvaluatorAgent 加载契约（A 端关键信息）

### 4.1 加载入口

```python
import json
from pathlib import Path

RUBRIC_PATH = Path(__file__).parent.parent / "data" / "rubrics" / "v0.json"

def load_rubric() -> dict:
    """加载 v0 rubric。失败立即报错（M3 EvaluatorAgent 的硬依赖）。"""
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
```

### 4.2 EvaluatorAgent 输出契约

LLM-Judge 必须按下列 JSON schema 输出（每节课调用一次）：

```jsonc
{
  "MR": {
    "score": 0|1|2|3|4,
    "evidence": {
      "dialog_id": "<DialogSession.id 或 null>",
      "chunk_seq": 5,                          // 对话第 6 条消息（0-indexed）
      "excerpt": "教师：你想到 0/0 时，是把它当算式还是过程？"
    }
  },
  "KC": { "score": ..., "evidence": {...} },
  "RR": { "score": ..., "evidence": {...} },
  "TQ": { "score": ..., "evidence": {...} },
  "SS": { "score": ..., "evidence": {...} },
  "improvement_hints": [
    "对薄弱生 X，下次建议先用 ... 类比",
    "迷思 Y 你识别到了但解释跳得快，可以用 ..."
  ]
}
```

约束：

- `score` 必须是 0–4 的整数，**不允许小数**；证据不足时填 `"N/A"` 而不是中庸 `2`
- `evidence.dialog_id` / `chunk_seq` / `excerpt` 三个字段必须齐全（占位结构来自 `evidence_field_template`），便于反馈页定位
- `improvement_hints` 至少 1 条，至多 5 条；指向具体可改进的提问技术

### 4.3 验收脚本（C 端提供 self-check）

```bash
cd backend
uv run python scripts/validate_rubric.py
```

输出示例：

```
✅ data/rubrics/v0.json    schema OK    dims=5 [MR/KC/RR/TQ/SS]
✅ theory_anchors all resolvable to data/edu_theories/*.json
```

A 端 `tests/test_evaluator.py::test_rubric_load` 应当至少包含：

```python
def test_rubric_load():
    rubric = load_rubric()
    assert rubric["id"] == "echoclass_rubric_v0"
    assert rubric["version"] == "v0"
    assert len(rubric["dimensions"]) == 5
    assert {d["id"] for d in rubric["dimensions"]} == {"MR", "KC", "RR", "TQ", "SS"}
    for dim in rubric["dimensions"]:
        assert set(dim["levels"].keys()) == {"0", "1", "2", "3", "4"}
        assert dim["theory_anchors"]
```

---

## 5. 已知局限与 v1 改进方向

| 局限 | 影响 | v1 计划 |
|---|---|---|
| 5 维度等权 | 实际"迷思破除"应权重更高 | v1 加入维度权重 + 用户测试反推合理值 |
| LLM-Judge 单次调用 | 长对话可能超 context | 实测验证；超长则按 dialog 分块评 |
| Piaget `applies_to.rubric=false` 但 KC 引用了它 | 数据契约不完全自洽 | v1 修正 Piaget 的 applies_to，或将 KC 锚点改为 Vygotsky 单挂 |
| 无"跑题转化"专项指标 | v0.5 草案样本 C 展示了重要能力但未独立打分 | v1 在 TQ 加 "topic_navigation" 子维度 |
| 缺少老师"自我反思"维度 | 当前只评对话 | M3 后期加入 self_reflection 阶段 + 评分 |

---

## 6. 与现有 issue / 文档的关系

- **#122**（本 issue）：交付 `data/rubrics/v0.json` + `docs/rubric_v0.md` + `backend/scripts/validate_rubric.py`
- **#73**：v0.5 草案（`docs/eval_rubric_draft.md`）的母 issue，3 个试评分样本可直接迁移到 M3 EvaluatorAgent 的回归数据
- **EduKB 第二期**：`docs/edu_kb_theory_map.md` §5 中规划的 Bloom + Hattie 第二期理论卡片落地后，v1 的 KC 与 TQ 维度可补加锚点

---

## 附录 A · 数据来源速查

| 字段 / 量 | 来源 | 类型 | 用于哪个维度 |
|---|---|---|---|
| `total_questions / resolved / abandoned / pending / active` | `QASession.summary()` | int | RR |
| `covered_key_points` | `QASession.summary()` | list[str] | KC |
| `broken_misconception_ids` | `QASession.summary()` | list[str] | MR |
| `resolution_sources` | `QASession.summary()` | dict[str,int] | RR / SS |
| `dialog.history[].role / .content / .self_resolved` | `DialogSession.messages` | obj | RR / TQ / SS |
| `dialog.question.category` | `StudentQuestion.category` | enum | KC / MR |
| `lesson.key_points / difficult_points` | `LessonMeta` | list[str] | KC |
| `match_misconceptions(...)` 输出 | `rag.misconceptions` | list[Misconception] | MR |
| `data/edu_theories/<id>.json` | EduKB 第一期 | obj | 所有维度的 `theory_anchors` |
