# Legacy — 旧"虚拟课堂回合制"架构归档

> ⚠️ 本目录下的所有代码**已停用**，新功能不要导入 `legacy.*`。
> 仅保留作为 git history 与设计回顾。

## 为什么停用

EchoClass 在 2026-04-25 完成了一次产品方向转型：

- **旧定位**：模拟一节完整虚拟课堂（Director 调度多学生 + LangGraph 回合制状态机）
- **新定位**：1v1 师范生答疑陪练（学生主动提问，老师 1v1 解答，类微信对话切换）

转型决策详见 [`docs/PIVOT.md`](../../docs/PIVOT.md)。

## 归档内容

| 路径 | 原路径 | 内容 |
|---|---|---|
| `legacy/agents/director.py` | `agents/director.py` | DirectorAgent（多学生调度） |
| `legacy/graph/` | `graph/` | LangGraph 课堂状态机 + checkpoint |
| `legacy/schemas/director.py` | `schemas/director.py` | DirectorDecision / StudentAction / Message / DirectorConfig |
| `legacy/schemas/events.py` | `schemas/events.py` | 旧 AgentEvent 协议（DirectorEvent / BoardUpdateEvent 等） |
| `legacy/prompts/director.j2` | `prompts/director.j2` | Director Agent prompt 模板 |
| `legacy/scripts/try_*.py` | `scripts/try_*.py` | Director / Classroom 交互测试脚本 |
| `legacy/tests/test_*.py` | `tests/test_*.py` | 对应单元测试，**已不参与 CI**（`pytest.ini_options.testpaths = ["tests"]` 不收 legacy） |

## 是否仍可运行

⚠️ **不再保证可运行**。随着 main 路径上的产品转型，`agents.student.StudentAgent` 的
`__init__` 不再接受 `context` 参数、`StudentReply` 已迁出、旧 `respond()` 已删除。
legacy 的 `graph/classroom.py` 仍按旧接口调用 StudentAgent，因此再跑 legacy
demo 会在 fanout/respond 调用处抛错。

legacy 代码保留的目的是**作为设计回顾与转型决策的可追溯记录**，不再追求执行可运行性。
如果未来真有"复活老课堂"的需求，需要：

1. 在 `legacy/agents/` 单独 fork 一份与 main 解耦的 `StudentAgent`
2. 或者在 main `StudentAgent` 上重新接出兼容旧接口的 wrapper

legacy 测试目录 `legacy/tests/` 已随产品转型清理。

## 不要这么做

- ❌ 在新代码 import `legacy.*` 模块
- ❌ 修复 legacy 的 bug
- ❌ 给 legacy 加新功能
- ❌ 把 legacy 的 prompt 拷贝到新 prompt 里"参考"（新 prompt 必须从零写）

## 可以这么做

- ✅ 阅读 legacy 代码理解过往设计权衡
- ✅ 复用 `data/personas/`、`data/stage_profiles/`、`data/misconceptions/`、`data/lesson_samples/`（这些**不在 legacy**）
- ✅ 复用 `agents/student.py`、`rag/`、`schemas/student.py`、`schemas/lesson.py`、`schemas/stage.py`、`schemas/misconception.py`（这些**保留为主路径**）
- ✅ 在产品汇报中引用本目录证明"我们做过完整探索后才主动转型"
