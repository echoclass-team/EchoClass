# Demo Checklist + 翻车预案

> **Issue**：#137 [W5][M3-C4] Pitch + Demo 脚本
> **配套**：[`5min.md`](./5min.md) §4 现场 demo · [`qa_preparation.md`](./qa_preparation.md)
> **验收线**（#137）：**全员走一遍 ≤ 10 分钟、无卡壳；翻车预案实测一次**

---

## 1. T-24h Checklist（演讲前一天）

> 全部 ✅ 后才能上场。**任何一项不过 = 启动 §3 翻车预案对应等级**。

### 1.1 数据层

- [ ] `data/demo_sessions/session_{good,mid,bad}.json` 三份文件存在且 JSON 合法
- [ ] `(cd backend && uv run python scripts/seed_demo.py --build)` 跑通，三份 JSON 重新生成无报错
- [ ] `(cd backend && uv run python scripts/seed_demo.py --reset)` 跑通，DB 中确认 demo user + 3 条 session 已入库
- [ ] `/sessions` 页面访问后**确实显示 3 条**，标题 / 时间 / 分数三列正确
- [ ] 点开 `session_bad` → `/qa/{id}/summary` 能看到 5 维评分卡 + evidence 片段 + FeedbackAgent 反馈

### 1.2 应用层

- [ ] reviewer_c 账号能登录（`Test@2026`）
- [ ] 整个 demo 路径走一遍（session 列表 → 进入 bad → 滚动看 evidence → 切 Feedback → ESC），**计时 90 s ± 5 s**
- [ ] 浏览器**已关闭其他 tab**、**已关闭通知**、**字号 ≥ 125%**（评委后排能看清）
- [ ] 网络：连接演讲场地 wifi 测一次；手机热点已 tethering 备好
- [ ] 后端 / 前端 / WS 三个进程在同一台电脑上**已启动且稳定 30 min 以上不重启**

### 1.3 物料层

- [ ] 演讲胶片 PDF 拷贝到讲台机 + USB
- [ ] [`30s.md`](./30s.md) / [`2min.md`](./2min.md) / [`5min.md`](./5min.md) 三份脚本打印成纸质 + 大字号
- [ ] [`qa_preparation.md`](./qa_preparation.md) 12 题 Q&A 卡片打印
- [ ] **demo 录屏备份 mp4**（90 s，已剪好）放在桌面 `_demo_backup.mp4`
- [ ] 计时器：手机倒计时 5:00 + 同伴举牌（4:30 / 4:50 / 5:00）

### 1.4 角色协同

- [ ] **演讲人**（C-Prod）：脚本默背 ≥ 3 次，§4 demo 闭眼能走完
- [ ] **后台保障**（B-Full）：现场坐前排，**手持 reset 命令**待命
- [ ] **答辩助攻**（A-Agent）：Q&A 段如涉及 Agent / RAG 技术细节，必要时**举手补充**（事先约定手势）

---

## 2. 现场 T-30min Checklist（开场前 30 分钟）

按顺序执行，**不要乱序**：

1. **接电源** + 关闭笔记本电池省电模式
2. **连场地 wifi**，浏览器访问 `http://localhost:3000/sessions` 确认能进
3. `(cd backend && uv run python scripts/seed_demo.py --reset)` **跑一次清空重灌** —— 确保 demo 状态全新
4. 访问 `/sessions`，确认 3 条 session 显示，**点开 session_bad 预热一下后端缓存**
5. ESC 回到 `/sessions` 列表页，**关闭浏览器其他所有 tab**
6. 投影器测试：把 `/sessions` 页面投到大屏，**蹲到最后一排**确认字号能看清
7. 打开 `_demo_backup.mp4` 在 VLC 里**预加载**（不播），万一翻车一键播放
8. 同伴在前排坐定，**举牌测试 + 暗号测试**

---

## 3. 翻车预案

> **金科玉律**：**绝不在评委面前 debug**。任何故障 → 立刻按对应等级降级 → demo 段结束后再处理。

### 3.1 等级与降级矩阵

| 等级 | 故障类型 | 降级动作 | 演讲口播补救 |
|---|---|---|---|
| **L0 · 轻微** | 单次响应慢 / loading 转圈 < 5 s | **不动**，继续讲 | 不补救 |
| **L1 · 中等** | 5–15 s 卡住 / 局部 UI 错位 | 切到下一段 demo 步骤跳过卡点 | "这一段我们的实时计算需要点时间，我先讲下一处" |
| **L2 · 严重** | WS 断开 / 5xx / 报错弹窗 | **ESC 回胶片** + 切到 [`5min.md`](./5min.md) §4 改用胶片讲 | "现场环境不太稳定，我用截图给大家看效果" |
| **L3 · 致命** | 后端进程挂 / 数据库丢 / 浏览器崩溃 | **立刻切 `_demo_backup.mp4`** | "我们提前录了一段，质量更稳，请看 90 秒" |

### 3.2 一键 rollback（手动步骤）

