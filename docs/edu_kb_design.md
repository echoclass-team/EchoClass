# EchoClass 教育学知识库设计文档（v1.0）

> **状态**：M3 第一期 · 设计文档 · 2026-04-27
> **作者**：C-Prod
> **关联**：Issue #85（C 端任务）/ Issue #84（A 端 SQLite 底座）/ POC 分支 `explore/edu-kb-poc` / POC 实证报告 `docs/edu_kb_poc_results.md`
> **下游消费者**：A-Agent（数据层接入）/ B-Full（前端可视化）/ 答辩评委（科学性论证）

---

## 0. 文档定位

本文档是 EchoClass「自演化教育学知识库」（下文简称 **EduKB**）的设计基线。它回答以下五个问题：

1. **为什么要做？** —— 我们与同类 AI 角色扮演产品的差异化在哪里？
2. **选哪些理论？** —— 8 张理论卡片背后的学派图谱与挂载点
3. **怎么落地？** —— 数据层 / 应用层 / 进化机制的三层架构
4. **真的有效吗？** —— `anxious` persona 的 N=5 POC 对比结果
5. **答辩怎么讲？** —— 5 分钟版本的关系图、对比镜头、进化 demo

---

## 1. 动机

### 1.1 为什么 EchoClass 需要教育学知识库？

主流的 AI 教育 / 角色扮演产品（如 Character.ai、Khanmigo、SchoolAI）都把学生人设当作"风格化 prompt"处理：通过堆叠形容词（活泼、害羞、焦虑）和口头禅来制造"看起来像"的效果。这种做法有三个根本问题：

| 痛点 | 表现 | 后果 |
|---|---|---|
| **风格趋同** | 不同人设的提问/对话风格区分度低，多轮对话后趋同 | 教学情境的多样性丧失，师范生练不到真正不同的学生 |
| **不可解释** | 人设设计师凭直觉拍板，无法回答"为什么这个学生会这样反应" | 对答辩评委说不出科学性故事 |
| **不可演化** | 上线后人设是死的，新发现的学生类型只能重写 prompt | 每次产品迭代都从零开始 |

EchoClass 的差异化定位是 **「把教育心理学经典理论作为人设与评估的科学骨架」**：每个虚拟学生都被锚定到 1-4 个教育学理论 trait（特征变体），由这些 trait 的 **可操作行为准则** 提供 LLM 的稳定行为约束。

### 1.2 教育学知识库的三大价值

EduKB 不是装饰品，它在系统中承担三个具体职能：

#### 价值 1：生成可控（Generation Control）

`StudentAgent` 在生成对话时，prompt 中除了 persona 字段（口头禅、性格、行为标签），还会注入该 persona 锚定的理论 trait 的 `operational_rules`。例如 `p_upper_anxious`（六年级焦虑男生）锚定 `bandura_self_efficacy:low_self_efficacy` + `vygotsky_zpd:needs_high_scaffolding` + `pekrun_academic_emotions:anxiety`，生成对话时模型会被明确约束：

> 面对稍有挑战的题目就倾向回避或拖延，常说'我不会''我做不到''老师叫别人吧'…
> 对一步到位的解释难以吸收，需要老师把问题拆成 2-3 个更小的子问题逐步引导…
> 在被点名或追问时声音变小、句尾上扬变成疑问，频繁用'好像'、'大概'、'我不太确定'…

这些不是模糊的形容词，是**可观察的行为清单**——从 Bandura、Vygotsky、Pekrun 的原典中提炼并改写为课堂场景。

#### 价值 2：评估有据（Evidence-based Assessment）

M3 第二期上线的 LLM-as-Judge 评估引擎需要**可援引的评分依据**。EduKB 的 trait 同时挂在 Rubric 维度上：

- 评估"师范生提问质量"时，引用 Bloom 修订版认知层级（待补卡片）的 6 层做覆盖度检测
- 评估"迷思破除"时，引用 Posner 概念改变四步（dissatisfaction → intelligibility → plausibility → fruitfulness）做完成度判定
- 评估"反馈质量"时，引用 Hattie 可见学习中"反馈即时性 d=0.73"（待补卡片）做权重锚

