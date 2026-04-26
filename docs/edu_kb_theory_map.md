# EchoClass 教育学知识库关系图

> **状态**：M3 第一期 · 答辩主图 · 2026-04-27
> **作者**：C-Prod
> **配套文档**：`docs/edu_kb_design.md`（设计基线）/ `docs/eval_rubric_draft.md`（Rubric 草案）

---

## 0. 阅读指引

本图是答辩 5 分钟版本的主视觉。建议按以下顺序看：

1. **先看左中右三栏的标题**：左 = 教育学理论（8 张）、中 = 虚拟学生人设（6 个代表）、右 = 评估 Rubric 维度（5 个）
2. **再看边的颜色与语义**：实线 = "锚定"（人设引用理论 trait）；虚线 = "评分依据"（Rubric 维度引用理论操作化）
3. **最后看 anxious persona 的高亮路径**：4 条锚点同时连到 4 张卡片，是 EchoClass 与"形容词式 prompt"产品的差异化典型例

---

## 1. 全景关系图

```mermaid
graph LR

  %% ============== 理论层 ==============
  subgraph THEORIES["8 张教育学理论卡片"]
    direction TB
    Bandura["Bandura<br/>自我效能感<br/>(1977)"]
    Vygotsky["Vygotsky<br/>最近发展区 ZPD<br/>(1978)"]
    Posner["Posner<br/>概念改变 4 步<br/>(1982)"]
    Piaget["Piaget<br/>认知发展阶段<br/>(1952)"]
    Pekrun["Pekrun<br/>学业情绪 CV 理论<br/>(2006)"]
    DeciRyan["Deci & Ryan<br/>自我决定理论 SDT<br/>(1985)"]
    Weiner["Weiner<br/>归因理论<br/>(1985)"]
    Chi["Chi<br/>迷思三类型<br/>(2008)"]
  end

  %% ============== 人设层 ==============
  subgraph PERSONAS["6 个学段代表人设"]
    direction TB
    Quiet["p_lower_quiet<br/>周小萌 / P1<br/>安静女孩"]
    Xueba["p_middle_xueba<br/>陈思远 / P3<br/>数学尖子"]
    Anxious["⭐ p_upper_anxious<br/>郑宇凡 / P6<br/>焦虑薄弱"]
    Introvert["j_lower_introvert<br/>李文博 / J2<br/>内向学霸"]
    Giveup["j_upper_giveup<br/>徐浩 / J3<br/>放弃型"]
    Lost["h_lost<br/>宋俊鹏 / H3<br/>意义危机"]
  end

  %% ============== Rubric 维度层 ==============
  subgraph RUBRIC["5 维评估 Rubric"]
    direction TB
    MR["MR · 迷思破除"]
    KC["KC · 重点覆盖"]
    RR["RR · 解决率"]
    TQ["TQ · 师范生提问质量"]
    SS["SS · 学生满意度"]
  end

  %% ============== 实线：人设 → 理论（锚定）==============
  Quiet -.锚定.-> Bandura
  Quiet -.锚定.-> Pekrun
  Quiet -.锚定.-> Piaget

  Xueba -.锚定.-> Bandura
  Xueba -.锚定.-> Vygotsky
  Xueba -.锚定.-> DeciRyan
  Xueba -.锚定.-> Piaget

  Anxious ==锚定==> Bandura
  Anxious ==锚定==> Vygotsky
  Anxious ==锚定==> Pekrun
  Anxious ==锚定==> Weiner

  Introvert -.锚定.-> Bandura
  Introvert -.锚定.-> Pekrun
  Introvert -.锚定.-> Piaget

  Giveup -.锚定.-> Bandura
  Giveup -.锚定.-> Weiner
  Giveup -.锚定.-> DeciRyan
  Giveup -.锚定.-> Pekrun

  Lost -.锚定.-> DeciRyan
  Lost -.锚定.-> Weiner
  Lost -.锚定.-> Pekrun
  Lost -.锚定.-> Piaget

  %% ============== 虚线：理论 → Rubric（评分依据）==============
  Posner -. 评分依据 .-> MR
  Chi -. 评分依据 .-> MR

  Vygotsky -. 评分依据 .-> KC
  Piaget -. 评分依据 .-> KC

  Bandura -. 评分依据 .-> RR
  Weiner -. 评分依据 .-> RR

  Vygotsky -. 评分依据 .-> TQ

  Pekrun -. 评分依据 .-> SS
  DeciRyan -. 评分依据 .-> SS

  %% ============== 样式 ==============
  classDef theory fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#92400e
  classDef persona fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e40af
  classDef rubric fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#166534
  classDef poc fill:#fee2e2,stroke:#dc2626,stroke-width:3px,color:#7f1d1d

  class Bandura,Vygotsky,Posner,Piaget,Pekrun,DeciRyan,Weiner,Chi theory
  class Quiet,Xueba,Introvert,Giveup,Lost persona
  class Anxious poc
  class MR,KC,RR,TQ,SS rubric
```

