# EchoClass Backend

Python 3.11 · FastAPI · LangGraph · Chroma

## 本地启动

依赖管理用 [uv](https://docs.astral.sh/uv/)。

```bash
# 1. 安装 uv（若未装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 进入 backend 目录，同步依赖（自动创建 .venv）
cd backend
uv sync --extra dev

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
# 默认使用 ChatECNU（华东师大大模型，参赛平台自有）：
#   登录 https://chat.ecnu.edu.cn/html/ → 左下角头像 → 我的令牌
#   base_url: https://chat.ecnu.edu.cn/open/api/v1
#   model: ecnu-max
# 也可切 DeepSeek / Qwen 等其它 OpenAI 兼容后端（见 .env.example 注释）

# 4. 启动开发服务器
uv run uvicorn main:app --reload --port 8000
```

验证：

```bash
curl http://localhost:8000/health
# -> {"status":"ok"}
```

## 运行测试

```bash
cd backend
uv run pytest
```

## 目录结构

```
backend/
├── agents/      # 学生 / Director / Evaluator Agent (Role A)
├── api/         # REST 路由 + WebSocket endpoint (Role B)
├── db/          # SQLite 持久化 (Role B)
├── graph/       # LangGraph 状态机 (Role A)
├── llm/         # LLM 客户端封装 (Role A)
├── prompts/     # Prompt 模板 (Role C + A)
├── rag/         # 教案解析、向量化、检索 (Role A)
├── schemas/     # Pydantic 模型 (Role B)
├── tests/       # pytest
├── main.py      # FastAPI 入口（脚手架由 A 建，日常归 B）
└── pyproject.toml
```

所有权细则见根目录 [`docs/roles.md`](../docs/roles.md)。
