#!/usr/bin/env python3
"""QASession 真实 LLM 交互式 demo。

跑通 1v1 答疑陪练完整闭环：
1. 加载示例教案 + 推荐学生组
2. 让每个学生 agent 真实调 LLM 生成自己想问的问题
3. CLI 列出问题队列，老师选择某个进入 1v1 对话
4. 多轮对话；学生可能在末尾输出 [懂了] 标记 → 提示老师确认
5. 老师可选择"已解答"、"放弃"或"切换学生"
6. 退出时打印 session summary

用法（在 backend/ 下执行）::

    uv run python scripts/try_qa_session.py
    uv run python scripts/try_qa_session.py --lesson math_p3_fraction --students 2 --questions 2

特殊命令（在对话中）：
    /resolve     标记为已解答（teacher_marked）
    /abandon     放弃此问题
    /switch      切换到其他学生（保留当前进度，可后续回来）
    /done        结束整个 session
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.lesson import LessonMeta
from schemas.stage import load_stage_profile_by_id
from schemas.student import ClassroomContext, load_personas
from services.qa_session import QASession

LESSON_SAMPLES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "lesson_samples"
)

# (lesson_key, stage_id) 预设
PRESETS = {
    "math_p2_addition": "p_lower",
    "math_p3_fraction": "p_middle",
    "math_p5_area": "p_upper",
    "math_j3_quadratic": "j_lower",
    "math_h2_derivative": "h",
    "physics_j2_force": "j_lower",
}


def _load_lesson_meta(lesson_key: str) -> LessonMeta:
    path = LESSON_SAMPLES_DIR / f"{lesson_key}.meta.md"
    if not path.exists():
        raise FileNotFoundError(f"未找到 {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} 缺 JSON 块")
    data = json.loads(match.group(1))
    return LessonMeta(
        subject=data.get("subject", ""),
        grade=data.get("grade", ""),
        topic=data.get("topic", ""),
        objectives=data.get("objectives", []),
        key_points=data.get("key_points", []),
        difficult_points=data.get("difficult_points", []),
    )


def _print_lesson(lesson: LessonMeta) -> None:
    print("=" * 72)
    print(f"📘 {lesson.subject} · {lesson.grade} · {lesson.topic}")
    if lesson.key_points:
        print(f"   重点：{'；'.join(lesson.key_points)}")
    if lesson.difficult_points:
        print(f"   难点：{'；'.join(lesson.difficult_points)}")
    print("=" * 72)


def _print_question_card(idx: int, dialog) -> None:
    q = dialog.question
    cat_tag = {
        "clarify_concept": "❓ 澄清概念",
        "challenge_example": "🎯 反例挑战",
        "extend_topic": "🌱 拓展联想",
        "off_topic": "💭 跑题",
        "stuck_misconception": "⚠️ 卡在迷思",
    }.get(q.category, q.category)
    diff = {"easy": "★☆☆", "medium": "★★☆", "hard": "★★★"}.get(q.difficulty, "?")
    print(f"\n  [{idx}] {q.speaker_name}  {cat_tag}  难度 {diff}")
    print(f"      {q.content}")
    if q.linked_key_point:
        print(f"      关联重点：{q.linked_key_point}")
    if q.linked_misconception_id:
        print(f"      关联迷思：{q.linked_misconception_id}")


def _print_summary(session: QASession) -> None:
    s = session.summary()
    print("\n" + "=" * 72)
    print("📊 Session Summary")
    print("-" * 72)
    print(f"  教案话题：{s['lesson_topic']}")
    print(f"  问题总数：{s['total_questions']}")
    print(
        f"  已解答 {s['resolved']} ｜ 放弃 {s['abandoned']} ｜ 待处理 {s['pending']} ｜ 进行中 {s['active']}"
    )
    if s["covered_key_points"]:
        print(f"  覆盖重点：{'、'.join(s['covered_key_points'])}")
    if s["broken_misconception_ids"]:
        print(f"  破除迷思：{'、'.join(s['broken_misconception_ids'])}")
    if s["resolution_sources"]:
        print(f"  解决方式：{s['resolution_sources']}")
    print("=" * 72)


async def _run_dialog(session: QASession, dialog_id: str, persona_name: str) -> str:
    """跑一个 1v1 对话直到 /resolve、/abandon、/switch 或 /done。

    返回值：next_action ∈ {"continue", "switch", "done"}。
    """
    print(f"\n🟢 进入与 {persona_name} 的 1v1 对话。")
    print(
        "    /resolve 标记已解答 ｜ /abandon 放弃 ｜ /switch 切换学生 ｜ /done 结束 session"
    )
    while True:
        try:
            text = input("\n👨‍🏫 你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "done"
        if not text:
            continue
        if text == "/resolve":
            session.mark_resolved(dialog_id, source="teacher_marked")
            print("✅ 已标记为解答。")
            return "continue"
        if text == "/abandon":
            session.abandon_dialog(dialog_id)
            print("⏭️ 已放弃。")
            return "continue"
        if text == "/switch":
            return "switch"
        if text == "/done":
            return "done"

        try:
            result = await session.send_teacher_message(dialog_id, text)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 失败：{exc}")
            continue
        print(f"\n🧒 {persona_name}：{result.content}")
        if result.self_resolved:
            confirm = (
                input(f"\n💡 {persona_name} 表示懂了，标记为已解答吗？[Y/n] ")
                .strip()
                .lower()
            )
            if confirm in {"", "y", "yes"}:
                session.mark_resolved(dialog_id, source="self_resolve")
                print("✅ 已标记。")
                return "continue"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lesson", default="math_p3_fraction", choices=sorted(PRESETS.keys())
    )
    parser.add_argument(
        "--students", type=int, default=2, help="参与陪练的学生数（最少 1）"
    )
    parser.add_argument("--questions", type=int, default=2, help="每个学生生成几个问题")
    args = parser.parse_args()

    stage_id = PRESETS[args.lesson]
    lesson = _load_lesson_meta(args.lesson)
    stage = load_stage_profile_by_id(stage_id)
    if stage is None:
        raise RuntimeError(f"未找到 stage_profile {stage_id}")

    personas = [p for p in load_personas() if p.stage_id == stage_id][: args.students]
    if not personas:
        raise RuntimeError(f"学段 {stage_id} 无可用 persona")

    llm = LLMClient()
    print(f"✅ LLMClient (model={llm.model})")
    _print_lesson(lesson)
    print(f"👥 参与学生（{len(personas)} 位）：{'、'.join(p.name for p in personas)}")

    # 为每个 persona 构造一个 StudentAgent。ClassroomContext 在新方向用不上，
    # 只为兼容现有 __init__ 必填参数；后续 v2 可让 context 变 optional。
    agents = [
        StudentAgent(
            llm=llm,
            persona=p,
            context=ClassroomContext(subject=lesson.subject, topic=lesson.topic),
            stage=stage,
        )
        for p in personas
    ]

    session = QASession(lesson_meta=lesson)
    print("\n⏳ 学生们正在阅读教案，构思问题……（每个学生约 1 次 LLM 调用）")
    questions = await session.spawn(agents, questions_per_student=args.questions)
    print(f"✅ 共生成 {len(questions)} 个问题。\n")

    while True:
        print("-" * 72)
        print(f"📋 问题队列（剩余 {session.pending_count()}）：")
        pending_dialogs = [d for d in session.dialogs.values() if d.status == "pending"]
        if not pending_dialogs:
            print("   （已无 pending 问题）")
            break
        for i, d in enumerate(pending_dialogs, 1):
            _print_question_card(i, d)

        choice = input(
            "\n👨‍🏫 选择要回答的问题序号（直接回车跳过 / done 结束）：> "
        ).strip()
        if choice in {"done", "/done", "q", "exit"}:
            break
        if not choice:
            continue
        try:
            idx = int(choice)
        except ValueError:
            print("⚠️ 请输入数字")
            continue
        if not (1 <= idx <= len(pending_dialogs)):
            print("⚠️ 序号超出范围")
            continue

        chosen = pending_dialogs[idx - 1]
        action = await _run_dialog(session, chosen.id, chosen.question.speaker_name)
        if action == "done":
            break
        # switch / continue 都是回到主循环

    _print_summary(session)


if __name__ == "__main__":
    asyncio.run(main())