---

## 2. 边的语义对照表

| 边形态 | 语义 | 数据载体 |
|---|---|---|
| **实线粗边** `==锚定==>` | POC 已实证的锚点 | `p_upper_anxious.theory_anchors` 4 条（含 POC 验证两条 + 本期扩充两条） |
| **虚线** `-.锚定.->` | 本期新增的 5 个 persona 锚点 | `data/personas/<persona>.json` 中 `theory_anchors` 字段 |
| **虚线** `-. 评分依据 .->` | Rubric 维度引用的理论操作化（M3 第二期落地） | `docs/edu_kb_design.md` §5 + `docs/eval_rubric_draft.md` v0.5 |

---

## 3. 重点关系：anxious persona 的"四锚点"案例

`p_upper_anxious`（郑宇凡）是 EchoClass 与同类产品差异化的典型例子。同一个人设同时被 **4 张教育学理论卡片**锚定，4 套 `operational_rules` 协同注入到 `StudentAgent` 的 prompt：

```mermaid
graph TD
  A["⭐ p_upper_anxious<br/>郑宇凡 / P6<br/>学业吃力 + 小升初焦虑"]

  A -->|认知层面| B1["Bandura: low_self_efficacy<br/>'我不会''老师别叫我''看同桌求助'<br/>= 6 条 operational_rules"]
  A -->|认知层面| B2["Vygotsky: needs_high_scaffolding<br/>抽象解释吸收差，需 2-3 步分解<br/>= 5 条 operational_rules"]
  A -->|情绪层面| B3["Pekrun: anxiety<br/>说话颤抖、眼眶泛红<br/>= 6 条 operational_rules"]
  A -->|归因层面| B4["Weiner: maladaptive_ability_attribution<br/>'我太笨了'<br/>= 6 条 operational_rules"]

  B1 -.合成.-> C["✨ StudentAgent prompt<br/>注入 23 条具体可观察行为准则<br/>而非'焦虑'两字"]
  B2 -.合成.-> C
  B3 -.合成.-> C
  B4 -.合成.-> C

  classDef poc fill:#fee2e2,stroke:#dc2626,stroke-width:3px,color:#7f1d1d
  classDef theory fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#92400e
  classDef output fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px,color:#3730a3

  class A poc
  class B1,B2,B3,B4 theory
  class C output
```

> **关键论证**：传统的形容词式 prompt（"焦虑、害羞、害怕考试"）只会得到风格化的台词；EchoClass 的多维理论锚点把"焦虑"这一笼统印象拆解为**认知 + 情绪 + 归因**三个独立维度的 23 条可观察行为，由不同学派的原典背书——这是答辩时可以掷地有声讲出来的科学性故事。

---

## 4. 学派分布

```mermaid
pie title 第一期 8 张理论卡片的学派分布
  "建构主义系（Vygotsky/Posner/Chi）" : 3
  "动机/情绪系（Pekrun/Deci-Ryan/Weiner）" : 3
  "社会认知（Bandura）" : 1
  "发生认识论（Piaget）" : 1
```

第一期覆盖了**「认知」「情绪」「动机」「概念改变」**四个核心维度，足以撑起一个学生人设的多维侧写。第二期补充**「评估能力」**（Bloom 修订版）与**「学习风格」**（Hattie 可见学习 / Gardner 多元智能）维度。

---

## 5. 后续路线

- **第二期补图**：把 Bloom + Hattie 加入主图（连到 TQ + SS），形成 10 张理论卡片的稳定盘
- **进化层补图**：增加 `trait_drift_detector → review queue → CI rebuild` 子图，演示进化 pipeline 的回路
- **持续维护**：每新增一个 persona anchor 或 Rubric ↔ theory 引用，本图同步更新（建议作为 PR checklist 一项）

---

## 6. 渲染说明

- 本图采用 [Mermaid](https://mermaid.js.org/) 语法，GitHub 与 VSCode + Markdown Preview Mermaid Support 插件均可直接渲染
- 答辩用导出建议：`mmdc -i edu_kb_theory_map.md -o edu_kb_theory_map.png -t default -b transparent`
- 颜色方案：理论 = 琥珀色 / 人设 = 蓝色 / Rubric = 绿色 / POC 高亮 anxious = 红色（与 EchoClass 演示文档配色保持一致）
