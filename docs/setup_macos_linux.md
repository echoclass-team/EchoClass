# EchoClass 后端使用文档（macOS / Linux）

适用于 macOS（Apple Silicon / Intel）以及主流 Linux 发行版（Ubuntu 22.04+ / Debian 12+ / Fedora 40+ / Arch 等）。

> Windows 用户请看 [`setup_windows.md`](./setup_windows.md)。

---

## 1. 系统要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | **3.11+**（推荐 3.11 / 3.12 / 3.13） | `pyproject.toml` 中 `requires-python = ">=3.11"` |
| Git | 任意近期版本 | 拉代码 |
| uv | 最新稳定版 | 唯一指定的包管理器，**不要用 pip / poetry** |
| 系统编译工具 | 见下方 | `chromadb` / `pymupdf4llm` 个别平台需要 |

### 1.1 安装系统依赖

**macOS**（Xcode Command Line Tools 一般已带 `clang`）：

```bash
# 若未装过，会弹窗提示
xcode-select --install
```

**Ubuntu / Debian**：

```bash
sudo apt update
sudo apt install -y build-essential python3-dev curl git
```

**Fedora / RHEL**：

```bash
sudo dnf install -y gcc gcc-c++ python3-devel curl git
```

**Arch / Manjaro**：

```bash
sudo pacman -S --needed base-devel python git curl
```

---

## 2. 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 安装后让当前 shell 立即识别（或重开终端）：
source $HOME/.local/bin/env   # macOS / Linux 默认安装位置
uv --version                  # 验证：uv 0.5+ 即可
```

---

## 3. 克隆仓库

```bash
git clone https://github.com/echoclass-team/EchoClass.git
cd EchoClass
```

---

## 4. 安装后端依赖

```bash
cd backend
uv sync --extra dev
```

`uv sync` 会：

- 自动创建 `.venv/`（位于 `backend/.venv`）
- 按 `uv.lock` 装好运行时 + 开发依赖

主要依赖一览（来自 `backend/pyproject.toml`）：

- **Web**: `fastapi`, `uvicorn[standard]`, `python-multipart`
- **LLM**: `openai>=1.40` (OpenAI 兼容客户端), `tenacity` (重试)
- **Schema**: `pydantic>=2.8`
- **Prompt**: `jinja2`
- **RAG**: `chromadb>=0.5`, `pymupdf4llm>=0.0.17`
- **配置**: `python-dotenv`
- **dev**: `pytest>=8.3`, `pytest-asyncio>=0.24`, `httpx`

---

## 5. 配置环境变量

```bash
cp .env.example .env
```

打开 `backend/.env`，填入：

```ini
# 默认走华东师大 ChatECNU（参赛平台自有大模型）
# 获取 token：登录 https://chat.ecnu.edu.cn/html/ → 左下角头像 → 我的令牌
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
LLM_MODEL=ecnu-max

# CORS（前端 dev server）
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

> `.env` 已在 `.gitignore`，**绝对不要 commit**。
>
> 如果你想换 DeepSeek / Qwen 等其它 OpenAI 兼容后端，把 `OPENAI_BASE_URL` / `LLM_MODEL` 替换即可，业务代码不需要动（参考 `.env.example` 注释）。

---

## 6. 运行单元测试（不消耗 API 配额）

```bash
# 在 backend/ 目录下
uv run pytest -q
```

预期输出（截至当前进度）：

```
142 passed in ~1s
```

测试用 mock 替代 LLM，**不会调外部网络**，可在无 token 环境下跑。

### 6.1 跑指定测试

```bash
uv run pytest tests/test_student_stream.py -v       # 流式输出
uv run pytest tests/test_qa_session.py -v           # 1v1 答疑编排
uv run pytest tests/test_student_dialog.py -v       # 多轮对话 + [懂了] 标记
uv run pytest tests/test_student_questions.py -v    # 学生问题生成
uv run pytest -k "stream"                           # 关键字筛选
```

---

## 7. 真实 LLM 冒烟测试（消耗 API 配额）

需要 `.env` 里有效的 `OPENAI_API_KEY`。

### 7.1 1v1 答疑陪练交互 demo

```bash
uv run python scripts/try_qa_session.py
# 默认: math_p3_fraction（小学中年级·分数）+ 2 学生 × 3 问题

# 切其它学段教案
uv run python scripts/try_qa_session.py --lesson math_h2_derivative --students 2 --questions 2
```

可选 `--lesson`：

| key | 学段 | 示例话题 |
|---|---|---|
| `math_p2_addition` | 小学低年级 | 两位数加法 |
| `math_p3_fraction` | 小学中年级 | 分数的初步认识 |
| `math_p5_area` | 小学高年级 | 平行四边形面积 |
| `math_j3_quadratic` | 初中高年级 | 二次函数 |
| `math_h2_derivative` | 高中 | 导数的概念 |
| `physics_j2_force` | 初中低年级 | 力的概念 |

进入交互模式后命令：

- `/resolve` — 把当前对话标为已解答
- `/abandon` — 放弃当前对话
- `/switch` — 切到下一个学生
- `/done` — 结束 session 并打印 summary

### 7.2 教案 RAG 管线

```bash
uv run python scripts/try_lesson_rag.py
# 解析 data/lesson_samples/ 下样例 PDF → LLM 抽取 LessonMeta → Chroma 索引
```

### 7.3 Persona 完整性校验（不调 LLM）

```bash
uv run python scripts/validate_personas.py
# 校验 data/personas/*.json 18 字段 schema
```

---

## 8. 启动 FastAPI 开发服务器

```bash
# backend/ 目录下
uv run uvicorn main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
# -> {"status":"ok"}
```

API 文档自动生成：

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

---

## 9. 常见问题

### `uv: command not found`

`uv` 安装到了 `~/.local/bin`，但当前 shell 还没把它加进 PATH：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc   # zsh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # bash
exec $SHELL
```

### `uv sync` 在 Linux 编译 `chroma-hnswlib` 失败

缺 C++ 编译器或 Python 头文件：

```bash
# Ubuntu/Debian
sudo apt install -y build-essential python3-dev
# Fedora
sudo dnf install -y gcc-c++ python3-devel
```

### macOS Apple Silicon 上 `pymupdf4llm` 报错

更新 Xcode Command Line Tools：

```bash
sudo rm -rf /Library/Developer/CommandLineTools
xcode-select --install
```

### 测试卡死或网络超时

确认是否误把单测跑到了真实网络上。本仓库所有 `tests/` 都是 mock，**不应**联网；
如果真的卡，多半是 `chromadb` 的 telemetry / OpenTelemetry 在后台尝试上报。可以在 `.env` 里加：

```ini
ANONYMIZED_TELEMETRY=False
```

### API Key 401 / 403

- 确认 token 没过期（ChatECNU 控制台可重置）
- 确认 `OPENAI_BASE_URL` 末尾**带 `/v1`**：`https://chat.ecnu.edu.cn/open/api/v1`
- 别在 token 前后留空格

---

## 10. 一行回归

```bash
cd backend && uv sync --extra dev && uv run pytest -q
```

期望：`142 passed`。
