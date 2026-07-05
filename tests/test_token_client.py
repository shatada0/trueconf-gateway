"""Тесты токен-логики TrueConfClient.

TrueConf эмулируется через httpx.MockTransport (выдача и ротация токенов,
401 на протухший access), PostgreSQL заменён на dict. Никаких внешних
сервисов не нужно: pip install -r requirements-dev.txt && pytest.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.trueconf import TrueConfClient, TrueConfError

pytestmark = pytest.mark.anyio


class FakeTrueConf:
    """Поведение мока: /token, /refresh с ротацией, 401 на невалидный access."""

    def __init__(self) -> None:
        self.valid_access: set[str] = set()
        self.valid_refresh: set[str] = set()
        self.token_calls = 0
        self.refresh_calls = 0
        self.rejected_401 = 0
        self._n = 0

    def _issue(self) -> httpx.Response:
        self._n += 1
        access, refresh = f"acc-{self._n}", f"ref-{self._n}"
        self.valid_access.add(access)
        self.valid_refresh.add(refresh)
        return httpx.Response(
            200,
            json={
                "access_token": access,
                "refresh_token": refresh,
                "token_type": "Bearer",
                "expires_in": 120,
            },
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/token":
            self.token_calls += 1
            body = json.loads(request.content)
            if (body["client_id"], body["client_secret"]) != ("cid", "secret"):
                return httpx.Response(401, json={"detail": "bad credentials"})
            return self._issue()
        if path == "/refresh":
            self.refresh_calls += 1
            token = json.loads(request.content)["refresh_token"]
            if token not in self.valid_refresh:
                return httpx.Response(401, json={"detail": "invalid refresh"})
            self.valid_refresh.discard(token)  # ротация: старый сгорает
            return self._issue()
        # защищённые эндпоинты
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if token not in self.valid_access:
            self.rejected_401 += 1
            return httpx.Response(401, json={"detail": "expired"})
        if path == "/users":
            return httpx.Response(
                200,
                json=[{
                    "id": "a.ivanov@company",
                    "display_name": "Иван Иванов",
                    "email": "a.ivanov@company.ru",
                    "department": "Разработка",
                }],
            )
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def fake() -> FakeTrueConf:
    return FakeTrueConf()


@pytest.fixture
async def client(fake):
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler), base_url="http://mock"
    )
    c = TrueConfClient(http=http)
    store: dict = {}

    async def load():
        return store.get("pair")

    async def save(data):
        store["pair"] = SimpleNamespace(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            access_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=data["expires_in"]),
        )
        return data["access_token"]

    c._load_pair = load  # in-memory вместо PostgreSQL
    c._save_pair = save
    c.store = store
    yield c
    await c.close()


async def test_cold_start_gets_token(client, fake):
    resp = await client.request("GET", "/users")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "a.ivanov@company"
    assert fake.token_calls == 1


async def test_valid_token_reused(client, fake):
    await client.request("GET", "/users")
    await client.request("GET", "/users")
    assert fake.token_calls == 1
    assert fake.refresh_calls == 0


async def test_reactive_refresh_on_401(client, fake):
    await client.request("GET", "/users")
    fake.valid_access.clear()  # access протух на стороне TrueConf
    resp = await client.request("GET", "/users")
    assert resp.status_code == 200
    assert fake.refresh_calls == 1
    assert fake.token_calls == 1  # повторный /token не понадобился


async def test_invalid_refresh_falls_back_to_token(client, fake):
    await client.request("GET", "/users")
    fake.valid_access.clear()
    fake.valid_refresh.clear()  # refresh тоже невалиден
    resp = await client.request("GET", "/users")
    assert resp.status_code == 200
    assert fake.token_calls == 2  # переавторизация по client_id/secret


async def test_concurrent_401_burn_refresh_once(client, fake):
    await client.request("GET", "/users")
    fake.valid_access.clear()
    responses = await asyncio.gather(
        *[client.request("GET", "/users") for _ in range(5)]
    )
    assert [r.status_code for r in responses] == [200] * 5
    # ключевое: ротируемый refresh использован ровно один раз
    assert fake.refresh_calls == 1


async def test_proactive_refresh_before_expiry(client, fake):
    fake.valid_refresh.add("ref-seeded")
    client.store["pair"] = SimpleNamespace(
        access_token="acc-expired",
        refresh_token="ref-seeded",
        access_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    resp = await client.request("GET", "/users")
    assert resp.status_code == 200
    assert fake.rejected_401 == 0  # TrueConf ни разу не увидел протухший токен


async def test_auth_failure_raises(client, fake, monkeypatch):
    monkeypatch.setattr(settings, "trueconf_client_secret", "wrong")
    with pytest.raises(TrueConfError):
        await client.request("GET", "/users")
