"""Pytest fixtures. Env is configured BEFORE any av_nexus import so the settings
singleton picks up an isolated SQLite DB and offline deterministic agents."""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="avnexus-tests-")
os.environ["AVNEXUS_DB_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["AVNEXUS_SEED_DEMO"] = "false"
os.environ["AVNEXUS_JWT_SECRET"] = "test-secret"
os.environ["AVNEXUS_LLM_PROVIDER"] = "off"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from av_nexus.db.session import create_session, get_engine  # noqa: E402
from av_nexus.main import create_app  # noqa: E402
from av_nexus.models.base import Base  # noqa: E402


@pytest.fixture()
def db_session() -> Session:
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    session = create_session()
    yield session
    session.close()


@pytest.fixture()
def client() -> TestClient:
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    with TestClient(create_app()) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str = "chair@example.com") -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "test-password-123",
            "full_name": "Test Chairman",
            "org_name": "Test Holding",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}