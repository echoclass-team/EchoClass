"""Agent 模块 — 师范生 1v1 答疑陪练的虚拟学生 Agent。

提供 ``StudentAgent``：
  · ``generate_questions(lesson_meta)`` — 根据人设 + 教案主动生成会问老师的问题
    （含宽生成 + 二阶段 self-check + 类别多样性筛选）
  · ``respond_in_dialog(question, ...)`` — 多轮 1v1 对话中的学生回应
"""
