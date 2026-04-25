# Legacy — 旧"虚拟课堂回合制"架构归档

> ⚠️ 本目录下的所有代码**已停用**，新功能不要导入 `legacy.*`。
> 仅保留作为 git history、设计回顾与答辩素材。

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

理论上能跑，所有内部 import 已改为 `legacy.*` 前缀，依赖的 main 模块（`llm`、`schemas.lesson`、`schemas.stage`、`schemas.student`）保持不变。

```bash
# 在 backend/ 下手动跑老 demo（仅用于回看）
uv run python -m legacy.scripts.try_director
uv run python -m legacy.scripts.try_classroom --auto

# 跑 legacy 测试（不在 CI 中）
uv run pytest legacy/tests
```

## 不要这么做

- ❌ 在新代码 import `legacy.*` 模块
- ❌ 修复 legacy 的 bug
- ❌ 给 legacy 加新功能
- ❌ 把 legacy 的 prompt 拷贝到新 prompt 里"参考"（新 prompt 必须从零写）

## 可以这么做

- ✅ 阅读 legacy 代码理解过往设计权衡
- ✅ 复用 `data/personas/`、`data/stage_profiles/`、`data/misconceptions/`、`data/lesson_samples/`（这些**不在 legacy**）
- ✅ 复用 `agents/student.py`、`rag/`、`schemas/student.py`、`schemas/lesson.py`、`schemas/stage.py`、`schemas/misconception.py`（这些**保留为主路径**）
- ✅ 在答辩时引用本目录证明"我们做过完整探索后才主动转型"
