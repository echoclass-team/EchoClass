# EchoClass 后端使用文档（Windows）

适用于 Windows 10 / 11（x64 / ARM64 均可）。推荐 **PowerShell 7+** 或新版 **Windows Terminal**，文中命令以 PowerShell 为主，备注 cmd 差异。

> macOS / Linux 用户请看 [`setup_macos_linux.md`](./setup_macos_linux.md)。

---

## 1. 系统要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Windows | 10 1909+ / 11 | 64 位 |
| Python | **3.11+**（推荐 3.11 / 3.12 / 3.13） | `pyproject.toml` 中 `requires-python = ">=3.11"` |
| Git | Git for Windows 任意近期版本 | <https://git-scm.com/download/win> |
| uv | 最新稳定版 | 唯一指定的包管理器，**不要用 pip / poetry / conda** |
| MSVC Build Tools | 2019+ | `chromadb` 依赖的 `chroma-hnswlib` 是 C++ 扩展，必装 |

### 1.1 安装 Python

从 <https://www.python.org/downloads/windows/> 安装 3.11+，**勾选 "Add python.exe to PATH"**。

```powershell
python --version
# Python 3.12.x
```

### 1.2 安装 Git

从 <https://git-scm.com/download/win> 下载默认安装即可。

### 1.3 安装 MSVC Build Tools（关键）

从 <https://visualstudio.microsoft.com/visual-cpp-build-tools/> 下载 **Build Tools for Visual Studio**，安装时勾选：

- **Desktop development with C++**（"使用 C++ 的桌面开发"）
  - Windows 11 SDK（最新）
  - MSVC v143 - VS 2022 C++ x64/x86 build tools

> 不装这个 `uv sync` 在 `chroma-hnswlib` 那一步会失败。这是大多数 Windows 用户唯一会遇到的卡点。

### 1.4 推荐：启用长路径（避免 npm/pip 超长路径报错）

以管理员身份运行 PowerShell：

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

---

## 2. 安装 uv

PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完后 **重开一个 PowerShell 窗口** 让 PATH 生效，验证：

```powershell
uv --version
# uv 0.5+
```

---

## 3. 克隆仓库

```powershell
git clone https://github.com/echoclass-team/EchoClass.git
cd EchoClass
```

---

## 4. 安装后端依赖

```powershell
cd backend
uv sync --extra dev
```

`uv sync` 会：

- 自动创建 `.venv\`（位于 `backend\.venv`）
- 按 `uv.lock` 装好运行时 + 开发依赖

主要依赖一览（来自 `backend\pyproject.toml`）：

- **Web**: `fastapi`, `uvicorn[standard]`, `python-multipart`
- **LLM**: `openai>=1.40` (OpenAI 兼容客户端), `tenacity` (重试)
- **Schema**: `pydantic>=2.8`
- **Prompt**: `jinja2`
- **RAG**: `chromadb>=0.5`, `pymupdf4llm>=0.0.17`
- **配置**: `python-dotenv`
- **dev**: `pytest>=8.3`, `pytest-asyncio>=0.24`, `httpx`

> 如果在 `chroma-hnswlib` 报 `error: Microsoft Visual C++ 14.0 or greater is required`，回到 [1.3 安装 MSVC Build Tools](#13-安装-msvc-build-tools关键)。

---

## 5. 配置环境变量

```powershell
Copy-Item .env.example .env
notepad .env
```

填入：

```ini
# 默认走华东师大 ChatECNU
# 获取 token：登录 https://chat.ecnu.edu.cn/html/ → 左下角头像 → 我的令牌
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
LLM_MODEL=ecnu-max

# CORS（前端 dev server）
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

> `.env` 已在 `.gitignore`，**绝对不要 commit**。
>
> 切 DeepSeek / Qwen 等其它 OpenAI 兼容后端只改 `OPENAI_BASE_URL` / `LLM_MODEL` 即可，业务代码无需改动。

### Windows 编码注意

`.env` 用 UTF-8 (无 BOM) 保存。VSCode / Notepad++ 默认即可；用系统记事本时**不要**保存为 ANSI / UTF-8 with BOM。

---

## 6. 运行单元测试（不消耗 API 配额）

```powershell
# backend\ 目录下
uv run pytest -q
```

预期（截至当前进度）：

```
142 passed in ~1s
```