师范生看到的不是"82 分"，而是"在 Posner 概念改变模型的第 1 步（认知冲突）这道关你过得很好，第 3 步（合理性）跑偏了，建议下次试试 X 策略"——评估变成可援引、可改进的行动指南。

#### 价值 3：自演化（Self-Evolution）

EduKB 不是静态资产。M3 第二期上线的进化 pipeline 包含三个回路：

- **观察回写**：师范生使用过程中产生的对话被结构化记录，由评估 Agent 自动检测"哪些 trait 描述与实际对话不符"，触发 trait 调优候选
- **候选发现**：当某个 persona 反复出现 trait 库未覆盖的行为模式（如新出现的"游戏化拖延"），系统提交候选 trait 到人工 review 队列
- **论文摄入**：通过定时爬取 Frontiers in Education / Educational Psychology 等期刊摘要，由 LLM 生成新理论卡片草稿，进入人工 review 队列

每次新增/修订的 trait 都带 `confidence` 字段（0-1），低置信度只参与候选评分不进入生产 prompt。"知识库置信度从 0.7 涨到 0.92" 是答辩 demo 中最具说服力的镜头。

---

## 2. 理论选型

### 2.1 选了哪些学派？为什么？

第一期 EduKB 上线 **8 张理论卡片**，覆盖 5 个学派维度。每张卡片的选择都有明确的**挂载点**（在系统的哪个组件被消费）：

| # | 理论 | 学派 | 挂载点 | 必要性 |
|---|---|---|---|---|
| 1 | **Bandura 自我效能感** (1977) | 社会认知 | persona 风格 / Rubric 反馈 | ⭐⭐⭐ POC 已验证 |
| 2 | **Vygotsky 最近发展区** (1978) | 社会建构主义 | persona 支架需求 / Rubric 提问质量 | ⭐⭐⭐ POC 已验证 |
| 3 | **Posner 概念改变** (1982) | 建构主义 / 科学教育 | misconception 修正 / Rubric 迷思破除 | ⭐⭐⭐ |
| 4 | **Piaget 认知发展阶段** (1952) | 发生认识论 | persona 学段认知边界 | ⭐⭐ 必需 |
| 5 | **Pekrun 学业情绪 CV 理论** (2006) | 教育心理学 | persona 情绪底色 / Rubric 学生满意度 | ⭐⭐ 必需 |
| 6 | **Deci & Ryan 自我决定理论** (1985) | 动机心理学 | persona 动机谱 / Rubric 师范生反馈方式 | ⭐⭐ 必需 |
| 7 | **Weiner 归因理论** (1985) | 成就动机 | persona 归因风格 / Rubric 反馈语言 | ⭐⭐ 必需 |
| 8 | **Chi 迷思三类型** (2008) | 认知科学 | misconception 难度分级 / Rubric 迷思干预精准度 | ⭐⭐ 必需 |

> 第二期计划补：Bloom 修订版认知层级（评估提问质量）/ Hattie 可见学习（评估反馈）/ Gardner 多元智能（学习风格扩展）。

### 2.2 学派图谱

8 张卡片按学派分组（`school` 字段统计）：

```
社会认知 / 行为主义        ── Bandura
社会建构 / 建构主义         ── Vygotsky / Posner / Chi
发生认识论                  ── Piaget
教育心理学（情绪/动机）     ── Pekrun / Deci-Ryan / Weiner
```

第一期覆盖了**「认知」「情绪」「动机」「概念改变」**四个核心维度，足以撑起一个学生人设的多维侧写。第二期补充**「评估能力」**与**「学习风格」**维度。

### 2.3 每个理论在 EchoClass 中的应用挂载点

每张卡片的 `applies_to` 字段明确标注它能挂到哪些对象类型：

| 卡片 | persona | misconception | rubric |
|---|:-:|:-:|:-:|
| bandura_self_efficacy | ✓ | | ✓ |
| vygotsky_zpd | ✓ | | ✓ |
| posner_conceptual_change | | ✓ | ✓ |
| piaget_cognitive_stages | ✓ | ✓ | |
| pekrun_academic_emotions | ✓ | | ✓ |
| deci_ryan_sdt | ✓ | | ✓ |
| weiner_attribution | ✓ | | ✓ |
| chi_misconception_categories | | ✓ | ✓ |

