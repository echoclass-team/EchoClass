# EchoClass

> AI-powered Q&A coaching for pre-service teachers.
> 师范生 1v1 答疑陪练系统 —— 让未来的教师在走上讲台前先被 AI 学生「问倒」几百次。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

---

## ✨ 项目简介

### 背景

师范生最高频、最痛苦的备课动作不是「讲课」，而是**被学生问倒**：

- **真人试讲难**：组织一节真实课堂代价高，一次只能留下 40 分钟录音和模糊印象
- **反馈滞后**：导师点评稀缺，错了就是真的失败，没有重来一次的机会
- **学生反应千差万别**：薄弱生、优等生、走神生、爱跑题生 —— 真实课堂只能遇到一种组合
- **教案到实战的鸿沟**：写教案时计划详尽，一到课堂就发现「这个概念孩子根本听不懂」

### 使用流程

EchoClass 是一个基于教育学双层建模的 1v1 答疑陪练系统：

1. **上传教案** — PDF / Markdown / TXT，系统自动解析并抽取学科、学段、教学目标、知识点、难点
2. **选择学段与学生** — 6 档学段（小学 3 + 初中 2 + 高中 1）× 每档 3 种典型学生 = 18 个虚拟学生人设
3. **学生主动提问** — AI 学生根据自己的人设 × 教案内容**主动构思**会问老师的问题（5 类 category × 3 档难度，关联具体教学重点与学科迷思）
4. **微信式 1v1 答疑** — 师范生从问题队列里挑学生进入 1v1 对话；多个学生可切换
5. **退出总结** — 统计已解答 / 放弃数、覆盖的教学重点、破除的学科迷思

### 核心设计

- **双层教育学建模**：6 档学段特征库（基于皮亚杰认知发展阶段、维果茨基最近发展区、埃里克森心理社会理论、《中小学心理健康教育指导纲要》）约束认知上限，再叠加个体人设（性格、口头禅、学业水平、迷思倾向），避免 LLM 常见的「小学一年级开口讲微积分」失真。

- **学生主动提问**：颠倒「老师讲、学生答」的传统模拟范式，更接近真实辅导场景，也最贴师范生备课时的高频痛点（「如果学生这样问我能答上来吗？」）。

- **学科迷思概念库驱动**：学生的错误前提不是随机的，而是从学科常见迷思库里挑选（如小学分数加法常把分子分母分别相加）。`stuck_misconception` 类问题的对话只有当老师**真正击中错误前提**时学生才会承认「懂了」。

- **二阶段 self-check 提升问题质量**：`generate_questions` 内部跑两次 LLM —— 先宽生成 N+overshoot 个候选，再让 agent 自评（人设贴合度 + 教育价值 + 教案相关性），最后类别多样性筛选取 top N。

- **同学段 few-shot 注入**：6 个学段各维护 2 个 ask 范例 + 2 个 chat 范例（[`data/qa_examples/`](./data/qa_examples/)），渲染 prompt 时按当前 persona 自动挑选注入，显著提升口语化与人设贴合度。

- **教案 RAG 检索**：上传的教案被解析、切片、向量化并索引，问题与对话围绕教案实际内容展开。

## 🏗️ 技术栈

| 层 | 技术 | Owner |
|---|---|---|
| **前端** | Next.js 14（App Router）· TypeScript · TailwindCSS · shadcn/ui · Zustand · TanStack Query · Recharts | **B** |
| **API / 协议** | FastAPI · WebSocket（JSON Lines）· REST · CORS · uv | **B** |
| **Agent 编排** | 1v1 dialog session 管理（普通 async service 类）· few-shot + self-check 二阶段质量增强 | **A** |
| **LLM 接入** | ChatECNU ecnu-max（OpenAI 兼容接口）· openai 客户端 · tenacity 重试 · token 使用日志 | **A** |
| **RAG** | Chroma 向量库 · pymupdf4llm（PDF → Markdown）· Jinja2 Prompt 模板 · 500 token 切片 | **A** |
| **教育学建模** | 6 档学段认知特征库 · 18 个学生人设 JSON · 学科迷思概念库 · 6 学段 few-shot 范例 | A / C |
| **持久化** | SQLite（会话 / 消息） | **B** |
| **评估** | Flanders 互动分析 · 自定义 Rubric · LLM-as-a-Judge | A / C |
| **测试** | pytest + pytest-asyncio（后端）· Vitest + Playwright（前端，可选） | A / B |

