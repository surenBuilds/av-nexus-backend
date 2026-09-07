"""Demo seed regression: the seeded chairman must be able to log in end-to-end.

The demo email must pass pydantic's EmailStr validation (a valid, registerable
public TLD) so the whole register/seed -> login -> token -> /me path works.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from av_nexus.db.session import create_session
from av_nexus.seed.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


def test_demo_seed_login_end_to_end(client: TestClient) -> None:
    session = create_session()
    try:
        assert seed_demo(session) is True
    finally:
        session.close()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert token

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["user"]["email"] == DEMO_EMAIL
    assert me.json()["organization"]["name"] == "AV Holding (Demo)"


def test_demo_email_is_valid_registrable_tld() -> None:
    from pydantic import BaseModel, EmailStr

    class EmailModel(BaseModel):
        email: EmailStr

    # Guards the exact regression: .local is RFC 6762-reserved and rejected.
    assert EmailModel(email=DEMO_EMAIL).email == DEMO_EMAIL
    assert "@avnexus.local" not in DEMO_EMAIL