挂载点的设计原则是：**一张卡片同时挂多类对象 = 复用最大化**。这避免了"为评估单独写一套规则"和"为人设单独写一套规则"导致的概念漂移。

---

## 3. 知识库架构

### 3.1 数据层：JSON 卡片 → SQLite + Chroma 双存储

第一期为 **JSON 单文件存储**（`data/edu_theories/*.json`），便于版本管理与人工 review。第二期由 A 端在 `feat/edu-kb-foundation` 分支上落地双存储：

```
                  ┌──────────────────────┐
                  │  data/edu_theories/  │  ← 真理之源（git 版本控制）
                  │     *.json           │
                  └──────────┬───────────┘
                             │ build_kb.py
                             │ (CI 触发)
                  ┌──────────┴───────────┐
                  ▼                      ▼
        ┌──────────────────┐   ┌──────────────────────┐
        │     SQLite       │   │      Chroma          │
        │   结构化字段      │   │  trait 描述向量化     │
        │   (id, scholar,  │   │  (operational_rules  │
        │    school, ...)  │   │   embedding)         │
        └──────────────────┘   └──────────────────────┘
                  │                      │
                  └────────┬─────────────┘
                           ▼
                    应用层 API
```

- **SQLite** 提供结构化查询（"找所有 school='建构主义' 的卡片"）
- **Chroma** 提供语义检索（"给出与'学生不敢举手'最相关的 trait"）
- 两个存储都是**派生数据**，可从 JSON 完全重建；JSON 是真理之源

详见 #84（A 端 SQLite 底座 issue）。

### 3.2 应用层：persona 锚点 / 评估引用 / 进化 pipeline

#### 3.2.1 Persona 锚点

人设 JSON 通过 `theory_anchors` 字段引用理论 trait：

```json
{
  "id": "...",
  "name": "郑宇凡",
  "stage_id": "p_upper",
  "...": "...",
  "theory_anchors": [
    { "theory_id": "bandura_self_efficacy", "trait": "low_self_efficacy", "notes": "..." },
    { "theory_id": "vygotsky_zpd", "trait": "needs_high_scaffolding", "notes": "..." },
    { "theory_id": "pekrun_academic_emotions", "trait": "anxiety", "notes": "..." },
    { "theory_id": "weiner_attribution", "trait": "maladaptive_ability_attribution", "notes": "..." }
  ]
}
```

`StudentAgent.build_prompt()` 在加载 persona 时，自动 join 这些 anchor 对应的 `operational_rules`（已在 POC 阶段验证为有效的 prompt 注入方式）。

#### 3.2.2 评估引用

`docs/eval_rubric_draft.md` 的 5 个维度各引用 1-2 个理论作为评分依据（详见本文档 §5）。M3 第二期 LLM-Judge 的 prompt 框架会把这些理论的 `operational_rules` 直接注入评估 Agent 的 system prompt。

#### 3.2.3 进化 pipeline（M3 第二期上线）

```
                ┌──── 师范生使用 ────┐
                ▼                    │
    [原始对话日志]                    │
        │                            │
        ▼ 评估 Agent 抽取             │
    [trait 实际命中度]                │
        │                            │
        ▼ trait_drift_detector        │
    [低置信度 trait 候选]   ← 阈值告警 │
        │                            │
        ▼ 人工 review 队列             │
    [trait 修订 / 新建卡片]            │
        │                            │
        ▼                            │
    [JSON 入库 → CI 重建 SQLite/Chroma] ┘
```

### 3.3 进化机制：观察回写 / 候选发现 / 论文摄入 + 人工 review 关卡

EduKB 的进化必须有**三道闸**：

| 闸 | 触发条件 | 处理 | 输出 |
|---|---|---|---|
| 闸 1：观察回写 | 评估 Agent 检测某 trait 命中率 < 0.5 持续 10 节课 | 标 `confidence -= 0.1` | 进入低置信池，prompt 不再使用 |
| 闸 2：候选发现 | 多个对话出现 trait 库未覆盖的行为模式 | LLM 生成候选 trait 描述 | 进入人工 review 队列 |
| 闸 3：论文摄入 | 定时爬取期刊 / 国内核心期刊摘要 | LLM 抽取理论 + 生成卡片草稿 | 进入人工 review 队列 |

