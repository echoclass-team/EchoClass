"""Pydantic 数据模型模块。

当前包含：
- schemas.student：Persona / ClassroomContext / load_personas()
- schemas.stage：StageProfile / load_stage_profiles
- schemas.lesson：LessonMeta / LessonRecord / RecommendedPersonasData
- schemas.misconception：Misconception
- schemas.question：StudentQuestion（含 self_score / category / difficulty / linked_*）
- schemas.dialog：DialogSession / DialogMessage / DialogReplyResult / DialogStatus / StudentStreamEvent
- schemas.ws_events：QA 答疑陪练 WebSocket 协议事件（WsClientEvent / WsServerEvent 等）
"""
