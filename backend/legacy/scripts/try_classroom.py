#!/usr/bin/env python3
"""ClassroomGraph 真实 API 交互式冒烟测试。

跑通完整链路：teacher_input → director → fanout_students → aggregate
真实调用 LLM（DirectorAgent + StudentAgent），并直观展示：
- 老师本轮发言命中的 current_focus_key_point
- DirectorAgent 决策（speak / raise_hand / daydream / silent）
- 每个被选中学生的回复（intent / emotion / 触发的迷思）
- 黑板更新

用法（在 backend/ 目录下执行）::

    uv run python scripts/try_classroom.py
    uv run python scripts/try_classroom.py --lesson math_p3_fraction --turns 3
    uv run python scripts/try_classroom.py --auto    # 用预设老师发言一次性跑完

交互模式下输入 ``exit`` / ``quit`` 退出，``focus`` 查看当前 focus，``board`` 查看黑板。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from legacy.agents.director import DirectorAgent
from legacy.graph.classroom import ClassroomGraph
from legacy.graph.state import initial_classroom_state
from llm.client import LLMClient
from schemas.lesson import LessonMeta
from schemas.stage import load_stage_profile_by_id
from schemas.student import load_personas

LESSON_SAMPLES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "lesson_samples"
)

# 预设的几节示范课，跑 demo 用。key 与 .meta.md 文件名对应。
PRESET_LESSONS = {
    "math_p3_fraction": {
        "stage_id": "p_middle",
        "auto_utterances": [
            "同学们好，今天我们来学习一个新的数学知识。",
            "我们先来看几分之一是什么意思。",
            "现在大家想想，分数各部分的名称是什么？",
            "好，我们来挑战一下，怎么比较两个分数的大小？",
        ],
    },
    "math_p2_addition": {
        "stage_id": "p_lower",
        "auto_utterances": [
            "同学们，今天我们学习两位数加法。",
            "先想想个位相加要注意什么？",
            "好，那十位呢？",
        ],
    },
    "math_p5_area": {
        "stage_id": "p_upper",
        "auto_utterances": [
            "今天我们来研究平行四边形的面积。",
            "先回忆一下，长方形的面积公式是什么？",
            "怎么把平行四边形转化成长方形？",
        ],
    },
}


def _load_lesson_meta(lesson_key: str) -> LessonMeta:
    """从 data/lesson_samples/<key>.meta.md 抽 JSON 块构造 LessonMeta。"""
    path = LESSON_SAMPLES_DIR / f"{lesson_key}.meta.md"
    if not path.exists():
        raise FileNotFoundError(f"未找到 {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} 中未找到 JSON 块")
    data = json.loads(match.group(1))
    return LessonMeta(
        subject=data.get("subject", ""),
        grade=data.get("grade", ""),
        topic=data.get("topic", ""),
        key_points=data.get("key_points", []),
        difficult_points=data.get("difficult_points", []),
        objectives=data.get("objectives", []),
    )


def _print_state_overview(state, lesson: LessonMeta) -> None:
    print("=" * 72)
    print(f"📘 课程：{lesson.subject} · {lesson.grade} · {lesson.topic}")
    print(f"🎯 重点：{'；'.join(lesson.key_points)}")
    if lesson.difficult_points:
        print(f"🧗 难点：{'；'.join(lesson.difficult_points)}")
    print(f"👥 学生（{len(state['students'])} 人）：")
    for s in state["students"]:
        print(f"   - {s.name}（{s.grade or s.stage_id} · {s.effective_level}）")
    print("=" * 72)


def _print_turn(state, turn_no: int) -> None:
    print(f"\n🟢 第 {turn_no} 轮")
    print(f"  ↳ 当前 focus: {state['current_focus_key_point'] or '（无明确焦点）'}")

    if state["director_history"]:
        decision = state["director_history"][-1]
        print(f"  ↳ Director 决策（rationale: {decision.rationale}）：")
        for action in decision.actions:
            tag = {
                "speak": "🗣 发言",
                "raise_hand": "✋ 举手",
                "daydream": "💭 走神",
                "silent": "🤐 沉默",
            }.get(action.action_type, action.action_type)
            print(f"     {tag}  {action.speaker_id}  (priority={action.priority})")

    last_student_msgs = [m for m in state["transcript"] if m.role == "student"][
        -len(state["students"]) :
    ]
    if last_student_msgs:
        # 仅打印本轮（最近一轮的学生发言）
        turn_start_idx = next(
            (
                i
                for i in range(len(state["transcript"]) - 1, -1, -1)
                if state["transcript"][i].role == "teacher"
            ),
            0,
        )
        replies = [
            m for m in state["transcript"][turn_start_idx + 1 :] if m.role == "student"
        ]
        if replies:
            print("  ↳ 学生回复：")
            for m in replies:
                print(f"     · {m.speaker_id}：{m.content}")

    if state["blackboard"]:
        print(f"  ↳ 黑板已讲：{'；'.join(state['blackboard'])}")


async def _run_turn(graph, state, utterance: str):
    state = await graph.run_turn(state, utterance)
    return state


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lesson", default="math_p3_fraction", choices=sorted(PRESET_LESSONS.keys())
    )
    parser.add_argument("--max-students", type=int, default=4, help="最多加载几个学生")
    parser.add_argument(
        "--auto", action="store_true", help="用预设老师发言一次性跑完，不进入交互"
    )
    parser.add_argument(
        "--turns", type=int, default=None, help="auto 模式下跑几轮，缺省=预设全部"
    )
    parser.add_argument("--chunk-size", type=int, default=12)
    args = parser.parse_args()

    preset = PRESET_LESSONS[args.lesson]
    stage_id = preset["stage_id"]

    # 1. 资源加载
    lesson = _load_lesson_meta(args.lesson)
    stage = load_stage_profile_by_id(stage_id)
    if stage is None:
        raise RuntimeError(f"未找到 stage_profile {stage_id}")
    students = [p for p in load_personas() if p.stage_id == stage_id][
        : args.max_students
    ]
    if len(students) < 2:
        raise RuntimeError(f"学段 {stage_id} 学生不足 2 个，仅 {len(students)} 个")

    # 2. LLM + agents + graph
    llm = LLMClient()
    print(f"✅ LLMClient (model={llm.model}, base={llm.base_url})\n")

    director = DirectorAgent(llm=llm)
    queue: asyncio.Queue = asyncio.Queue()
    graph = ClassroomGraph(
        director=director, llm=llm, event_queue=queue, chunk_size=args.chunk_size
    )

    state = initial_classroom_state(
        session_id="local-try-classroom",
        lesson_meta=lesson,
        stage=stage,
        students=students,
    )
    _print_state_overview(state, lesson)

    # 3. auto / interactive
    if args.auto:
        utterances = preset["auto_utterances"]
        if args.turns is not None:
            utterances = utterances[: args.turns]
        for i, u in enumerate(utterances, 1):
            print(f"\n👨‍🏫 老师：{u}")
            state = await _run_turn(graph, state, u)
            _print_turn(state, i)
        print("\n🎉 自动模式结束。")
        return

    # interactive
    print("\n💡 输入老师发言；命令：exit 退出，focus 查看当前焦点，board 查看黑板。\n")
    turn_no = 0
    while True:
        try:
            line = input("👨‍🏫 老师 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit", "q"}:
            break
        if line.lower() == "focus":
            print(f"   当前 focus: {state['current_focus_key_point']!r}")
            continue
        if line.lower() == "board":
            print(f"   黑板：{state['blackboard']}")
            print(f"   taught_points：{sorted(state['taught_points'])}")
            continue

        turn_no += 1
        try:
            state = await _run_turn(graph, state, line)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 本轮失败：{exc}")
            continue
        _print_turn(state, turn_no)

    print("\n👋 课堂结束。")
    print(
        f"📊 总轮次：{state['turn_index']}，黑板覆盖：{len(state['taught_points'])}/{len(lesson.key_points)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