## 📁 目录结构

```
EchoClass/
├── backend/                     # Python 3.11+ · FastAPI
│   ├── agents/
│   │   └── student.py           # StudentAgent — generate_questions / respond_in_dialog
│   ├── services/
│   │   └── qa_session.py        # QASession orchestrator（1v1 答疑会话编排）
│   ├── rag/
│   │   ├── parser.py            # PDF / MD / TXT → 纯文本（pymupdf4llm）
│   │   ├── extractor.py         # LLM 抽取 LessonMeta（subject/grade/topic/objectives/key_points/difficult_points）
│   │   ├── indexer.py           # 500 token 切片 + Chroma 向量化
│   │   ├── misconceptions.py    # 学科迷思概念库（按 stage/subject/key_point 匹配）
│   │   └── qa_examples.py       # 6 学段 few-shot 范例集合（按 persona 自动挑选）
│   ├── llm/                     # LLMClient 封装（chat / stream + 重试 + 日志）
│   ├── prompts/
│   │   ├── student_ask.j2       # 学生根据教案生成问题（含同学段 few-shot）
│   │   ├── student_chat.j2      # 学生 1v1 多轮对话（含 [懂了] 自我宣称解决）
│   │   ├── student_check.j2     # 二阶段 self-check 评分
│   │   └── extractor.j2         # 教案元数据抽取
│   ├── schemas/
│   │   ├── stage.py             # StageProfile（学段认知特征）
│   │   ├── student.py           # Persona / ClassroomContext
│   │   ├── lesson.py            # LessonMeta / LessonRecord / RecommendedPersonasData
│   │   ├── question.py          # StudentQuestion（含 self_score / category / difficulty / linked_*）
│   │   ├── dialog.py            # DialogSession / DialogMessage / DialogReplyResult
│   │   └── misconception.py     # Misconception
│   ├── api/                     # REST 路由（B 端）
│   ├── db/                      # SQLite 持久化（B 端规划中）
│   ├── scripts/                 # 冒烟测试与 CLI demo
│   └── tests/                   # pytest 单元与集成测试
├── frontend/                    # TypeScript · Next.js 14 + TailwindCSS（B 端）
├── data/
│   ├── stage_profiles/          # 6 档学段认知特征 JSON
│   ├── personas/                # 18 个学生人设 JSON
│   ├── qa_examples/             # 6 学段 few-shot 范例集合
│   ├── lesson_samples/          # 样例教案（PDF + Markdown + 解析预期）
│   ├── misconceptions/          # 学科迷思概念库
│   └── eval_rubrics/            # 评估评分标准（规划中）
├── docs/
│   ├── roles.md                 # 三人分工细则
│   ├── api_contract.md          # API 合约
│   ├── persona_design.md        # 人设设计文档
│   └── proposal.md              # 立项书
├── .github/                     # PR / Issue 模板
├── CONTRIBUTING.md              # 协作规范
└── README.md
```

## 👥 团队分工

> 完整分工细则见 **[`docs/roles.md`](./docs/roles.md)**，以下为速览。

