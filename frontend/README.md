# EchoClass Frontend

## 启动

先将 `.env.local.example` 复制为 `.env.local`，再按需调整环境变量。
其中 `NEXT_PUBLIC_API_BASE` 默认指向 `http://localhost:8000`。

```bash
npm run dev
```

默认访问 `http://localhost:3000`。

## 当前范围

- `lessons`：教案占位页
- `sessions`：会话占位页
- `src/lib`：API 基础封装与环境读取

## 暂未接入

- 教案上传、列表、配置
- 会话创建、实时课堂事件、互动面板
- 后端业务接口联调

## 建议接入顺序

1. 教案上传与列表
2. 会话创建与详情
3. 实时课堂事件
4. 互动面板与状态同步
