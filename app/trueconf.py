"""Клиент TrueConf: хранит токены в PostgreSQL и сам их обновляет.

Логика получения access_token:
- если в БД есть неистёкший токен (с запасом leeway) - используем его;
- иначе под asyncio.Lock: перечитываем БД (пока ждали лок, сосед мог уже
  обновить пару), затем пробуем /refresh, при невалидном refresh - /token.
- любой запрос к моку при 401 один раз повторяется со свежим токеном
  (реактивный refresh); токен, на котором получили 401, помечается как stale,
  чтобы не вернуть его же из БД повторно.

Ротация refresh безопасна: обновление идёт строго под локом, поэтому два
конкурентных 401 не сожгут один refresh_token дважды.

Поверх БД - кэш пары в памяти: читаем PostgreSQL только на холодном старте,
дальше все чтения из кэша (пишет в него только этот же клиент под локом,
поэтому в рамках одного процесса кэш всегда когерентен).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .models import TokenPair

logger = logging.getLogger(__name__)


class TrueConfError(Exception):
    """Мок TrueConf недоступен или авторизация не удалась."""


class TrueConfClient:
    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        # retries - повтор при сетевых ошибках подключения (мок перезапустился и т.п.)
        self._http = http or httpx.AsyncClient(
            base_url=settings.trueconf_base_url,
            timeout=10,
            transport=httpx.AsyncHTTPTransport(retries=2),
        )
        # asyncio.Lock хватает для одного процесса; при нескольких
        # инстансах API нужен SELECT ... FOR UPDATE на строке токенов.
        self._lock = asyncio.Lock()
        self._cache: TokenPair | None = None  # кэш пары поверх БД

    async def close(self) -> None:
        await self._http.aclose()

    # -- токены --------------------------------------------------------------

    async def _load_pair(self) -> TokenPair | None:
        if self._cache is not None:
            return self._cache
        async with SessionLocal() as session:
            self._cache = await session.get(TokenPair, 1)
        return self._cache

    async def _save_pair(self, data: dict) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        async with SessionLocal() as session:
            stmt = insert(TokenPair).values(
                id=1,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                access_expires_at=expires_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[TokenPair.id],
                set_={
                    "access_token": stmt.excluded.access_token,
                    "refresh_token": stmt.excluded.refresh_token,
                    "access_expires_at": stmt.excluded.access_expires_at,
                    # onupdate из модели не срабатывает при ON CONFLICT -
                    # обновляем явно
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
            await session.commit()
        self._cache = TokenPair(
            id=1,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            access_expires_at=expires_at,
        )
        return data["access_token"]

    def _is_usable(self, pair: TokenPair | None, stale: str | None) -> bool:
        if pair is None or pair.access_token == stale:
            return False
        leeway = timedelta(seconds=settings.token_refresh_leeway)
        return pair.access_expires_at > datetime.now(timezone.utc) + leeway

    async def _get_access_token(self, stale: str | None = None) -> str:
        """Вернуть валидный access_token; stale - токен, на котором словили 401."""
        pair = await self._load_pair()
        if self._is_usable(pair, stale):
            return pair.access_token
        async with self._lock:
            pair = await self._load_pair()  # мог обновиться, пока ждали лок
            if self._is_usable(pair, stale):
                return pair.access_token
            return await self._authorize(pair)

    async def _authorize(self, pair: TokenPair | None) -> str:
        """Обновить пару через /refresh, при неудаче - заново через /token."""
        if pair is not None:
            resp = await self._http.post(
                "/refresh", json={"refresh_token": pair.refresh_token}
            )
            if resp.status_code == 200:
                logger.info("Токены обновлены через /refresh")
                return await self._save_pair(resp.json())
            logger.warning("Refresh не удался (%s), авторизуемся заново", resp.status_code)
        resp = await self._http.post(
            "/token",
            json={
                "client_id": settings.trueconf_client_id,
                "client_secret": settings.trueconf_client_secret,
            },
        )
        if resp.status_code != 200:
            raise TrueConfError(f"Авторизация в TrueConf не удалась: {resp.status_code}")
        logger.info("Получена новая пара токенов через /token")
        return await self._save_pair(resp.json())

    # -- запросы к API мока ----------------------------------------------------

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Запрос с Bearer-токеном и одним повтором после 401."""
        try:
            token = await self._get_access_token()
            resp = await self._http.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            if resp.status_code == 401:
                token = await self._get_access_token(stale=token)
                resp = await self._http.request(
                    method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
                )
            return resp
        except httpx.HTTPError as exc:
            raise TrueConfError(f"TrueConf недоступен: {exc}") from exc


client = TrueConfClient()