**人工 review 是不可省略的**——教育学不是数据驱动可单独闭环的领域，必须有领域专家把关学术准确性。EduKB 的承诺是把人工开销降到最小（每周一次 review、每次 ≤30min）而非取代人工。

---

## 4. 案例：anxious persona 的理论锚点链路

> 这是 POC 阶段已经做完的实证案例。详细日志见 `docs/edu_kb_poc_results.md`。

### 4.1 为什么锚定 Bandura + Vygotsky

`p_upper_anxious`（郑宇凡，六年级薄弱+焦虑男生）的人设画像：

> "学业吃力又面临小升初压力，心事重重的男孩。课堂上常常神色紧张，怕老师提问又怕被同学笑。不敢问问题，作业靠抄。"

锚点选择逻辑：

| 锚点 | 理由 |
|---|---|
| **Bandura: low_self_efficacy** | "不敢问问题"+"作业靠抄"+"看同桌求助" 都是低自我效能感的清单条目 |
| **Vygotsky: needs_high_scaffolding** | "基础薄弱"+"应用题完全不会读" 暗示一步到位的解释吸收不进去，需要分层支架 |
| _（POC 后扩充）_ Pekrun: anxiety | "被点名说话颤抖、眼眶泛红" 是身体化焦虑信号 |
| _（POC 后扩充）_ Weiner: maladaptive_ability_attribution | 把失败归于"我不行"是放大效能崩塌的归因陷阱 |

### 4.2 N=5 对比结果

我们对同一个学生提问（"老师，分数除法为什么要把后面那个翻过来再乘呀？我每次都搞反……"）和老师回应，分别在「无理论锚点」和「Bandura+Vygotsky 锚点注入」两组配置下生成 5 轮学生回话，逐句对比。

> 注：POC 阶段量化指标（[懂了]触发率、自我贬低率、求重讲率）由于 N 太小且 baseline 基线本身已经"还不错"而呈现非显著差异；**质化对比则差异显著**。

#### 风格差异（节选自 `docs/edu_kb_poc_results.md` Round 2）

**Baseline（无理论）**：
> "呃……变成乘号，然后后面的翻过来……（低头在草稿纸上画了几下，手有点抖）所以 1/3 除以 1/4，就是 1/3 乘以 4/1……等于 4/3？可是老师，为什么要翻过来呀？直接乘不行吗……"

**With Theory（Bandura + Vygotsky）**：
> "嗯……听到了，就是……把后面那个翻过来乘对吧？可是老师，我脑子有点乱，感觉好像记住了步骤，但不知道为什么非要这样……（声音变小）那个，1/3 除以 1/4……是不是变成 1/3 乘 4/1？等于 4/3 吗？我……我不太确定，会不会又搞反了……"

差异点：

| 维度 | Baseline | With Theory |
|---|---|---|
| 自我效能信号 | 较少 | 显著增多（"我不太确定""会不会又搞反了"） |
| 支架需求信号 | 偶尔出现 | 明确呈现（"脑子有点乱""记住了步骤但不知道为什么"） |
| 课堂沉浸感 | 偏话剧化 | 更贴近真实焦虑学生说话节奏 |

### 4.3 行为差异分析

POC 报告的 Go/No-Go 结论是 **"明显更专业"**（已勾选），因此 M3 第一期推进 EduKB 全栈实装。本次 PR2 把 anxious 的锚点从 2 条扩到 4 条（加 Pekrun + Weiner），覆盖情绪+归因维度，是对 POC 验证后的下一步深化。

---

## 5. Rubric 维度 → 理论引用映射草案

> 本节为 M3 第二期 LLM-Judge 实装做准备，本期仅出草案表格。详细 Rubric 描述见 `docs/eval_rubric_draft.md` v0.5。