| 角色 | 代号 | 负责人 | 核心职责 | 代码领地 |
|---|---|---|---|---|
| **Agent 工程师** | `A-Agent` | **[@Nekooo915](https://github.com/Nekooo915)** | LLMClient 封装、StudentAgent（提问 + 1v1 对话）、QASession 编排器、教案 RAG 管线、迷思库 / few-shot 数据加载 | `backend/{agents,services,rag,llm,prompts,schemas}` |
| **全栈工程师** | `B-Full` | **[@Traumere7](https://github.com/Traumere7)** | 前端答疑 UI（微信式多对话切换）、WebSocket 端到端、REST 路由、会话持久化、视觉与落地页 | `frontend/`、`backend/{api,db}` |
| **产品 / 评测** | `C-Prod` | **[@IST00](https://github.com/IST00)** | 立项书与产品展示材料、学生人设设计、学科迷思概念库、评估 Rubric、用户测试、Demo 视频 | `data/`、`docs/`、`backend/prompts/` |

### A ↔ B 协议（待对齐）

- A 通过 `services/qa_session.QASession` 暴露：`spawn` / `next_pending` / `start_dialog` / `send_teacher_message` / `mark_resolved` / `abandon_dialog` / `summary`
- B 在 WebSocket endpoint 中 consume `QASession` 事件并编码为 JSON Lines 帧推给前端
- 前后端事件协议在 `docs/api_contract.md` 与 issue 中固化

## 🚦 协作 & 开发

- **协作规范**：[`CONTRIBUTING.md`](./CONTRIBUTING.md)
- **分工细则**：[`docs/roles.md`](./docs/roles.md)
- **API 合约**：[`docs/api_contract.md`](./docs/api_contract.md)
- **人设设计**：[`docs/persona_design.md`](./docs/persona_design.md)
- **立项书**：[`docs/proposal.md`](./docs/proposal.md)
- **任务看板**：<https://github.com/orgs/echoclass-team/projects/1>
- **Issue 列表**：<https://github.com/echoclass-team/EchoClass/issues>

### 路线图

| 里程碑 | 范围 | 状态 |
|---|---|---|
| **M1 — 后端 1v1 闭环** | StudentAgent.generate_questions / respond_in_dialog · QASession orchestrator · 6 学段 few-shot · 二阶段 self-check · CLI demo · 单元 / 集成测试 | ✅ 完成 |
| **M2 — 前后端联调** | 流式 chunk · WebSocket 协议 · 微信式 1v1 UI · 多学生切换 · 队列红点提醒 | ⏳ 进行 |
| **M3 — 评估闭环** | 学生自我宣称解决判定 · 师范生手动 override · 退出 summary 报告 · 评估 Rubric | ⏳ |
| **M4 — 产品打磨** | 评估 Agent 自动判分 · 用户测试 · Demo 视频 · PPT | ⏳ |

完整 issue 列表见 GitHub。

### 新成员 Onboarding

1. 阅读本 README + [`CONTRIBUTING.md`](./CONTRIBUTING.md) + [`docs/roles.md`](./docs/roles.md)
2. 认领自己的 Role（A / B / C）
3. 从 [Issue 列表](https://github.com/echoclass-team/EchoClass/issues) 里挑一个分配给自己
4. 按 [`CONTRIBUTING.md`](./CONTRIBUTING.md) 流程开分支、写代码、开 PR

```bash
gh issue develop <N> --repo echoclass-team/EchoClass --checkout
```

### 本地启动后端

详见 [`backend/README.md`](./backend/README.md)。快速开始：

```bash
cd backend
uv sync --extra dev                       # 安装依赖（需先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh）
cp .env.example .env                      # 填入 OPENAI_API_KEY 等
uv run uvicorn main:app --reload --port 8000
# 验证：curl http://localhost:8000/health  →  {"status":"ok"}
uv run pytest                             # 全部单元 / 集成测试
```

### 本地启动前端

```bash
cd frontend
npm install
npm run dev                               # 启动在 http://localhost:3000
```

前端默认连后端 `http://localhost:8000`，覆盖在 `frontend/.env.local` 设置：

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### 1v1 答疑陪练 demo（真实 LLM）

```bash
cd backend
uv run python scripts/try_qa_session.py --lesson math_p3_fraction --students 2 --questions 3
```

交互命令：`/resolve` 标记已解答 · `/abandon` 放弃 · `/switch` 切换学生 · `/done` 结束 session。

可选学段教案：`math_p2_addition` · `math_p3_fraction` · `math_p5_area` · `math_j3_quadratic` · `math_h2_derivative` · `physics_j2_force`。

## 📜 License

MIT
