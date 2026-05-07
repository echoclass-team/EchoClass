"""Shared test fixtures — auth helpers etc."""

from __future__ import annotations

import pytest

from api.auth_utils import create_access_token


_TEST_USER_ID = "test-user-001"
_TEST_USERNAME = "test_teacher"


@pytest.fixture
def auth_token() -> str:
    """Generate a valid JWT for test requests."""
    return create_access_token(_TEST_USER_ID, _TEST_USERNAME)


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Authorization header dict for REST requests."""
    return {"Authorization": f"Bearer {auth_token}"}
