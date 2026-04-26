# `backend/kb/` — 教育学知识库

教育学理论卡片的持久化、解析与（第二期）进化引擎。

## 模块清单

| 文件 | 作用 |
|---|---|
| `models.py` | 5 张表 SQLAlchemy ORM（`kb_*` 前缀） |
| `database.py` | Engine/Session 工厂，SQLite 优化 |
| `poc_loader.py` | 理论卡片加载 + persona anchors 解析（DB / JSON 双路径） |
| `evolution.py` | 观察事件写入 + 候选迷思状态机（Phase 1.C 骨架，第二期接 LLM 检测） |
| `retrieval.py` | Chroma 向量检索（按 trait 粒度索引，跨学派过滤） |

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

## 向量索引（Chroma）

把 SQLite 里的理论 trait 全量索引进 Chroma `edu_theories` collection，
为第二期 LLM-as-Judge 准备语义检索能力。

```bash
cd backend
# 默认 ./chroma_data
uv run python scripts/build_theory_index.py
# 跑完做 sanity check
uv run python scripts/build_theory_index.py --sanity-query "焦虑学生"
```

⚠️ 当前默认 embedding 是英文 MiniLM，中文召回质量不佳。第二期会切换
多语种或 OpenAI embedding。本期仅保证功能与 metadata 过滤可用。

## 默认 DB 文件位置

`data/echoclass.db`（gitignored）。可用 `ECHOCLASS_DB_URL` 环境变量覆盖。

## 表名前缀约定

所有表名 `kb_` 前缀。理由：B 端 M3 会在同一个 SQLite 文件加 `qa_sessions` /
`dialogs` / `messages` 等业务表，前缀避免冲突。