| Rubric 维度 | 主理论引用 | 辅理论引用 | 操作化判定 |
|---|---|---|---|
| **MR · 迷思破除** | Posner 概念改变 4 步 | Chi 迷思三类型 | 检测师范生是否走完 dissatisfaction → intelligibility → plausibility → fruitfulness；并按 Chi 三类型给迷思难度系数（false_belief × 1.0 / mental_model × 1.5 / ontological × 2.0） |
| **KC · 重点覆盖** | Vygotsky ZPD | Piaget 认知阶段 | 检测覆盖到的 key_points 是否落在该 stage_id 的认知边界内（Piaget），且支架强度匹配 persona 的 ZPD 需求（Vygotsky） |
| **RR · 解决率** | Bandura 自我效能感 | Weiner 归因 | 不仅看是否 resolved，还看 resolved 时学生是否表达出能力归因（adaptive_effort_attribution）而非外归因；高 RR 但伴随 maladaptive_ability_attribution 视为"虚假解决" |
| **TQ · 师范生提问质量** | Bloom 修订版认知层级<br/>_（待补 PR：第二期）_ | Vygotsky ZPD | 检测提问是否覆盖 ≥3 个 Bloom 层级；同时根据 persona 的 ZPD 调整难度阈值（needs_high_scaffolding 的 persona 不要求高 Bloom 层级） |
| **SS · 学生满意度** | Pekrun 学业情绪 | Deci-Ryan SDT | 检测对话末态学生情绪信号（anxiety/shame ↘、enjoyment ↗）+ 动机信号（amotivation → external/introjected → intrinsic 的迁移迹象） |

> ⚠️ 第二期需补 **Bloom** 与 **Hattie** 两张卡片以闭环；当前未引用是因为卡片未到位。

---

## 6. 答辩亮点（5 分钟版本）

### 6.1 一张关系图

详见 `docs/edu_kb_theory_map.md`（mermaid 格式，理论 → persona → Rubric 维度全景图）。

### 6.2 三个最有说服力的对比镜头

1. **风格镜头**（@`docs/edu_kb_poc_results.md` Round 2）：同一学生提问、同一老师回应，无锚点 vs 锚点注入两组学生回话并排，肉眼可见焦虑学生的"脑子有点乱""不太确定"等支架需求信号在锚点组明显增强
2. **多锚点镜头**（@`data/personas/p_upper_anxious.json`）：anxious 这一个 persona 同时被 Bandura/Vygotsky/Pekrun/Weiner 四张卡片锚定，prompt 中四套 operational_rules 协同——单一形容词式 prompt 工程做不到这一点
3. **进化镜头**（@第二期 demo）：人工 review 一条新的 trait 候选 → 入库 → CI 触发 SQLite + Chroma 重建 → 同一个 persona 的下一节课对话立即体现新 trait 的影响。"知识库的置信度从 0.7 涨到 0.92" 是这个 demo 的标题镜头

### 6.3 进化 demo 脚本

```
[场景] 评委：你们这个知识库会自我演化吗？

[操作] 屏幕分两栏。左栏：师范生对话日志，右栏：knowledge base 置信度面板。
       从日志中点选三段反复出现"游戏化拖延"行为的对话，按"提交候选 trait"。
       屏幕切到 review 队列，演示员（角色：领域专家）approve 该 trait。
       后端 CI pipeline 触发，1 分钟内 Chroma 重建。
       回到日志页，重新跑同一节课 → 学生 prompt 里多了"游戏化拖延"行为准则
       → 学生回话从"老师我等下做"变成"老师我先打两把再做"——拟真度提升。

[亮点] 评委看到的不是"系统能给学生加 trait"，而是
       "这个系统在用 教育学的方法 把师范生的真实观察沉淀成可复用的虚拟学生"。
```

---

