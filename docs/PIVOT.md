# EchoClass 产品方向转型 RFC（2026-04-25）

> Status: **已通过**（A / B / C 三人达成一致）
> Branch: `feat/qa-coach-pivot`
> 影响：架构级重构。旧 graph/director 归档至 `backend/legacy/`，新代码从零搭建。

---

## 1. 背景

EchoClass 原定位为 **AI 虚拟课堂师范生陪练系统**：
- 老师在系统里"讲课"
- DirectorAgent 调度 6 个虚拟学生
- LangGraph 状态机驱动回合制
- WebSocket 推流学生发言

我们已经做到 #69（迷思库集成），并在 `feat/student-focus-key-point` 上进一步加了"老师当前焦点"机制。但**真实试用后发现，"模拟一节完整课堂"这个目标本身存在不可逾越的障碍**：

### 为什么旧方向走不通

| # | 问题 | 是否可在 42 天内解决 |
|---|---|---|
| 1 | 真实课堂是异步交错的（学生打断、抢答、议论），我们却是严格回合制 | ❌（需重写消息层 + 状态管理） |
| 2 | 学生没有跨轮内部状态，N 个独立人偶轮流朗诵人设 | ❌（需做状态化 LLM） |
| 3 | 18 字段 persona + 学段 + 迷思一起灌进 prompt，LLM 风格固化 | ⚠️（治标不治本） |
| 4 | 缺"老师追问 → 学生改口"短回路 | ⚠️ |
| 5 | Director 决策粗粒度，"为什么这个学生举手"不真实 | ⚠️ |

**三人一致判断**：1、2 是结构性死结。继续推进会得到一个**"看着炫但用起来假"**的演示。

## 2. 新方向：1v1 师范生答疑陪练

### 核心场景

师范生最高频、最痛苦的备课动作不是"讲课"，是**被学生问倒**。我们就直接做"学生问、师范生答"的 1v1 陪练系统。

### 用户流程

1. 师范生**上传教案**（PDF / Markdown）
2. 系统**解析教案**，根据 `stage_id` 推荐默认人设组（可手动切换学段）
3. 每个学生 Agent 根据自己的人设 × 教案内容 **主动构思一组问题**（含难度、关联重点、关联迷思）
4. 系统按节奏**逐个推送**问题到师范生面前（不是一次性铺出 N 个）
5. 师范生选择某个学生进入 **1v1 微信式对话**
6. 通过 3–5 轮对话引导该学生：
   - 解决困惑（澄清概念）
   - 破除迷思（关联 misconception）
   - 应对反例（学生主动提问的拓展）
7. 学生 Agent 自我宣称"懂了"或师范生手动标记"已解答" → 切换到下一个学生
8. 退出时给出全场总结（解决了几个？什么类型？覆盖哪些重点？）

### 设计亮点

- **学生主动提问**：颠倒了"老师讲、学生答"的传统模拟范式，更接近真实辅导场景，也更适合师范生入门练习
- **微信式多对话切换**：保留"虚拟班级"卖点（多个学生），但去掉了多人调度的工程复杂度
- **问题结构化元数据**：每个问题都关联 `key_point` / `misconception_id` / `difficulty`，评估天然可量化
- **节奏控制**：问题逐个推送、单次只解决一个，不让师范生认知过载

### 命名

- **代码 / repo 名**：保留 `EchoClass`（避免改名造成的工程灾难）
- **对外产品名**：暂定 `PupilEcho · 师范生答疑陪练`（最终待定）
- **产品故事内核**：传统师范生只能在真实课堂里试错；EchoClass 让 AI 学生基于真实教案与 60+ 学科迷思主动向你提问，让每一次答疑都是安全的练兵。

## 3. 架构对比

### 旧架构（废弃）

```
teacher_input → director → fanout_students → aggregate → persist → wait
                  ↓               ↓
            DirectorDecision   StudentReply
                  ↓
        AgentEvent[director_event / student_reply_chunk / board_update / ...]
                  ↓
           WebSocket → 前端单一对话流
```

### 新架构

