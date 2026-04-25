"""Agent 模块。

当前包含：
- StudentAgent：1v1 答疑陪练中的虚拟学生角色。
  · ``generate_questions(lesson_meta)`` — 根据人设 + 教案主动生成问题
    （含宽生成 + 二阶段 self-check + 类别多样性筛选）
  · ``respond_in_dialog(question, ...)`` — 多轮 1v1 对话回应

老课堂回合制 ``DirectorAgent`` / ``ClassroomGraph`` 已随产品转型归档至
``backend/legacy/``，详见 ``docs/PIVOT.md``。
"""
