# EchoClass Backend

Python 3.11+ · FastAPI · ChatECNU ecnu-max · Chroma · Jinja2

> ⚠️ 后端核心已从"虚拟课堂回合制状态机"转型为 **1v1 师范生答疑陪练**。
> 详见根目录 [`docs/PIVOT.md`](../docs/PIVOT.md)；旧 `DirectorAgent` /
> `ClassroomGraph` 已归档至 `backend/legacy/` 不再 CI。

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

# 4. 启动开发服务器（B 端 REST 用）
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
uv run pytest                                              # 全部 136 条单元 / 集成测试（mock LLM，不走网络）
uv run python scripts/try_qa_session.py --students 2 --questions 3  # 真实 LLM 端到端 demo
```

> 注：`backend/legacy/tests/` 已随产品转型清理；`legacy/` 下的代码 **不再保证可运行**。

## 目录结构

```
backend/
├── agents/                 # ✅ StudentAgent — 1v1 答疑陪练
│   └── student.py          #   · generate_questions（宽生成 + self-check + 多样性筛选）
│                           #   · respond_in_dialog（多轮对话 + [懂了] 标记）
├── services/               # ✅ QASession orchestrator（替代旧 ClassroomGraph）
│   └── qa_session.py       #   · spawn / next_pending / send_teacher_message / mark_resolved / summary
├── rag/                    # ✅ 教案解析 + 检索 + 知识库加载
│   ├── parser.py           #   PDF / MD / TXT → 纯文本（pymupdf4llm）
│   ├── extractor.py        #   LLM 抽取 LessonMeta（subject/grade/topic/objectives/key_points/difficult_points）
│   ├── indexer.py          #   500 token 切片 + Chroma 向量化
│   ├── misconceptions.py   #   学科迷思概念库（按 stage/subject/key_point 匹配）
│   └── qa_examples.py      #   6 学段 few-shot 范例集合（按 persona 自动挑选）
├── llm/                    # ✅ LLMClient 封装（chat / stream + tenacity 重试 + token 日志）
├── prompts/                # ✅ Jinja2 Prompt 模板
│   ├── student_ask.j2      #   学生根据教案生成问题（含同学段 few-shot）
│   ├── student_chat.j2     #   学生 1v1 多轮对话（含 [懂了] 标记）
│   ├── student_check.j2    #   二阶段 self-check 评分
│   └── extractor.j2        #   教案元数据抽取
├── schemas/                # ✅ Pydantic 模型
│   ├── stage.py            #   StageProfile（学段认知特征）
│   ├── student.py          #   Persona / ClassroomContext
│   ├── lesson.py           #   LessonMeta / LessonRecord / RecommendedPersonasData
│   ├── question.py         #   StudentQuestion（含 self_score / category / difficulty / linked_*）
│   ├── dialog.py           #   DialogSession / DialogMessage / DialogReplyResult
│   └── misconception.py    #   Misconception
├── api/                    # REST 路由（B 端领地）
├── db/                     # SQLite 持久化（B 端规划中）
├── legacy/                 # 旧课堂回合制架构归档（CI 不收，仅供回顾）
├── scripts/                # ✅ 冒烟测试与 CLI demo
│   ├── try_qa_session.py   #   1v1 答疑陪练交互 demo（真实 LLM）
│   ├── try_lesson_rag.py   #   教案 RAG 管线（解析 → 抽取 → 索引）
│   └── validate_personas.py #  18 个 persona JSON 完整性校验（不调 LLM）
├── tests/                  # ✅ pytest 单元 / 集成测试（136 条全绿）
├── main.py                 # FastAPI 入口
└── pyproject.toml
```

所有权细则见根目录 [`docs/roles.md`](../docs/roles.md)；产品转型决策见
[`docs/PIVOT.md`](../docs/PIVOT.md)。

## 调试 1v1 答疑陪练

```bash
# 默认：math_p3_fraction（小学中年级·分数）+ 2 学生 × 3 问题
uv run python scripts/try_qa_session.py

# 指定其他学段示例教案
uv run python scripts/try_qa_session.py --lesson math_h2_derivative --students 2 --questions 2

# 可选学段：math_p2_addition / math_p3_fraction / math_p5_area
#         / math_j3_quadratic / math_h2_derivative / physics_j2_force
```

交互命令：`/resolve` 标记已解答 · `/abandon` 放弃 · `/switch` 切换学生 · `/done` 结束 session。
