# EchoClass Backend

师范生 1v1 答疑陪练系统的后端。

Python 3.11+ · FastAPI · ChatECNU ecnu-max · Chroma · Jinja2

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
uv run pytest                                                       # 全部单元 / 集成测试（mock LLM，不走网络）
uv run python scripts/try_qa_session.py --students 2 --questions 3  # 真实 LLM 端到端 demo
```

## 目录结构

```
backend/
├── agents/                 # StudentAgent — 1v1 答疑陪练的虚拟学生 Agent
│   └── student.py          #   · generate_questions（宽生成 + self-check + 多样性筛选）
│                           #   · respond_in_dialog（多轮对话 + [懂了] 标记）
├── services/               # 业务编排层
│   └── qa_session.py       #   QASession — 学生提问队列与 1v1 对话状态机
├── rag/                    # 教案解析 + 检索 + 知识库加载
│   ├── parser.py           #   PDF / MD / TXT → 纯文本（pymupdf4llm）
│   ├── extractor.py        #   LLM 抽取 LessonMeta（subject/grade/topic/objectives/key_points/difficult_points）
│   ├── indexer.py          #   500 token 切片 + Chroma 向量化
│   ├── misconceptions.py   #   学科迷思概念库（按 stage/subject/key_point 匹配）
│   └── qa_examples.py      #   6 学段 few-shot 范例集合（按 persona 自动挑选）
├── llm/                    # LLMClient 封装（chat / stream + tenacity 重试 + token 日志）
├── prompts/                # Jinja2 Prompt 模板
│   ├── student_ask.j2      #   学生根据教案生成问题（含同学段 few-shot）
│   ├── student_chat.j2     #   学生 1v1 多轮对话（含 [懂了] 自我宣称解决）
│   ├── student_check.j2    #   二阶段 self-check 评分
│   └── extractor.j2        #   教案元数据抽取
├── schemas/                # Pydantic 模型
│   ├── stage.py            #   StageProfile（学段认知特征）
│   ├── student.py          #   Persona / ClassroomContext
│   ├── lesson.py           #   LessonMeta / LessonRecord / RecommendedPersonasData
│   ├── question.py         #   StudentQuestion（含 self_score / category / difficulty / linked_*）
│   ├── dialog.py           #   DialogSession / DialogMessage / DialogReplyResult
│   └── misconception.py    #   Misconception
├── api/                    # REST 路由（B 端领地）
├── db/                     # SQLite 持久化（B 端规划中）
├── scripts/                # 冒烟测试与 CLI demo
│   ├── try_qa_session.py   #   1v1 答疑陪练交互 demo（真实 LLM）
│   ├── try_lesson_rag.py   #   教案 RAG 管线（解析 → 抽取 → 索引）
│   └── validate_personas.py #  18 个 persona JSON 完整性校验（不调 LLM）
├── tests/                  # pytest 单元 / 集成测试
├── main.py                 # FastAPI 入口
└── pyproject.toml
```

所有权细则见根目录 [`docs/roles.md`](../docs/roles.md)。

## 关键链路

### 学生提问

```
StudentAgent.generate_questions(lesson_meta, count=3)
  ├─ 宽生成阶段（1st LLM）
  │    prompt = student_ask.j2  ← 注入同学段 2 个 ask 范例
  │    输出：count + overshoot 个候选 JSON
  ├─ 解析校验：构造 list[StudentQuestion]
  ├─ self-check 阶段（2nd LLM，可选）
  │    prompt = student_check.j2
  │    输出：[{index, score, keep, reason}, ...]
  │    剔除 keep=false / score<40
  └─ 多样性筛选：按 self_score 降序 + category 多样性 → top N
```

### 1v1 对话

```
QASession.send_teacher_message(dialog_id, text)
  └─ StudentAgent.respond_in_dialog(question, teacher_utterance, history)
       prompt = student_chat.j2  ← 注入同学段 1 个 chat 范例
       输出：纯文本回应；末尾 [懂了] 标记触发 self_resolved
```

## 调试 1v1 答疑陪练

```bash
# 默认：math_p3_fraction（小学中年级·分数）+ 2 学生 × 3 问题
uv run python scripts/try_qa_session.py

# 指定其他学段示例教案
uv run python scripts/try_qa_session.py --lesson math_h2_derivative --students 2 --questions 2
```

可选学段：

| key | 学段 | 示例话题 |
|---|---|---|
| `math_p2_addition` | 小学低年级 | 两位数加法 |
| `math_p3_fraction` | 小学中年级 | 分数的初步认识 |
| `math_p5_area` | 小学高年级 | 平行四边形面积 |
| `math_j3_quadratic` | 初中高年级 | 二次函数 |
| `math_h2_derivative` | 高中 | 导数的概念 |
| `physics_j2_force` | 初中低年级 | 力的概念 |

交互命令：`/resolve` 标记已解答 · `/abandon` 放弃 · `/switch` 切换学生 · `/done` 结束 session。