测试用 mock 替代 LLM，**不会调外部网络**，可在无 token 环境下跑。

### 6.1 跑指定测试

```powershell
uv run pytest tests\test_student_stream.py -v       # 流式输出
uv run pytest tests\test_qa_session.py -v           # 1v1 答疑编排
uv run pytest tests\test_student_dialog.py -v       # 多轮对话 + [懂了] 标记
uv run pytest tests\test_student_questions.py -v    # 学生问题生成
uv run pytest -k "stream"                           # 关键字筛选
```

> PowerShell 既接受 `\` 也接受 `/` 作分隔符；下文一律用 `\` 与 Windows 习惯保持一致。

---

## 7. 真实 LLM 冒烟测试（消耗 API 配额）

需要 `.env` 里有效的 `OPENAI_API_KEY`。

### 7.1 1v1 答疑陪练交互 demo

```powershell
uv run python scripts\try_qa_session.py
# 默认: math_p3_fraction（小学中年级·分数）+ 2 学生 × 3 问题

# 切其它学段教案
uv run python scripts\try_qa_session.py --lesson math_h2_derivative --students 2 --questions 2
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

交互命令：

- `/resolve` — 把当前对话标为已解答
- `/abandon` — 放弃当前对话
- `/switch` — 切到下一个学生
- `/done` — 结束 session 并打印 summary

> Windows PowerShell 终端如果出现中文输出乱码，先执行 `chcp 65001` 切到 UTF-8 代码页。

### 7.2 教案 RAG 管线

```powershell
uv run python scripts\try_lesson_rag.py
# 解析 data\lesson_samples\ 下样例 PDF → LLM 抽取 LessonMeta → Chroma 索引
```

### 7.3 Persona 完整性校验（不调 LLM）

```powershell
uv run python scripts\validate_personas.py
```

---

## 8. 启动 FastAPI 开发服务器

```powershell
# backend\ 目录下
uv run uvicorn main:app --reload --port 8000
```

健康检查（新开一个 PowerShell 窗口）：

```powershell
Invoke-WebRequest http://localhost:8000/health | Select-Object -ExpandProperty Content
# {"status":"ok"}
```

API 文档自动生成：

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

---

## 9. 常见问题

### `uv : 无法将"uv"项识别为 cmdlet`

刚装完 uv 没重开终端，PATH 还没刷新。**关掉所有 PowerShell 窗口重开**即可；或手动：

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
```

### `error: Microsoft Visual C++ 14.0 or greater is required`

`chroma-hnswlib` 需要 C++ 编译器。回到 [1.3 安装 MSVC Build Tools](#13-安装-msvc-build-tools关键)。

### `uv sync` 卡在 `Resolving dependencies` 很久

国内网络访问 PyPI 慢。可以用清华镜像：

```powershell
# 临时
$env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
uv sync --extra dev

# 永久（用户级）
[Environment]::SetEnvironmentVariable("UV_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple", "User")
```

### PowerShell 执行脚本被禁

某些公司机器禁了 RemoteSigned 以下策略，导致 uv 安装脚本拒绝运行。临时放开当前会话：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 中文输出乱码（PowerShell / cmd）

```powershell
chcp 65001                    # 切到 UTF-8 代码页
$OutputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
```

或在系统设置中：**设置 → 时间和语言 → 语言和区域 → 管理语言设置 → 更改系统区域设置 → 勾选 "Beta：使用 Unicode UTF-8 提供全球语言支持"**，重启生效。

### 测试卡死或网络超时

本仓库所有 `tests\` 都是 mock，**不应**联网；如果卡住可能是 `chromadb` 的 telemetry。`.env` 加：

```ini
ANONYMIZED_TELEMETRY=False
```

### API Key 401 / 403

- token 是否过期（ChatECNU 控制台可重置）
- `OPENAI_BASE_URL` 末尾**带 `/v1`**：`https://chat.ecnu.edu.cn/open/api/v1`
- token 前后无空格、无引号

### `uv run` 报 `OSError: [WinError 1314] 客户端没有所需的特权`

某些 Windows 上 uv 试图建符号链接被拒。开启 [开发者模式](ms-settings:developers) 或用管理员身份运行 PowerShell。

---

## 10. 一行回归

```powershell
cd backend; uv sync --extra dev; uv run pytest -q
```

期望：`142 passed`。
