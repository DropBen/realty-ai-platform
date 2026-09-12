import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "disabled"

from realty.config import settings  # noqa: E402
from realty.db import Base, get_db  # noqa: E402
from realty.main import app  # noqa: E402


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> Generator[sessionmaker[Session], None, None]:
    url = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        **({"poolclass": StaticPool} if url == "sqlite://" else {}),
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("realty.jobs.SessionLocal", factory)
    monkeypatch.setattr("realty.main.SessionLocal", factory)
    monkeypatch.setattr(settings, "storage_path", str(Path("data/test-documents").resolve()))
    yield factory
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def register(client: TestClient, suffix: str = "one") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Agent " + suffix,
            "email": f"agent-{suffix}@example.com",
            "password": "secure-password-123!",
            "organization": "Agency " + suffix,
        },
    )
    assert response.status_code == 201, response.text
    client.headers["x-csrf-token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def account(client: TestClient) -> dict:
    return register(client)


@pytest.fixture
def contact(client: TestClient, account: dict) -> dict:
    response = client.post(
        "/api/v1/crm/contacts",
        json={"name": "Jordan Buyer", "email": "buyer@example.com", "kind": "buyer"},
    )
    assert response.status_code == 201, response.text
    return response.json()
