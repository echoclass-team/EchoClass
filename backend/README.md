# EchoClass Backend

Python 3.11+ · FastAPI · LangGraph · ChatECNU ecnu-max · Chroma

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
# 编辑 .env，填入你的 ChatECNU API Key：
#   登录 https://chat.ecnu.edu.cn/html/ → 左下角头像 → 我的令牌
#   默认 base_url: https://chat.ecnu.edu.cn/open/api/v1
#   默认 model: ecnu-max
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
uv run pytest         # 单元测试（45 passed，不走网络）
uv run python scripts/try_student_agent.py  # 真实 API 冒烟测试（消耗少量 tokens）
```

详细测试指引见 [`docs/w1_smoke_test.md`](../docs/w1_smoke_test.md)。

## 目录结构

```
backend/
├── agents/      # ✅ StudentAgent（单学生 Agent，根据人设生成回复）
├── api/         # REST 路由 + WebSocket endpoint (Role B)
├── db/          # SQLite 持久化 (Role B)
├── graph/       # LangGraph 状态机（W2）
├── llm/         # ✅ LLMClient 封装（ChatECNU ecnu-max，chat/stream + 重试 + 日志）
├── prompts/     # ✅ Jinja2 Prompt 模板（注入人设、口头禅、迷思概念等）
├── rag/         # 教案解析、向量化、检索（W1 进行中）
├── schemas/     # ✅ Pydantic 模型（Persona / StudentReply / ClassroomContext）
├── scripts/     # ✅ 冒烟测试脚本（加载 6 个人设 JSON + 真实 API 验证）
├── tests/       # ✅ 45 条单元测试（pytest + pytest-asyncio）
├── main.py      # FastAPI 入口
└── pyproject.toml
```

所有权细则见根目录 [`docs/roles.md`](../docs/roles.md)。
