"""``/api/qa-sessions`` REST 路由集成测试 (#B1 / Issue #72)。

用 FastAPI ``TestClient`` + ``app.dependency_overrides`` 注入隔离的
``QASessionRegistry``、可控的 lesson lookup 和不触网的 fake agent factory，
全程不需要真实 LLM。

覆盖场景：
- POST 创建 session：成功 + 返回 ws_url + 注册到 registry
- POST 错误：lesson_id 不存在 → 404；persona_ids 空 / 不存在 → 400；
  count_per_student 越界 → 422（pydantic）
- GET 查询：成功投影 dialog 摘要；不存在 → 404
- POST end：成功返回 summary + pop registry；二次调用 → 404
- 创建后调 ``QASession.start_dialog`` / ``mark_resolved`` 改变状态后，
  ``GET`` 应反映出来
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastapi.testclient import TestClient

from api import qa_sessions as qa_sessions_module
from api.deps import CurrentUser, get_current_user
from api.qa_sessions import (
    AgentFactory,
    LessonLookup,
    get_agent_factory,
    get_lesson_lookup,
)
from main import app
from schemas.lesson import LessonMeta, LessonRecord
from schemas.question import StudentQuestion
from schemas.stage import StageProfile
from schemas.student import Persona, load_personas
from services.qa_session_registry import QASessionRegistry, get_registry

_FAKE_USER = CurrentUser(id="test-user-001", username="test_teacher")


# ============================================================ Fakes


class _FakeAgent:
    """不调 LLM 的 fake StudentAgent。

    - ``generate_questions`` 返回脚本化的 ``StudentQuestion`` 列表
    - ``stream_in_dialog`` 留空（本测试只覆盖 REST 部分，不连 WS）
    """

    def __init__(self, persona: Persona) -> None:
        self.persona = persona

    async def generate_questions(
        self, lesson_meta: LessonMeta, *, count: int = 3
    ) -> list[StudentQuestion]:
        return [
            StudentQuestion(
                id=f"{self.persona.id or self.persona.name}-q{i}",
                speaker_id=self.persona.id or self.persona.name,
                speaker_name=self.persona.name,
                content=f"{self.persona.name}的问题{i}：" + (lesson_meta.topic or ""),
                category="clarify_concept",
                difficulty="easy",
                rationale="",
            )
            for i in range(count)
        ]


def _fake_agent_factory(persona: Persona, stage: Optional[StageProfile]):
    return _FakeAgent(persona)


# ============================================================ Fixtures


@pytest.fixture
def isolated_registry() -> QASessionRegistry:
    """每个用例独立 registry，避免相互污染。"""
    reg = QASessionRegistry()
    app.dependency_overrides[get_registry] = lambda: reg
    yield reg
    app.dependency_overrides.pop(get_registry, None)


@pytest.fixture
def lesson_store() -> dict[str, LessonRecord]:
    """提供一个进程内 lesson 字典，路由通过 dependency 查它。

    用例可往里塞测试用 lesson；teardown 自动清理。
    """
    store: dict[str, LessonRecord] = {}

    def _lookup(lesson_id: str) -> Optional[LessonRecord]:
        return store.get(lesson_id)

    app.dependency_overrides[get_lesson_lookup] = lambda: _lookup
    yield store
    app.dependency_overrides.pop(get_lesson_lookup, None)


@pytest.fixture
def fake_agents() -> AgentFactory:
    app.dependency_overrides[get_agent_factory] = lambda: _fake_agent_factory
    yield _fake_agent_factory
    app.dependency_overrides.pop(get_agent_factory, None)


@pytest.fixture
def client(
    isolated_registry: QASessionRegistry,
    lesson_store: dict[str, LessonRecord],
    fake_agents: AgentFactory,
) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def real_persona_ids() -> list[str]:
    """从 data/personas/ 真实加载，取前两个的 id。"""
    personas = load_personas()
    assert len(personas) >= 2, "需要至少 2 个 persona 才能跑这套测试"
    return [personas[0].id or personas[0].name, personas[1].id or personas[1].name]


def _seed_lesson(
    lesson_store: dict[str, LessonRecord], lesson_id: str = "lesson-1"
) -> LessonRecord:
    record = LessonRecord(
        lesson_id=lesson_id,
        filename="demo.md",
        meta=LessonMeta(
            subject="数学",
            grade="三年级",
            topic="分数的初步认识",
            objectives=["理解分数"],
            key_points=["几分之一"],
            difficult_points=[],
        ),
        text_length=100,
        chunk_count=1,
    )
    lesson_store[lesson_id] = record
    return record


# ============================================================ create


def test_create_session_success(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    resp = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids,
            "count_per_student": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]

    assert data["session_id"]
    assert data["ws_url"] == f"/ws/qa-sessions/{data['session_id']}"
    assert data["lesson"]["topic"] == "分数的初步认识"
    assert len(data["students"]) == 2
    # M3：每个学生一个连续答疑 thread
    assert len(data["questions"]) == 2
    # 学生顺序 == 入参 persona_ids 顺序
    assert [s["id"] for s in data["students"]] == real_persona_ids


@pytest.mark.asyncio
async def test_create_session_registers_in_registry(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    resp = client.post(
        "/api/qa-sessions",
        json={"lesson_id": "lesson-1", "persona_ids": real_persona_ids[:1]},
    )
    assert resp.status_code == 200
    session_id = resp.json()["data"]["session_id"]

    session = await isolated_registry.get(session_id)
    assert session is not None
    assert session.id == session_id


def test_create_session_lesson_not_found(
    client: TestClient,
    real_persona_ids: list[str],
) -> None:
    resp = client.post(
        "/api/qa-sessions",
        json={"lesson_id": "ghost", "persona_ids": real_persona_ids[:1]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
    assert "ghost" in body["message"]


def test_create_session_persona_ids_empty(
    client: TestClient, lesson_store: dict[str, LessonRecord]
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    resp = client.post(
        "/api/qa-sessions",
        json={"lesson_id": "lesson-1", "persona_ids": []},
    )
    # pydantic min_length=1 会先拦下来 → 422
    assert resp.status_code == 422


def test_create_session_persona_id_unknown(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    resp = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": [real_persona_ids[0], "ghost-persona"],
        },
    )
    assert resp.status_code == 400
    assert "ghost-persona" in resp.json()["message"]


def test_create_session_count_per_student_out_of_range(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    resp = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids[:1],
            "count_per_student": 0,
        },
    )
    assert resp.status_code == 422


def test_create_session_dedup_persona_ids(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    real_persona_ids: list[str],
) -> None:
    """重复传同一 persona_id 不报错，但只算一份。"""
    _seed_lesson(lesson_store, "lesson-1")
    pid = real_persona_ids[0]
    resp = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": [pid, pid, pid],
            "count_per_student": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["students"]) == 1
    assert len(data["questions"]) == 1


# ============================================================ get


def test_get_session_state(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    create = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids,
            "count_per_student": 2,
        },
    )
    session_id = create.json()["data"]["session_id"]

    resp = client.get(f"/api/qa-sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["session_id"] == session_id
    assert data["lesson"]["topic"] == "分数的初步认识"
    assert len(data["students"]) == 2
    assert len(data["dialogs"]) == 2
    # 全部刚 spawn，未启动
    assert data["pending"] == 2
    assert data["active"] == 0
    assert data["resolved"] == 0
    assert data["abandoned"] == 0
    # dialog 摘要字段
    d0 = data["dialogs"][0]
    assert d0["status"] == "pending"
    assert d0["turn_count"] == 0
    assert d0["question_preview"]
    # issue #102: history 字段始终存在，未发生对话时为空数组
    assert d0["history"] == []
    assert all(d["history"] == [] for d in data["dialogs"])


@pytest.mark.asyncio
async def test_get_session_state_returns_dialog_history(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    """issue #102 — GET 应返回每个 dialog 的完整 history。

    构造一个发生过 2 来回 + 1 学生 self_resolved 的 dialog，断言 GET 拿到
    完整 4 条消息（teacher / student / teacher / student），且 student
    的 self_resolved 标志能被准确投影。
    """
    from datetime import datetime, timezone

    from schemas.dialog import DialogMessage

    _seed_lesson(lesson_store, "lesson-1")
    create = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids[:1],
            "count_per_student": 1,
        },
    )
    session_id = create.json()["data"]["session_id"]

    session = await isolated_registry.get(session_id)
    assert session is not None
    dialog_id = next(iter(session.dialogs))
    dialog = session.dialogs[dialog_id]

    # 直接注入消息（不走 LLM），模拟已发生 2 来回，最后一轮学生 self_resolved
    now = datetime.now(timezone.utc)
    dialog.messages.extend(
        [
            DialogMessage(role="teacher", content="先看分母", timestamp=now),
            DialogMessage(
                role="student",
                content="嗯……分母在下面",
                timestamp=now,
                self_resolved=False,
            ),
            DialogMessage(role="teacher", content="对，再看分子", timestamp=now),
            DialogMessage(
                role="student",
                content="哦明白了！",
                timestamp=now,
                self_resolved=True,
            ),
        ]
    )

    resp = client.get(f"/api/qa-sessions/{session_id}")
    assert resp.status_code == 200
    target = next(d for d in resp.json()["data"]["dialogs"] if d["id"] == dialog_id)

    history = target["history"]
    assert len(history) == 4
    assert [m["role"] for m in history] == ["teacher", "student", "teacher", "student"]
    assert history[0]["content"] == "先看分母"
    assert history[3]["content"] == "哦明白了！"
    assert history[1]["self_resolved"] is False
    assert history[3]["self_resolved"] is True
    # teacher 回合的 self_resolved 应始终 False（即使将来有 bug 改写也保护住）
    assert all(m["self_resolved"] is False for m in history if m["role"] == "teacher")


@pytest.mark.asyncio
async def test_get_session_state_reflects_transitions(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    create = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids,
            "count_per_student": 2,
        },
    )
    session_id = create.json()["data"]["session_id"]

    session = await isolated_registry.get(session_id)
    assert session is not None
    first_id = next(iter(session.dialogs))
    second_id = list(session.dialogs)[1]
    session.start_dialog(first_id)
    # M3: count_per_student=2, 需要对每个子题 resolve 才能结束 dialog
    session.mark_resolved(
        first_id, source="teacher_marked"
    )  # Q1 resolved, advance to Q2
    session.mark_resolved(
        first_id, source="teacher_marked"
    )  # Q2 resolved, dialog resolved
    session.abandon_dialog(second_id)

    resp = client.get(f"/api/qa-sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["resolved"] == 1
    assert data["abandoned"] == 1
    assert data["pending"] == 0


def test_get_session_not_found(client: TestClient) -> None:
    resp = client.get("/api/qa-sessions/ghost")
    assert resp.status_code == 404


# ============================================================ end


@pytest.mark.asyncio
async def test_end_session_success(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    create = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids[:1],
            "count_per_student": 2,
        },
    )
    session_id = create.json()["data"]["session_id"]

    # 结束前手动改一个 dialog 为 resolved，确认 summary 反映出来
    session = await isolated_registry.get(session_id)
    assert session is not None
    first_id = next(iter(session.dialogs))
    # M3: count_per_student=2, 需要 resolve 两次才能结束整个 dialog
    session.mark_resolved(first_id, source="teacher_marked")  # Q1 resolved → Q2
    session.mark_resolved(
        first_id, source="teacher_marked"
    )  # Q2 resolved → dialog resolved

    resp = client.post(f"/api/qa-sessions/{session_id}/end")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == session_id
    summary = data["summary"]
    assert summary["session_id"] == session_id
    assert summary["resolved"] == 1
    assert summary["total_questions"] == 1

    # 已从 registry 移除
    assert await isolated_registry.get(session_id) is None


def test_end_session_idempotent_after_first(
    client: TestClient,
    lesson_store: dict[str, LessonRecord],
    isolated_registry: QASessionRegistry,
    real_persona_ids: list[str],
) -> None:
    _seed_lesson(lesson_store, "lesson-1")
    create = client.post(
        "/api/qa-sessions",
        json={
            "lesson_id": "lesson-1",
            "persona_ids": real_persona_ids[:1],
            "count_per_student": 1,
        },
    )
    session_id = create.json()["data"]["session_id"]

    first = client.post(f"/api/qa-sessions/{session_id}/end")
    assert first.status_code == 200

    second = client.post(f"/api/qa-sessions/{session_id}/end")
    assert second.status_code == 404


def test_end_session_not_found(client: TestClient) -> None:
    resp = client.post("/api/qa-sessions/ghost/end")
    assert resp.status_code == 404


# ============================================================ defensive


def test_default_agent_factory_is_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_agent_factory`` 默认应返回 ``_default_agent_factory``，构造真实 StudentAgent。

    本用例不覆盖 fake_agents fixture，直接验证默认值；不真的 LLM 触网。
    """
    factory = qa_sessions_module.get_agent_factory()
    assert factory is qa_sessions_module._default_agent_factory  # noqa: SLF001
