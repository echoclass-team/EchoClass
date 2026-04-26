# `backend/kb/` — 教育学知识库

教育学理论卡片的持久化、解析与（第二期）进化引擎。

## 模块清单

| 文件 | 作用 |
|---|---|
| `models.py` | 5 张表 SQLAlchemy ORM（`kb_*` 前缀） |
| `database.py` | Engine/Session 工厂，SQLite 优化 |
| `poc_loader.py` | 理论卡片加载 + persona anchors 解析（DB / JSON 双路径） |
| `evolution.py` | （第二期）观察事件写入 + 候选迷思状态机 |

## 数据模型

```
kb_theory                   理论卡片主表
  ├─ kb_theory_trait        trait 变体（复合主键）
  └─ kb_theory_anchor       trait ↔ persona/misconception/rubric_dim 多对多

kb_observation              运行时观察事件 + 审计日志
kb_misconception_candidate  LLM 候选迷思 + 审核状态机
```

## 加载源切换

`poc_loader.load_theories()` 支持三种模式：

| `ECHOCLASS_KB_SOURCE` | 行为 |
|---|---|
| 未设置 / `auto`（默认） | DB 优先，DB 空或异常时 fallback JSON |
| `db` | 强制 DB；异常会抛出 |
| `json` | 强制 JSON 文件加载（`data/edu_theories/*.json`） |

## 数据库管理

### 首次起库

```bash
# 方式 A：alembic（规范路径）
cd backend
uv run alembic upgrade head
uv run python scripts/seed_edu_kb.py

# 方式 B：一步到位（开发常用）
cd backend
uv run python scripts/seed_edu_kb.py --reset
```

### 增量更新理论卡片

修改 `data/edu_theories/*.json` 后：

```bash
cd backend
uv run python scripts/seed_edu_kb.py        # upsert
uv run python scripts/seed_edu_kb.py --dry-run  # 仅看变化
```

### 修改 schema

修改 `kb/models.py` 后，生成迁移：

```bash
cd backend
uv run alembic revision --autogenerate -m "add foo column"
# 检查生成的 alembic/versions/*.py
uv run alembic upgrade head
```

### 测试用内存库

```bash
ECHOCLASS_DB_URL=sqlite:///:memory: uv run pytest tests/test_kb_*.py
```

## 默认 DB 文件位置

`data/echoclass.db`（gitignored）。可用 `ECHOCLASS_DB_URL` 环境变量覆盖。

## 表名前缀约定

所有表名 `kb_` 前缀。理由：B 端 M3 会在同一个 SQLite 文件加 `qa_sessions` /
`dialogs` / `messages` 等业务表，前缀避免冲突。
