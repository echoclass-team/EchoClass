# EchoClass W1 后端阶段性测试指引（给队友）

> 目标：验证 `main` 分支上 **后端脚手架 + LLMClient + ChatECNU 集成 + StudentAgent 原型** 都正常。
> 预计耗时 15 分钟。

---

## 1. 拿自己的 ChatECNU API Key（必须）

每人用自己的账号：

1. 浏览器打开 https://chat.ecnu.edu.cn/html/
2. 用华东师大统一认证登录
3. 左下角头像 → **我的令牌** → 复制令牌（形如 `sk-xxxxxxxx...`）

**不要分享你的令牌**；泄露了就在"我的令牌"页面撤销重建。

---

## 2. 拉最新代码

```bash
git checkout main
git pull origin main
```

确认最新 commit 是 `50653c6 chore: 默认 LLM 后端切为 ChatECNU (华东师大大模型) (#43)`（或更新）。

---

## 3. 装 uv（首次才需要）

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 新终端或：source $HOME/.local/bin/env
uv --version
```

### Windows（PowerShell）

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# 装完重开 PowerShell
uv --version
```

> 若 `irm ... | iex` 被拒：管理员 PowerShell 跑 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## 4. 同步 Python 依赖

```bash
cd backend
uv sync --extra dev
```

第一次会装 ~100 个包，约 1-2 分钟。

---

## 5. 配置 .env

### macOS / Linux

```bash
cp .env.example .env
# 用编辑器打开 .env，把 OPENAI_API_KEY 改成你自己的 ChatECNU 令牌
```

### Windows（PowerShell）

```powershell
Copy-Item .env.example .env
notepad .env
```

确认最后是这样（把 `你的令牌` 替换成实际值）：

```
OPENAI_API_KEY=sk-你的令牌
OPENAI_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
LLM_MODEL=ecnu-max
```

---

## 6. 核心验证

### 6.1 跑单元测试（不走网络）

```bash
uv run pytest -v
```

**预期**：`40 passed`（含 StudentAgent 的 31 条测试）

### 6.2 跑 FastAPI `/health`

```bash
uv run uvicorn main:app --port 8000
```

**另开一个终端**（保留上面那个不动）：

```bash
# macOS / Linux
curl http://localhost:8000/health

# Windows PowerShell
Invoke-RestMethod http://localhost:8000/health
# 或：curl.exe http://localhost:8000/health
```

**预期**：`{"status":"ok"}`，HTTP 200

回上一个终端按 `Ctrl+C` 停服务。

### 6.3 打真 ChatECNU `ecnu-max`（消耗少量 tokens）

把下面脚本保存为 `/tmp/try_llm.py`（Mac）或 `$env:TEMP\try_llm.py`（Win）：

```python
import asyncio, logging
from pathlib import Path
from dotenv import load_dotenv

for p in [Path.cwd() / ".env", Path(__file__).parent / ".env"]:
    if p.exists():
        load_dotenv(p); break

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from llm.client import LLMClient

async def main():
    c = LLMClient()
    print(f"→ base_url={c.base_url} model={c.model}")

    print("\n=== chat ===")
    r = await c.chat([{"role": "user", "content": "用一句话介绍你自己"}], max_tokens=100)
    print("回复:", r.choices[0].message.content)

    print("\n=== stream ===")
    async for chunk in c.stream([{"role": "user", "content": "从1数到5，只输出数字"}], max_tokens=50):
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()

asyncio.run(main())
```

在 `backend/` 目录下运行：

```bash
# macOS / Linux
uv run python /tmp/try_llm.py

# Windows PowerShell
uv run python $env:TEMP\try_llm.py
```

**预期输出**：