```
upload_lesson
   ↓
LessonMeta (rag/lesson_parser)
   ↓
spawn_student_dialogs(stage_id, lesson_meta)
   ↓
for each student in 推荐组:
    StudentAgent.generate_questions(lesson_meta) → list[StudentQuestion]
   ↓
DialogQueue: 按 student × question 排队
   ↓
Frontend 微信式 UI：
    ├─ 学生列表（红点 = 有未读问题）
    ├─ 当前对话窗口（StudentAgent.respond_in_dialog 多轮）
    └─ "标记已解答" 按钮
   ↓
评估总结（v2 加自动评估 Agent）
```

无 Director、无 graph 状态机、无回合制。每个 1v1 dialog 是独立的多轮对话 session。

## 4. 代码迁移决策

### Archive（移到 `backend/legacy/`，不删）

保留旧代码作为**设计回顾素材**和**git history 价值**。CI 不再跑 legacy 测试（`testpaths = ["tests"]`）。

| 原路径 | 归档路径 |
|---|---|
| `agents/director.py` | `legacy/agents/director.py` |
| `graph/` | `legacy/graph/` |
| `schemas/director.py` | `legacy/schemas/director.py` |
| `schemas/events.py` | `legacy/schemas/events.py` |
| `prompts/director.j2` | `legacy/prompts/director.j2` |
| `scripts/try_classroom.py`、`scripts/try_director.py` | `legacy/scripts/` |
| `tests/test_classroom_graph.py`、`tests/test_director_agent.py` | `legacy/tests/` |

详见 `backend/legacy/DEPRECATED.md`。

### 保留并复用（核心积累）

- ✅ `agents/student.py` — 1v1 dialog 模式的核心，加 `generate_questions()` 与 `respond_in_dialog()`
- ✅ `rag/lesson_parser/` — 教案解析照用
- ✅ `rag/misconceptions.py` — 60+ 迷思库直接用，是问题生成的素材
- ✅ `data/personas/*.json` — 6 个人设照用
- ✅ `data/stage_profiles/*.json` — 学段照用
- ✅ `data/lesson_samples/*` — 示例教案照用
- ✅ `data/misconceptions/*.json` — 迷思库照用
- ✅ `schemas/student.py`、`schemas/lesson.py`、`schemas/stage.py`、`schemas/misconception.py`
- ✅ `llm/client.py` — LLM 客户端

### 新增

- 🆕 `schemas/question.py` — `StudentQuestion`（含 category / difficulty / linked_misconception_id 等）
- 🆕 `schemas/dialog.py` — `DialogSession` / `DialogMessage` / `DialogStatus`
- 🆕 `agents/student.py` 扩展 — `generate_questions(lesson_meta)` + `respond_in_dialog(history)`
- 🆕 `services/qa_session.py` — 轻量 orchestrator（普通类，不是 graph）
- 🆕 `prompts/student_ask.j2` — 学生根据教案生成问题
- 🆕 `prompts/student_chat.j2` — 学生 1v1 多轮对话
- 🆕 `api/qa_session.py` — REST + WS endpoints
- 🆕 `agents/evaluator.py`（v2）— 自动判定问题是否解决

## 5. WebSocket 协议 v2

旧 `AgentEvent` 协议（`director_event` / `board_update` 等）作废。新协议骨架：

| 事件类型 | 方向 | 用途 |
|---|---|---|
| `lesson_uploaded` | 后→前 | 教案解析完成，附 LessonMeta |
| `students_spawned` | 后→前 | 学生组及其首批问题数 |
| `question_pushed` | 后→前 | 推送一个新问题给师范生（含 student_id、question metadata） |
| `dialog_opened` | 前→后 | 师范生选择某学生开始对话 |
| `teacher_message` | 前→后 | 师范生发言 |
| `dialog_message_chunk` | 后→前 | 学生流式回复块（保留打字机效果） |
| `dialog_message_end` | 后→前 | 学生本条回复结束 |
| `student_self_resolve` | 后→前 | 学生宣称"懂了"，请求确认 |
| `question_resolved` | 双向 | 问题标记为解决（含手动 / 自动来源） |
| `dialog_closed` | 前→后 | 师范生关闭当前对话或切换学生 |
| `session_summary` | 后→前 | 退出时全场总结 |