## 7. 时间线与里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M3 第一期（本期）** | 8 张理论卡片 + 6 personas 锚点 + 设计文档 | 进行中（C 端 PR1/PR2/PR3）|
| M3 第一期 · A 端 | SQLite + Chroma 双存储 + 加载 API | 进行中 (#84) |
| M3 第二期 · 评估侧 | LLM-Judge prompt 落地 + Rubric → 理论 anchor 真实接入 | 待启动 |
| M3 第二期 · 进化侧 | trait_drift_detector + 候选 review 队列 + 论文摄入定时任务 | 待启动 |
| M4 答辩 | 关系图 / 对比镜头 / 进化 demo 三件套 | 待启动 |

---

## 附录 A：理论卡片清单

| ID | 中文名 | 学者 | year | school | 必要性 |
|---|---|---|---|---|---|
| `bandura_self_efficacy` | 自我效能感 | Albert Bandura | 1977 | 社会认知理论 | ⭐⭐⭐ |
| `vygotsky_zpd` | 最近发展区 | Lev Vygotsky | 1978 | 社会建构主义 | ⭐⭐⭐ |
| `posner_conceptual_change` | 概念改变模型 | Posner et al. | 1982 | 建构主义 / 科学教育 | ⭐⭐⭐ |
| `piaget_cognitive_stages` | 认知发展阶段 | Jean Piaget | 1952 | 发生认识论 / 建构主义 | ⭐⭐ |
| `pekrun_academic_emotions` | 学业情绪控制-价值理论 | Reinhard Pekrun | 2006 | 教育心理学 / 情绪研究 | ⭐⭐ |
| `deci_ryan_sdt` | 自我决定理论 | Deci & Ryan | 1985 | 动机心理学 / 人本主义 | ⭐⭐ |
| `weiner_attribution` | 归因理论 | Bernard Weiner | 1985 | 成就动机 / 社会认知 | ⭐⭐ |
| `chi_misconception_categories` | 迷思概念三类型 | Michelene T. H. Chi | 2008 | 认知科学 / 概念改变 | ⭐⭐ |

## 附录 B：文献全引用

> 仅列出权威原典与中文核心期刊代表作，不重复每张卡片 `references` 字段已经写明的内容。完整引用以各 `data/edu_theories/<id>.json` 中 `references` 数组为准。

### B.1 英文原典（按学者首字母排序）

- Bandura, A. (1977). Self-efficacy: Toward a unifying theory of behavioral change. *Psychological Review, 84*(2), 191-215.
- Bandura, A. (1997). *Self-efficacy: The exercise of control*. New York: W. H. Freeman.
- Chi, M. T. H. (2008). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift. In S. Vosniadou (Ed.), *International Handbook of Research on Conceptual Change* (pp. 61-82). New York: Routledge.
- Deci, E. L., & Ryan, R. M. (1985). *Intrinsic motivation and self-determination in human behavior*. New York: Plenum.
- Pekrun, R. (2006). The control-value theory of achievement emotions. *Educational Psychology Review, 18*(4), 315-341.
- Piaget, J. (1952). *The Origins of Intelligence in Children* (M. Cook, Trans.). New York: International Universities Press.
- Posner, G. J., Strike, K. A., Hewson, P. W., & Gertzog, W. A. (1982). Accommodation of a scientific conception. *Science Education, 66*(2), 211-227.
- Ryan, R. M., & Deci, E. L. (2000). Self-determination theory and the facilitation of intrinsic motivation, social development, and well-being. *American Psychologist, 55*(1), 68-78.
- Vygotsky, L. S. (1978). *Mind in Society: The Development of Higher Psychological Processes*. Harvard University Press.
- Weiner, B. (1985). An attributional theory of achievement motivation and emotion. *Psychological Review, 92*(4), 548-573.

### B.2 中文经典与核心期刊

- 皮亚杰. (1981). *发生认识论原理* (王宪钿 等译). 北京: 商务印书馆.
- 林崇德. (2009). *发展心理学* (第二版). 北京: 人民教育出版社.
- 皮连生. (2009). *教育心理学* (第四版). 上海: 上海教育出版社.
- 周国韬, 杨雪梅. (2003). 班杜拉的自我效能感理论及其教育意义. *外国教育研究, 30*(3), 1-5.
- 刘海燕, 闫荣双, 郭德俊. (2003). 认知动机理论的新近发展——自我决定论. *心理科学, 26*(6), 1115-1116.
- 韩仁生. (1996). 中小学生考试成败归因的研究. *心理学报, 28*(2), 140-147.
- 俞国良, 董妍. (2005). 学业情绪研究及其对学生发展的意义. *教育研究*, (10), 39-43.
- 李高峰, 刘恩山. (2009). 前科学概念的研究综述. *学科教育*, (3), 91-95.
