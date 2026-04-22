# EchoClass

> AI-powered virtual classroom for pre-service teachers.
> 师范生虚拟学生陪练 Agent —— 让每位未来的老师都有无限次"试讲"机会。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

---

## ✨ 项目简介

EchoClass 是一个基于多智能体的"虚拟课堂"系统：师范生上传教案后，系统生成多位性格/学力各异的虚拟学生（由 LLM 扮演），进行沉浸式课堂演练，并在课后输出量化的教学能力诊断报告。

核心亮点：

- **Director Agent 调度**：避免多学生同时发言的混乱，按真实课堂节奏触发互动
- **基于教育学理论的学生人设**：皮亚杰认知阶段 + 学科常见迷思概念库，错得真实
- **多维诊断报告**：教学设计 / 课堂互动 / 语言表达 / 课堂管理（参考 Flanders 互动分析）

## 🏗️ 技术栈

- **LLM**：DeepSeek-V3 / Qwen2.5
- **Agent 框架**：LangGraph
- **后端**：FastAPI + WebSocket
- **前端**：Next.js 14 + shadcn/ui + Vercel AI SDK
- **向量库**：Chroma
- **ASR/TTS**：阿里云 Paraformer / CosyVoice

## 📁 目录结构（规划中）

```
EchoClass/
├── backend/        # FastAPI + LangGraph
├── frontend/       # Next.js
├── data/           # 迷思概念库、样例教案
├── docs/           # 立项书、答辩材料
└── README.md
```

## 👥 团队分工

| 角色 | 负责人 | 主要任务 |
|------|--------|---------|
| Agent 工程师 | TBD | Director + 学生 Agent、LangGraph 状态机 |
| 全栈工程师   | TBD | 前端课堂 UI、WebSocket、RAG |
| 产品/评测    | TBD | 人设设计、评估 Prompt、Demo 与答辩 |

## 📅 里程碑

- [ ] Week 1：脚手架 + 单学生 Agent + 教案解析 Demo
- [ ] Week 2：Director + 多学生并发 + 前端课堂 UI
- [ ] Week 3：评估模块 + 报告 + 小学数学迷思库（50 条）
- [ ] Week 4：打磨 + Demo 视频 + 答辩 PPT

## 📜 License

MIT