```
→ base_url=https://chat.ecnu.edu.cn/open/api/v1 model=ecnu-max

=== chat ===
... HTTP Request: POST .../chat/completions "HTTP/1.1 200 OK"
... llm.chat model=ecnu-max prompt_tokens=16 completion_tokens=XX
回复: 我是 Qwen3.5，...

=== stream ===
... HTTP Request: POST .../chat/completions "HTTP/1.1 200 OK"
1
2
3
4
5... llm.stream model=ecnu-max prompt_tokens=XX completion_tokens=10
```

### 6.4 测试 StudentAgent + 人设联调（真实 API，消耗少量 tokens）

脚本会自动加载 `data/personas/` 下的 **6 个学生人设 JSON**，逐个调用真实 API 验证。

在 `backend/` 目录下运行：

```bash
uv run python scripts/try_student_agent.py
```

**预期输出**（内容每次不完全相同，但结构一致）：

```
📂 加载了 6 个人设（来自 data/personas/）

✅ LLMClient 初始化成功 (model=ecnu-max)
📡 base_url=https://chat.ecnu.edu.cn/open/api/v1

============================================================
👤 张雨欣（J1 中等）— 七年级活跃女生，爱抢答爱表现，热情有余严谨不足
   💬 口头禅: 老师老师！我来我来！

   intent:  answer_question
   content: （用口头禅开头，大致对但不严谨）
   emotion: 兴奋

============================================================
👤 林小雨（P3 薄弱）— 三年级基础薄弱女生，缺乏自信怕提问，需要耐心鼓励
   💬 口头禅: 嗯……好像是这样的吧？

   intent:  answer_question
   content: （模糊/不正确的回答，可能犯"分子加分子、分母加分母"的典型错误）
   emotion: 紧张

...（共 6 个学生）

🎉 全部测试通过！所有人设均正常响应。
```

**怎么看结果**：

| 人设 | 类型 | 应该怎样 |
|------|------|---------|
| **张雨欣** J1 中等 | 活跃抢答 | 用口头禅，凭直觉，不严谨 |
| **李文博** J2 优秀 | 内向学霸 | 回答正确但表述简略、犹豫 |
| **刘思琪** J2 中等 | 跑偏型 | 联想发散，可能从分数聊到宇宙 |
| **林小雨** P3 薄弱 | 薄弱怕错 | 小声、不确定，犯典型迷思概念错误 |
| **陈思远** P3 优秀 | 学霸型 | 准确完整，过度自信 |
| **王浩然** P4 中等 | 走神型 | 可能 off_topic，讲着讲着就跑了 |

只要 6 个人设的 `intent` / `content` / `emotion` **符合上述特征**（口头禅、迷思概念、说话风格有体现），就说明联调成功。

---

## 7. 验收清单

跑完后对照打勾：

- [ ] `uv run pytest` → `45 passed`
- [ ] `curl /health` 返回 `{"status":"ok"}`
- [ ] chat 能收到 ChatECNU 的回复
- [ ] stream 能逐字输出 `1 2 3 4 5`
- [ ] 日志打印了 `model=ecnu-max prompt_tokens=... completion_tokens=...`
- [ ] StudentAgent 6 个人设回复符合人设特征（口头禅、迷思概念有体现）

有任何一项失败，在群里发**完整报错 + 你在哪一步**，我们一起看。

---

## 常见坑

| 报错 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'llm.client'` | 不在 `backend/` 目录下跑 | `cd backend` 后再跑 |
| `OPENAI_API_KEY is required` | `.env` 没配或没被读到 | 检查 `backend/.env` 存在且格式正确（无引号、无空格） |
| `401 Unauthorized` | API key 错 / 没授权 `ecnu-max` | 回 ChatECNU "我的令牌" 重新复制 key |
| `curl` 输出格式奇怪（Win） | PS 里 `curl` 是别名 | 用 `curl.exe` 或 `Invoke-RestMethod` |
| 端口 8000 被占 | 其它进程占用 | 换端口 `--port 8001` |
| `uv sync` 卡在某个包 | 镜像慢 | 配 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` |
