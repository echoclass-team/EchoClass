"""Demo 固定种子数据脚本。

两种模式
--------
1. **--build**：从内置 Python fixture 重新生成 ``data/demo_sessions/*.json`` 三份样本。
   每次 schema 变更或想刷新内容时跑一次，提交生成的 JSON。
2. **默认（灌库）**：读 ``data/demo_sessions/*.json`` → 写 DB（lessons /
   qa_sessions / dialog_messages / evaluations / feedbacks）。供 B4 复盘 UI
   消费 `/sessions` 列表与 `/review/{session_id}`。
3. **--reset**：先删除已有 demo 行（按固定 id 前缀 + demo user）再灌入。

设计要点
--------
- 三份样本对应三个分数段：good / mid / bad，便于 Pitch 切片演示
- 时间戳固定（2026-01-01...）让 JSON 可复现，diff 友好
- demo user 用固定 ``demo-user-id`` / ``username=demo``；password_hash 留占位，
  仅作为 owner 关联，不参与登录链路
- 教案 ``demo-lesson-fractions`` 三份 session 共用，主题"分数的初步认识"

CLI
---
::

    uv run python scripts/seed_demo.py --build         # 重新生成 JSON
    uv run python scripts/seed_demo.py                 # 灌 DB（增量）
    uv run python scripts/seed_demo.py --reset         # 清空 demo 行后灌库
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from schemas.dialog import (
    DialogMessage,
    DialogSession,
    QuestionProgress,
)
from schemas.evaluation import EvaluationReport, Evidence, RubricScore
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession
from services.session_serde import (
    SessionBundle,
    dump_bundle_to_dict,
    load_bundle_from_dict,
)

logger = logging.getLogger(__name__)

# ============================================================ 常量

DEMO_DATA_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent / "data" / "demo_sessions"
)
DEMO_USER_ID = "demo-user-id"
DEMO_USERNAME = "demo"
DEMO_LESSON_ID = "demo-lesson-fractions"
DEMO_SESSION_IDS = {
    "good": "demo-session-good",
    "mid": "demo-session-mid",
    "bad": "demo-session-bad",
}

_FIXED_TIME = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def _ts(offset_seconds: int = 0) -> datetime:
    """固定基准时间 + 偏移，让 fixture 可复现。"""
    from datetime import timedelta

    return _FIXED_TIME + timedelta(seconds=offset_seconds)


# ============================================================ Lesson 元信息（共享）

DEMO_LESSON_META = LessonMeta(
    subject="数学",
    grade="三年级",
    topic="分数的初步认识",
    objectives=[
        "理解分数表示整体的一部分",
        "掌握几分之一与几分之几的读写",
    ],
    key_points=[
        "分数表示部分与整体的关系",
        "几分之几的写法与读法",
    ],
    difficult_points=[
        "分母分子相等的分数等于 1",
        "等值分数的初步感知",
    ],
)


# ============================================================ 三份样本


@dataclass
class _SampleSpec:
    """单份 demo 样本规约（fixture 内部用）。"""

    label: str  # "good" | "mid" | "bad"
    session_id: str
    persona_id: str
    persona_name: str


_SAMPLES: list[_SampleSpec] = [
    _SampleSpec(
        label="good",
        session_id=DEMO_SESSION_IDS["good"],
        persona_id="p_lower_curious",
        persona_name="张天乐",
    ),
    _SampleSpec(
        label="mid",
        session_id=DEMO_SESSION_IDS["mid"],
        persona_id="p_lower_curious",
        persona_name="张天乐",
    ),
    _SampleSpec(
        label="bad",
        session_id=DEMO_SESSION_IDS["bad"],
        persona_id="p_lower_curious",
        persona_name="张天乐",
    ),
]


# ---------- good ----------


def _build_good() -> SessionBundle:
    spec = _SAMPLES[0]
    question = StudentQuestion(
        id=spec.persona_id,
        speaker_id=spec.persona_id,
        speaker_name=spec.persona_name,
        content="老师，1/2 和 2/4 是一样大的吗？我感觉下面那个数字大的应该更大呀。",
        category="stuck_misconception",
        difficulty="medium",
        linked_key_point="分数表示部分与整体的关系",
        linked_misconception_id="frac_size_by_denominator",
        rationale="我以为分母越大分数越大，所以 2/4 应该比 1/2 大。",
    )
    messages = [
        DialogMessage(
            role="teacher",
            content="这是个好问题。我们想象有一个苹果，把它平均分成 2 份，你拿走 1 份，是 1/2；如果把同一个苹果平均分成 4 份，你拿走 2 份，是 2/4。你画一下，比比看大小？",
            timestamp=_ts(0),
        ),
        DialogMessage(
            role="student",
            content="嗯……我画了……欸？两块拼起来好像和半个一样大！",
            timestamp=_ts(60),
        ),
        DialogMessage(
            role="teacher",
            content="对！这就说明 1/2 和 2/4 一样大。分子和分母同时变大几倍，分数大小不变，这叫等值分数。再看 3/6 你猜呢？",
            timestamp=_ts(120),
        ),
        DialogMessage(
            role="student",
            content="3/6 也是一样大！因为 3 份和 6 份比起来正好是一半！老师我懂了。\n[懂了]",
            timestamp=_ts(180),
            self_resolved=True,
        ),
    ]
    progress = QuestionProgress(
        question_id=question.id,
        status="resolved",
        turns_used=2,
        message_start_idx=0,
        message_end_idx=len(messages),
        resolution_source="self_resolve",
    )
    dialog = DialogSession(
        id=spec.persona_id,
        student_id=spec.persona_id,
        question=question,
        status="resolved",
        messages=messages,
        started_at=_ts(0),
        ended_at=_ts(180),
        resolution_source="self_resolve",
        asked_questions=[question],
        question_progress=[progress],
        current_question_idx=1,
    )
    session = QASession(lesson_meta=DEMO_LESSON_META, session_id=spec.session_id)
    session.dialogs[dialog.id] = dialog

    evaluation = EvaluationReport(
        session_id=spec.session_id,
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="MR",
                score=4,
                rationale="老师精准识别学生'分母大=分数大'的迷思，用切苹果反例 + 等值分数类比，让学生自己说出'拼起来一样大'。",
                evidence=[
                    Evidence(
                        dialog_id=dialog.id,
                        chunk_seq=0,
                        excerpt="把同一个苹果平均分成 4 份，你拿走 2 份，是 2/4。你画一下",
                    )
                ],
            ),
            RubricScore(
                dimension="KC",
                score=3,
                rationale="覆盖了'分数表示部分与整体'与'等值分数'两个重点，用画图脚手架适配低年级具体运算阶段。",
                evidence=[],
            ),
            RubricScore(
                dimension="RR",
                score=3,
                rationale="self_resolve 比例落入 40-70% 甜区，学生在确认前主动验证 3/6 同理，体现 Bandura 自我效能。",
                evidence=[],
            ),
            RubricScore(
                dimension="TQ",
                score=4,
                rationale="老师不直接给答案，先让学生画图自验，再泛化到 3/6 检验类比迁移，是典型 ZPD scaffolding。",
                evidence=[
                    Evidence(
                        dialog_id=dialog.id,
                        chunk_seq=2,
                        excerpt="再看 3/6 你猜呢？",
                    )
                ],
            ),
            RubricScore(
                dimension="SS",
                score=3,
                rationale="学生表达从困惑→具象操作→泛化，完成一次完整的认知重构。",
                evidence=[],
            ),
        ],
        overall=3.4,
        generated_at=_ts(200),
    )
    feedback = TeacherFeedback(
        strengths=[
            "用切苹果具体情境替代抽象比较，精准命中'分母大=分数大'迷思",
            "让学生自己画图验证，再泛化到 3/6，体现脚手架式提问",
        ],
        improvements=[
            "可以让学生用自己的话复述'什么是等值分数'，进一步检验是否真懂",
        ],
        next_steps=[
            "下次答疑可准备 1-2 个变式题（如 4/8、5/10）让学生独立判断是否等值",
        ],
        tone="encouraging",
        generated_at=_ts(210),
    )
    return SessionBundle(
        session=session,
        evaluation=evaluation,
        feedback=feedback,
        label=spec.label,
        persona_ids=[spec.persona_id],
    )


# ---------- mid ----------


def _build_mid() -> SessionBundle:
    spec = _SAMPLES[1]
    question = StudentQuestion(
        id=spec.persona_id,
        speaker_id=spec.persona_id,
        speaker_name=spec.persona_name,
        content="老师，几分之几是什么意思呀？我看书上写 3/4，我不知道怎么读。",
        category="clarify_concept",
        difficulty="easy",
        linked_key_point="几分之几的写法与读法",
        linked_misconception_id=None,
        rationale="我对分数的写法不熟，记不住读法。",
    )
    messages = [
        DialogMessage(
            role="teacher",
            content="3/4 读作'四分之三'。下面的数字叫分母，先读分母；上面的数字叫分子，再读分子。所以是'四分之三'。",
            timestamp=_ts(0),
        ),
        DialogMessage(
            role="student",
            content="哦……那 5/8 是读'八分之五'吗？",
            timestamp=_ts(60),
        ),
        DialogMessage(
            role="teacher",
            content="对的，记住先读分母再读分子就行。",
            timestamp=_ts(120),
        ),
        DialogMessage(
            role="student",
            content="嗯……我大概知道了。\n[懂了]",
            timestamp=_ts(180),
            self_resolved=True,
        ),
    ]
    progress = QuestionProgress(
        question_id=question.id,
        status="resolved",
        turns_used=2,
        message_start_idx=0,
        message_end_idx=len(messages),
        resolution_source="self_resolve",
    )
    dialog = DialogSession(
        id=spec.persona_id,
        student_id=spec.persona_id,
        question=question,
        status="resolved",
        messages=messages,
        started_at=_ts(0),
        ended_at=_ts(180),
        resolution_source="self_resolve",
        asked_questions=[question],
        question_progress=[progress],
        current_question_idx=1,
    )
    session = QASession(lesson_meta=DEMO_LESSON_META, session_id=spec.session_id)
    session.dialogs[dialog.id] = dialog

    evaluation = EvaluationReport(
        session_id=spec.session_id,
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="MR",
                score=2,
                rationale="本题非典型迷思类，未涉及破除；但老师也未引导学生反思'为什么先读分母'的概念由来。",
                evidence=[],
            ),
            RubricScore(
                dimension="KC",
                score=2,
                rationale="覆盖'读法'重点但未联系'部分与整体'的核心含义，学生仅记住程序性规则。",
                evidence=[],
            ),
            RubricScore(
                dimension="RR",
                score=3,
                rationale="问题表面解决，学生表达'大概知道'有不确定信号，self_resolve 的真懂程度存疑。",
                evidence=[
                    Evidence(
                        dialog_id=dialog.id,
                        chunk_seq=3,
                        excerpt="嗯……我大概知道了",
                    )
                ],
            ),
            RubricScore(
                dimension="TQ",
                score=2,
                rationale="老师以陈述代替提问，未让学生用自己的话解释'为什么是这样读'，缺少脚手架。",
                evidence=[],
            ),
            RubricScore(
                dimension="SS",
                score=2,
                rationale="学生从'不知道怎么读'→'记住规则'，停留在记忆层未进入理解层。",
                evidence=[],
            ),
        ],
        overall=2.2,
        generated_at=_ts(200),
    )
    feedback = TeacherFeedback(
        strengths=[
            "及时回应学生的概念性提问，给出明确的读法规则",
        ],
        improvements=[
            "学生说'大概知道了'是不确定信号，建议追问 1 道变式题（如 7/10）确认",
            "可让学生用自己的话解释'为什么先读分母'，从记忆层推进到理解层",
        ],
        next_steps=[
            "下次面对程序性问题，多用'反问 + 学生复述'代替'直接告知'",
        ],
        tone="neutral",
        generated_at=_ts(210),
    )
    return SessionBundle(
        session=session,
        evaluation=evaluation,
        feedback=feedback,
        label=spec.label,
        persona_ids=[spec.persona_id],
    )


# ---------- bad ----------


def _build_bad() -> SessionBundle:
    spec = _SAMPLES[2]
    question = StudentQuestion(
        id=spec.persona_id,
        speaker_id=spec.persona_id,
        speaker_name=spec.persona_name,
        content="老师，3/3 是不是 1 啊？我感觉 3/3 应该比 1 大，因为有 3 个嘛。",
        category="stuck_misconception",
        difficulty="medium",
        linked_key_point="分母分子相等的分数等于 1",
        linked_misconception_id="frac_equal_to_one",
        rationale="我看到分子有 3 个，下意识觉得比 1 多。",
    )
    messages = [
        DialogMessage(
            role="teacher",
            content="对，3/3 就是等于 1，记住就行。",
            timestamp=_ts(0),
        ),
        DialogMessage(
            role="student",
            content="为什么呀？3 个不就比 1 个多吗？",
            timestamp=_ts(60),
        ),
        DialogMessage(
            role="teacher",
            content="规则就是这样的，分子分母相等就等于 1。课本上写了。",
            timestamp=_ts(120),
        ),
        DialogMessage(
            role="student",
            content="哦……（还是不太懂为什么）",
            timestamp=_ts(180),
        ),
        DialogMessage(
            role="teacher",
            content="多做几道题就熟了，先记下来。",
            timestamp=_ts(240),
        ),
        DialogMessage(
            role="student",
            content="好吧。",
            timestamp=_ts(300),
        ),
    ]
    progress = QuestionProgress(
        question_id=question.id,
        status="abandoned",
        turns_used=3,
        message_start_idx=0,
        message_end_idx=len(messages),
        resolution_source="abandoned",
    )
    dialog = DialogSession(
        id=spec.persona_id,
        student_id=spec.persona_id,
        question=question,
        status="abandoned",
        messages=messages,
        started_at=_ts(0),
        ended_at=_ts(300),
        resolution_source="abandoned",
        asked_questions=[question],
        question_progress=[progress],
        current_question_idx=1,
    )
    session = QASession(lesson_meta=DEMO_LESSON_META, session_id=spec.session_id)
    session.dialogs[dialog.id] = dialog

    evaluation = EvaluationReport(
        session_id=spec.session_id,
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="MR",
                score=0,
                rationale="老师识别到学生迷思但只给结论不解释为什么；学生明确追问后仍以'记住就行'敷衍，迷思未破除。",
                evidence=[
                    Evidence(
                        dialog_id=dialog.id,
                        chunk_seq=2,
                        excerpt="规则就是这样的……课本上写了",
                    )
                ],
            ),
            RubricScore(
                dimension="KC",
                score=1,
                rationale="触及'分母分子相等的分数等于 1'但仅以规则陈述，未用任何学段适配脚手架（如切蛋糕情境）。",
                evidence=[],
            ),
            RubricScore(
                dimension="RR",
                score=1,
                rationale="问题最终 abandoned；学生最后说'好吧'是典型的虚假接受，self_efficacy 受打击。",
                evidence=[
                    Evidence(
                        dialog_id=dialog.id,
                        chunk_seq=5,
                        excerpt="好吧。",
                    )
                ],
            ),
            RubricScore(
                dimension="TQ",
                score=0,
                rationale="老师全程只用陈述句和'记住'，没有任何反问或脚手架，缺失 ZPD 引导。",
                evidence=[],
            ),
            RubricScore(
                dimension="SS",
                score=1,
                rationale="学生从主动质疑→被动接受，态度从开放转为关闭，是负面学习体验。",
                evidence=[],
            ),
        ],
        overall=0.6,
        generated_at=_ts(320),
    )
    feedback = TeacherFeedback(
        strengths=[
            "能听到学生的提问并给出回应",
        ],
        improvements=[
            "学生追问'为什么 3 个不比 1 个多'是宝贵的认知冲突机会，应抓住而非以'记住'回避",
            "建议用具体情境（如蛋糕被切成 3 块、把 3 块都拿走）让学生自己看到 3/3 = 整个 = 1",
            "学生'好吧'是虚假接受信号，下次遇到类似回应应主动追问'你真的明白了吗？'",
        ],
        next_steps=[
            "复习 Posner 概念变化模型：识别迷思 → 提供反例 → 引导类比 → 学生复述",
            "下次答疑前准备 2-3 个具体情境道具（图片、实物），减少纯规则解释",
        ],
        tone="critical",
        generated_at=_ts(330),
    )
    return SessionBundle(
        session=session,
        evaluation=evaluation,
        feedback=feedback,
        label=spec.label,
        persona_ids=[spec.persona_id],
    )


def build_all_bundles() -> list[SessionBundle]:
    """构造三份 demo bundle（good / mid / bad）。"""
    return [_build_good(), _build_mid(), _build_bad()]


# ============================================================ JSON I/O


def _bundle_path(label: str) -> Path:
    return DEMO_DATA_DIR / f"session_{label}.json"


def write_bundles_to_disk(bundles: Iterable[SessionBundle]) -> list[Path]:
    """把 bundle 序列化为 JSON 写入 ``data/demo_sessions/session_{label}.json``。"""
    DEMO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for bundle in bundles:
        if not bundle.label:
            raise ValueError("bundle.label is required for write_bundles_to_disk")
        path = _bundle_path(bundle.label)
        payload = dump_bundle_to_dict(bundle)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def read_bundles_from_disk(labels: Iterable[str] | None = None) -> list[SessionBundle]:
    """从 ``data/demo_sessions/*.json`` 读出 bundle 列表（按 labels 顺序）。"""
    target_labels = list(labels) if labels else list(DEMO_SESSION_IDS.keys())
    bundles: list[SessionBundle] = []
    for label in target_labels:
        path = _bundle_path(label)
        if not path.exists():
            raise FileNotFoundError(
                f"demo session file missing: {path}. 先跑 --build 生成。"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        bundles.append(load_bundle_from_dict(data))
    return bundles


# ============================================================ DB 灌入


def _ensure_demo_user(db) -> None:
    """确保存在 ``demo`` user，作为所有 demo lesson / session 的 owner。"""
    from db.models import User

    row = db.query(User).filter(User.id == DEMO_USER_ID).first()
    if row is not None:
        return
    db.add(
        User(
            id=DEMO_USER_ID,
            username=DEMO_USERNAME,
            password_hash="demo-placeholder-hash",
        )
    )
    db.commit()


def _ensure_demo_lesson(db) -> None:
    """确保存在 demo lesson；title / meta_json 同 fixture。"""
    from db.crud import get_lesson_by_id, save_lesson

    existing = get_lesson_by_id(db, DEMO_LESSON_ID)
    if existing is not None:
        return
    save_lesson(
        db,
        lesson_id=DEMO_LESSON_ID,
        owner_id=DEMO_USER_ID,
        content_hash="demo-fixed-hash",
        filename="demo_fractions.pdf",
        title=DEMO_LESSON_META.topic,
        meta_json=DEMO_LESSON_META.model_dump_json(),
        text_length=0,
        chunk_count=0,
    )


def _seed_bundle(db, bundle: SessionBundle) -> None:
    """把单份 bundle 写入 DB（lessons 已确保存在）。"""
    from db.crud import (
        save_dialog_message,
        save_qa_session,
        upsert_evaluation,
        upsert_feedback,
    )

    session = bundle.session

    save_qa_session(
        db,
        session_id=session.id,
        lesson_id=DEMO_LESSON_ID,
        owner_id=DEMO_USER_ID,
        persona_ids=list(bundle.persona_ids or []),
    )

    seq = 1
    for dialog in session.dialogs.values():
        for message in dialog.messages:
            save_dialog_message(
                db,
                session_id=session.id,
                dialog_id=dialog.id,
                seq=seq,
                role=message.role,
                content=message.content,
                self_resolved=message.self_resolved,
                is_new_question=message.is_new_question,
                question_id=message.question_id,
                timestamp=message.timestamp,
            )
            seq += 1

    if bundle.evaluation is not None:
        upsert_evaluation(
            db,
            session_id=session.id,
            rubric_version=bundle.evaluation.rubric_version,
            report_json=bundle.evaluation.model_dump_json(),
        )
    if bundle.feedback is not None:
        upsert_feedback(
            db,
            session_id=session.id,
            feedback_json=bundle.feedback.model_dump_json(),
        )


def _reset_demo_rows(db) -> None:
    """清掉已有 demo session / lesson / user 关联行，让 seed 可重复执行。"""
    from db.models import (
        DialogMessageRecord,
        EvaluationRecord,
        FeedbackRecord,
        Lesson,
        QASessionRecord,
        User,
    )

    session_ids = list(DEMO_SESSION_IDS.values())
    db.query(DialogMessageRecord).filter(
        DialogMessageRecord.session_id.in_(session_ids)
    ).delete(synchronize_session=False)
    db.query(EvaluationRecord).filter(
        EvaluationRecord.session_id.in_(session_ids)
    ).delete(synchronize_session=False)
    db.query(FeedbackRecord).filter(FeedbackRecord.session_id.in_(session_ids)).delete(
        synchronize_session=False
    )
    db.query(QASessionRecord).filter(QASessionRecord.id.in_(session_ids)).delete(
        synchronize_session=False
    )
    db.query(Lesson).filter(Lesson.id == DEMO_LESSON_ID).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.id == DEMO_USER_ID).delete(synchronize_session=False)
    db.commit()


def seed_to_db(bundles: Iterable[SessionBundle], *, reset: bool = False) -> int:
    """把 bundles 灌入 DB，返回成功写入的 session 数量。"""
    from db.engine import SessionLocal

    db = SessionLocal()
    try:
        if reset:
            _reset_demo_rows(db)
        _ensure_demo_user(db)
        _ensure_demo_lesson(db)
        count = 0
        for bundle in bundles:
            _seed_bundle(db, bundle)
            count += 1
        return count
    finally:
        db.close()


# ============================================================ CLI


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_demo",
        description="EchoClass demo 固定种子数据：build JSON 或灌入 DB。",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="从内置 fixture 重新生成 data/demo_sessions/*.json",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="灌库前先清空已有 demo 行（仅默认模式有效）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_argparser().parse_args(argv)

    if args.build:
        bundles = build_all_bundles()
        paths = write_bundles_to_disk(bundles)
        for path in paths:
            print(f"✅ wrote {path.relative_to(path.parent.parent.parent)}")
        return 0

    bundles = read_bundles_from_disk()
    count = seed_to_db(bundles, reset=args.reset)
    print(f"✅ seeded {count} demo sessions into DB (reset={args.reset})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