**A 端**（@Nekooo915）负责后端协议实现 + qa_session orchestrator
**B 端**（@Traumere7）负责前端 WS client + 微信式 UI

详细 schema 待 #25 重写为 #25-v2，本 RFC 合入后开新 issue。

## 6. 路线图

### M1：基础闭环（目标 7 天）
- [ ] 新 `StudentQuestion` / `DialogSession` schema
- [ ] `StudentAgent.generate_questions()`
- [ ] `StudentAgent.respond_in_dialog()`
- [ ] `services/qa_session.py` orchestrator
- [ ] 新 prompt 模板：`student_ask.j2` / `student_chat.j2`
- [ ] 单一教案 + 单一学生 + 1v1 对话能跑通（CLI demo）

### M2：多学生切换（目标 +5 天）
- [ ] DialogQueue 实现
- [ ] 多个学生并行待命，但师范生只能一对一
- [ ] WS 协议 v2 后端实现
- [ ] B 端微信式 UI 接入

### M3：评估闭环（目标 +5 天）
- [ ] 学生自我宣称"懂了"判定
- [ ] 师范生手动 override 按钮
- [ ] 退出总结 / 全场报告

### M4：评估 Agent（v2，时间允许时做）
- [ ] 自动判定迷思是否破除
- [ ] 给师范生打分 + 改进建议

## 7. 已合入但需要重新评估的工作

### `feat/student-focus-key-point`（focus PR，未合）

**保留**部分（对新方向仍有价值）：
- `agents/student.py` 加 `focus_key_point` 参数 → 1v1 答疑里也需要"老师当前在讲哪个重点"
- `prompts/student.j2` 区分焦点 vs 背景 → 同上
- `rag/misconceptions.py` 修空字符串 bug → 通用修复
- `tests/test_student_agent.py` focus 相关测试 → 保留

**废弃**部分（依赖 graph/state，已归档）：
- `graph/state.py` 加 `current_focus_key_point` 字段 → 已随 state.py 进 legacy
- `graph/classroom.py` `_detect_focus_key_point` 节点逻辑 → 已随 classroom.py 进 legacy
- `tests/test_classroom_graph.py` focus 测试 → 已随 test 文件进 legacy

**处理建议**：
1. focus PR **不直接合 main**
2. 在 pivot 分支上 cherry-pick focus PR 中**保留**部分的 commit
3. focus 分支废弃，关闭对应 PR 时引用本文档说明

## 8. 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 是否保留 EchoClass repo 名 | ✅ 保留 | 改名会断 PR/issue/CI 链接，工程零收益 |
| 旧代码处置 | Archive 不删 | 设计回顾价值 + git history；CI 自动跳过 |
| 是否重写 prompt | ✅ 从零写 | 旧 student.j2 是"被动应答"思路，新方向是"主动提问 + 多轮对话" |
| 是否新建 evaluator agent | M4 才做 | MVP 用学生自我宣称 + 师范生手动 override，足够交付 |
| 异步推送队列 | ❌ MVP 不做 | 串行队列已能演示"多学生切换"，工程量翻倍不值 |
| LangGraph 是否还用 | ❌ 不用 | 1v1 多轮对话用普通 service 类管理，graph 反而增加复杂度 |

## 9. 立即行动

- [x] 开 `feat/qa-coach-pivot` 分支
- [x] 平移 legacy 代码 + 修 import + 跑通 legacy 测试
- [x] 写本 RFC（PIVOT.md）+ legacy DEPRECATED.md
- [x] 主路径 127 测试通过
- [ ] **本 PR 合入 main**（用 squash merge，commit message 引用本文档）
- [ ] 关闭/重新规划的 issue：#24（LangGraph 状态机）、#25（旧 WS 协议）、#65（DirectorDecision adapter）→ 改为新协议 issue
- [ ] 新开 epic issue：`epic: 转型为 1v1 答疑陪练（PupilEcho）`
- [ ] cherry-pick focus PR 的可保留部分到 pivot 分支
