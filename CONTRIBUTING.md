# 贡献指南 · EchoClass

欢迎加入 EchoClass！本文档是我们三人协作的"交通规则"，**请在第一次 commit 前通读一遍**。

---

## 1. 分支策略（GitHub Flow 简化版）

- `main` 永远保持可运行状态，**禁止直接 push**
- 每个任务开一个新分支，完成后走 PR 合并回 `main`

### 分支命名

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/` | 新功能 | `feat/director-agent` |
| `fix/` | 修 bug | `fix/websocket-disconnect` |
| `docs/` | 文档 | `docs/update-readme` |
| `chore/` | 依赖、配置、杂项 | `chore/bump-langgraph` |
| `refactor/` | 重构（无功能变化） | `refactor/extract-persona` |

---

## 2. 日常工作流

### 2.1 开始新任务

```bash
git checkout main
git pull origin main
git checkout -b feat/你的任务名
```

### 2.2 提交代码

```bash
git add .
git commit -m "feat: 简短描述"
git push -u origin feat/你的任务名   # 首次 push
```

### 2.3 开 Pull Request

1. 打开仓库页面，点 **Compare & pull request**
2. 填写 PR 描述（模板会自动载入）
3. 指定一位队友为 **Reviewer**
4. 等待 approve 后点 **Squash and merge**
5. 合并完成后删除该分支

### 2.4 每天开工前

```bash
git checkout main && git pull
git checkout feat/你的分支
git merge main   # 同步 main 的最新改动到自己分支
```

---

## 3. Commit Message 规范（Conventional Commits）

格式：`<type>: <简短描述（<= 50 字）>`

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 文档 |
| `style` | 格式（不影响逻辑） |
| `refactor` | 重构 |
| `test` | 测试 |
| `chore` | 构建 / 依赖 / 工具链 |

**好例子**：
```
feat: 添加 Director Agent 调度逻辑
fix: 修复多学生同时发言时的竞态问题
docs: 补充 RAG 模块的使用说明
```

---

## 4. Pull Request 规则

- **每个 PR 必须有至少 1 位队友 approve 才能合并**（main 分支保护已开启）
- PR 标题同样遵循 Conventional Commits 格式
- PR 描述请说明：**做了什么 / 为什么 / 如何验证**
- 勾选 PR 模板中的自查清单
- 合并策略统一使用 **Squash and merge**，保持 main 提交历史整洁

---

## 5. Code Review 规范

**作为 Reviewer**：
- 24 小时内给出反馈（哪怕只是"先看不完，明天回"）
- 对事不对人：评论具体代码行，不做人身评价
- 有疑问标 `question`，有建议标 `suggestion`，必须修改标 `must-fix`

**作为 PR 作者**：
- 回应每一条 review comment
- 修改后 re-request review，不要静默合并

---

## 6. 分工与目录约定

| 同学 | 主要目录 | 主分支前缀 |
|------|---------|------------|
| A (Agent 工程师) | `backend/agents/` | `feat/agent-*` |
| B (全栈工程师)   | `frontend/`, `backend/api/` | `feat/fe-*`, `feat/api-*` |
| C (产品/评测)    | `backend/eval/`, `data/`, `docs/` | `feat/eval-*`, `docs/*` |

**跨领域文件**（`README.md`、`backend/main.py`、依赖文件等）改动前请在群里同步。

---

## 7. 合并冲突处理

```bash
# 发生冲突时
git status                      # 查看冲突文件
# 手动编辑文件，删除 <<<<<<<  =======  >>>>>>>
git add <冲突文件>
git commit                      # 完成合并
git push
```

**原则**：冲突不确定时，叫对应队友一起看，**不要瞎猜**。

---

## 8. 敏感信息

- **严禁** commit API Key、账号密码、`.env` 文件
- 使用 `.env.example` 作为模板，真实密钥走本地 `.env`（已在 `.gitignore`）
- 不慎提交后立即旋转密钥并联系队友清理历史

---

## 9. 遇到问题？

- 先看本文档 + README
- 在 Issues 里搜一下
- 队内群里问
- 提 Issue（用对应模板）
