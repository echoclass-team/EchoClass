# Pitch & Demo 资料

#137 · C-Prod · 学术路线（答辩 / 毕设 / 竞赛）· 2026-05-08

## 文件

| 文件 | 用途 |
|---|---|
| [`30s.md`](./30s.md) | 电梯版 |
| [`2min.md`](./2min.md) | 评委版 · 5 段 |
| [`5min.md`](./5min.md) | 完整 demo + 答辩（5min 讲 + 3-5min Q&A） |
| [`demo_checklist.md`](./demo_checklist.md) | 演讲前 24h checklist + 翻车预案 + rollback |
| [`qa_preparation.md`](./qa_preparation.md) | 12 题 Q&A |

## `_<待回填>_` 字段

依赖 #136。W2-W3 测试跑完后统一回填：

- SUS 均值、NPS
- 测试场次、学段覆盖
- 师范生原话引语
- T1-T4 完成率
- 5 维评分反馈结论

## 外部引用

| 路径 | 用处 |
|---|---|
| `data/demo_sessions/session_{good,mid,bad}.json` | #128 demo seed |
| `backend/scripts/seed_demo.py` | `--build` / `--reset` |
| `../rubric_v0.md` | 5 维 Rubric 设计依据 |
| `../proposal.md` | 理论框架（长答辩可引） |
| `../user_test_plan.md` | 验证方法学 |
| `../user_test_report.md` | 实证数据（待 #136 回填） |

## 核心叙事三层

- 痛点：师范生答疑练习缺真学生 —— 同伴扮演没深度 / 实习前没被真追问过
- 方案：1v1 虚拟学生答疑陪练（学段 × 18 人设 × 21 迷思库）
- 机制：皮亚杰（防 LLM 超模）+ 维果茨基脚手架（不讲到点不说"懂了"）+ 结构化迷思库（typical_error / intervention_hint）
