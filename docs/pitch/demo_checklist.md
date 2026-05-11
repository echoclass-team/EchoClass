# Demo Checklist + 翻车预案

配套 [`5min.md`](./5min.md) §4 · [`qa_preparation.md`](./qa_preparation.md)。#137 验收：全员走一遍 ≤ 10 分钟无卡壳 + 翻车预案实测一次。

## 1. T-24h

任何一项不过就启动 §3 对应等级降级。

### 数据层

- [ ] `data/demo_sessions/session_{good,mid,bad}.json` 存在且 JSON 合法
- [ ] `(cd backend && uv run python scripts/seed_demo.py --build)` 跑通
- [ ] `(cd backend && uv run python scripts/seed_demo.py --reset)` 跑通，demo user + 3 条 session 已入库
- [ ] `/sessions` 确实显示 3 条（标题 / 时间 / 分数三列正确）
- [ ] 点 `session_bad` → `/qa/{id}/summary` 能看到 5 维评分卡 + evidence + FeedbackAgent 反馈

### 应用层

- [ ] reviewer_c 能登录（`Test@2026`）
- [ ] 完整 demo 路径走一遍，计时 90 s ± 5 s
- [ ] 浏览器关掉其他 tab / 关通知 / 字号 ≥ 125%（后排能看清）
- [ ] 场地 wifi 测一次 + 手机热点 tethering 备好
- [ ] backend / frontend / WS 启动后稳定 30+ 分钟不重启

### 物料

- [ ] 胶片 PDF 拷到讲台机 + USB
- [ ] `30s.md` / `2min.md` / `5min.md` 大字号纸质稿
- [ ] `qa_preparation.md` 12 题卡片
- [ ] **demo 录屏备份 mp4**（90s 剪好）放桌面 `_demo_backup.mp4`
- [ ] 计时器：手机倒计时 5:00 + 同伴举牌（4:30 / 4:50 / 5:00）

### 协同

- [ ] 演讲人（C）：脚本默背 ≥ 3 次，§4 闭眼能走完
- [ ] 后台（B）：前排坐定，手持 reset 命令
- [ ] 答辩助攻（A）：Q&A 涉及 Agent / RAG 技术细节时举手补充，手势事先约定

## 2. T-30min 现场

按顺序，不要乱：

1. 接电源，关电池省电模式
2. 连场地 wifi，访问 `http://localhost:3000/sessions` 确认能进
3. `(cd backend && uv run python scripts/seed_demo.py --reset)` 清空重灌
4. 进 `/sessions`，点 `session_bad` 预热后端缓存
5. ESC 回列表页，关其他 tab
6. 投影到大屏，蹲到最后一排确认字号
7. VLC 预加载 `_demo_backup.mp4`（不播）
8. 同伴前排坐定，举牌 + 暗号测试

## 3. 翻车预案

**金科玉律：绝不在评委面前 debug**。故障立刻按等级降级，demo 段结束再处理。

### 3.1 降级矩阵

| 等级 | 故障 | 动作 | 口播 |
|---|---|---|---|
| L0 轻微 | 单次响应 < 5 s | 不动 | 不补救 |
| L1 中等 | 5-15 s 卡 / 局部 UI 错位 | 跳下一步跳过卡点 | "这里实时计算需要点时间，我先讲下一处" |
| L2 严重 | WS 断开 / 5xx / 报错弹窗 | ESC 回胶片，改用胶片讲 | "现场环境不太稳定，我用截图给大家看效果" |
| L3 致命 | 后端挂 / DB 丢 / 浏览器崩 | 切 `_demo_backup.mp4` | "我们提前录了一段，质量更稳，请看 90 秒" |

### 3.2 一键 rollback（手动）

demo 数据污染时用。全部在 repo 根目录运行。

```powershell
# 1. Ctrl+C 停 backend
# 2. 清空重灌
(cd backend && uv run python scripts/seed_demo.py --reset)
# 3. 重启 backend
(cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000)
# 4. 刷新前端 /sessions 确认 3 条回来
```

三步 2 分钟内完成。做不到直接走 L3 切录屏，不要纠缠。

### 3.3 极端兜底

| 场景 | 动作 |
|---|---|
| wifi + 热点都挂 | 跳 §4 demo，改用截图讲 60s，省下的 30s 给 §5 |
| 投影坏 | 讲台中央纯口述 5min，重点讲 §3 |
| 多评委打断 > 30s | "这个问题留 Q&A 详谈，先把核心机制讲完"，硬回主线 |

## 4. 全员走查（#137 验收）

演讲前 48h 内必跑一次完整 ≤ 10min：5min 讲 + Q&A 抽 2 题 + 翻车演练。任何一人卡壳 / 超时 / 翻车没演到都要重排。

### 流程

| 步 | 时长 | 主导 | 通过标准 |
|---|---|---|---|
| C 演讲 5min | 5:00 | C | 4:50-5:10、§4 ≤ 90s、不卡壳 |
| A/B 抽 `qa_preparation.md` 2 题 | 3:00 | A 或 B 提问 | 每题 ≤ 75s |
| 翻车演练（强制） | 2:00 | B 拔网线触发 L2 | C 能正确 ESC + 切胶片 + 口播补救 |

### 走查记录（3 次全过才算验收）

| # | 日期 | 总时长 | §4 用时 | 翻车等级 | 通过 | 备注 |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |

## 5. 截图 / 录屏素材（#137 验收第 6 项）

全部匿名化，不含真实师范生姓名 / 学校。

| # | 素材 | 路径 | 用途 | 状态 |
|---|---|---|---|---|
| 1 | `/sessions` 列表 | `screenshots/sessions_list.png` | P2 右下 |  |
| 2 | `session_bad` 5 维评分卡 | `screenshots/eval_card.png` | P3 配图 |  |
| 3 | Evidence 片段 | `screenshots/evidence.png` | §4 30-60s |  |
| 4 | FeedbackAgent 反馈卡 | `screenshots/feedback.png` | §4 60-80s |  |
| 5 | 1v1 答疑流式 GIF | `screenshots/streaming.gif` | §3 迷思机制 |  |
| 6 | 完整 90s demo mp4 | `_demo_backup.mp4`（不入库） | L3 一键播 |  |
| 7 | #136 测试现场剪影 | `screenshots/user_test.png` | §5（依赖 #136） |  |

工具：ShareX（Win）/ CleanShot（Mac）。统一 1920×1080 + 白底阴影。

## 6. 演讲后 24h 归档

- [ ] 现场录屏传 `gdrive://EchoClass/pitch/{date}_{venue}/`
- [ ] 评委追问 + 临场答案补到 `qa_preparation.md`（标 `from-{venue}` tag）
- [ ] 翻车点更新到 §3.1 矩阵
- [ ] 截图按 §5 命名规范 commit 到 `screenshots/`