> 当 demo 数据被误改 / DB 状态污染时使用。**全部命令在 repo 根目录运行**。

```powershell
# 步骤 1：停止 backend（如在跑）
#   按 Ctrl+C 终止，或在另一个 terminal 找进程 kill

# 步骤 2：清空 + 重灌 demo seed
(cd backend && uv run python scripts/seed_demo.py --reset)

# 步骤 3：重启 backend（在仓库根目录）
(cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000)

# 步骤 4：刷新前端 /sessions，确认 3 条 demo session 重新出现
```

> ⏱️ 三步在 **2 分钟内** 完成。如果做不到 → **直接走 L3 切录屏**，不要纠缠。

### 3.3 极端兜底：完全无网络

| 场景 | 动作 |
|---|---|
| 场地 wifi 全挂 + 手机热点也连不上 | 跳过 §4 demo，直接 §4 改用截图叙述（讲 60 s 即可），用省下的 30 s 在 §5 多说一些用户测试细节 |
| 投影坏 | 站讲台中央 + 不切换胶片，**纯口述 5 min**——§3 教育学理论段是亮点段，重点讲它 |
| 同时多个评委打断追问超过 30 s | 说"这个问题我留到 Q&A 详细回答，先把核心机制讲完"，硬性回到主线 |

---

## 4. 全员走查（**#137 验收线**）

> 演讲前 **48 小时内** 必须走一次完整 ≤ 10 min（5 min 演讲 + 3 min Q&A 抽 2 题 + 翻车预案演练 1 次）。
> 任何一人卡壳 / 超时 / 翻车预案没演到 = 不通过 → 重排。

### 4.1 走查流程

| 步骤 | 时长 | 谁主导 | 通过标准 |
|---|---|---|---|
| 1. C-Prod 演讲 5 min | 5:00 | C | 时长 4:50–5:10、§4 demo ≤ 90 s、不卡壳 |
| 2. A/B 抽 [`qa_preparation.md`](./qa_preparation.md) **2 题**做 Q&A | 3:00 | A 或 B 提问 | C 答完每题 ≤ 75 s |
| 3. 翻车预案演练（**强制**） | 2:00 | B 中途拔网线触发 L2 | C 是否能正确切 ESC + 切胶片 + 口播补救 |

### 4.2 走查记录

> 每次走查填一行，**3 次全过**才算 #137 验收通过。

| # | 日期 | 走查时长 | §4 demo 用时 | 翻车演练等级 | 通过 | 备注 |
|---|---|---|---|---|---|---|
| 1 | _YYYY-MM-DD_ | _x:xx_ | _0:xx_ | L_x_ | ✅/❌ | _待填_ |
| 2 | _YYYY-MM-DD_ | _x:xx_ | _0:xx_ | L_x_ | ✅/❌ | _待填_ |
| 3 | _YYYY-MM-DD_ | _x:xx_ | _0:xx_ | L_x_ | ✅/❌ | _待填_ |

---

## 5. 截图 / 录屏素材清单（#137 验收第 6 项）

> 用于胶片 + B 站宣传 + Pitch 备份。**全部素材匿名化**（不含真实师范生姓名 / 学校）。

| # | 素材 | 路径 | 用途 | 状态 |
|---|---|---|---|---|
| 1 | `/sessions` 列表三条 demo | `docs/pitch/screenshots/sessions_list.png` | P2 闭环图右下角 | ⬜ |
| 2 | `session_bad` 5 维评分卡 | `docs/pitch/screenshots/eval_card.png` | P3 教育学机制 § 配图 | ⬜ |
| 3 | Evidence 引用片段 | `docs/pitch/screenshots/evidence.png` | §4 demo 第 30–60 s 配图 | ⬜ |
| 4 | FeedbackAgent 反馈卡 | `docs/pitch/screenshots/feedback.png` | §4 demo 第 60–80 s 配图 | ⬜ |
| 5 | 1v1 答疑流式 GIF | `docs/pitch/screenshots/streaming.gif` | §3 第二层迷思机制配图 | ⬜ |
| 6 | **完整 90 s demo mp4** | `_demo_backup.mp4`（不入库） | L3 翻车一键播 | ⬜ |
| 7 | _<#136 用户测试现场剪影>_ | `docs/pitch/screenshots/user_test.png` | §5 验证数据段 | ⬜（依赖 #136） |

> 截图工具建议：ShareX（Win） / CleanShot（Mac），统一 **1920×1080** + **白底 + 阴影**，方便胶片复用。

---

## 6. 收尾归档（演讲后 24h 内）

- [ ] 现场录屏归档至 `gdrive://EchoClass/pitch/{date}_{venue}/`
- [ ] 评委提问 + 回答整理成 **新 Q&A** 补到 [`qa_preparation.md`](./qa_preparation.md)（标记 `from-{venue}` tag）
- [ ] 翻车点 / 卡壳点更新到本文件 §3.1 矩阵作为下次输入
- [ ] 截图素材按 §5 命名规范 commit 到 `docs/pitch/screenshots/`
