import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .db import engine
from .routers import conferences, users
from .trueconf import TrueConfError, client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # PostgreSQL может подниматься дольше API - ждём готовности, затем миграции
    for attempt in range(30):
        try:
            async with engine.connect():
                break
        except Exception:
            if attempt == 29:
                raise
            logger.info("БД ещё не готова, повтор через 1 с...")
            await asyncio.sleep(1)
    # alembic-команды синхронные - уводим в поток, чтобы не блокировать loop
    await asyncio.to_thread(_run_migrations)
    yield
    await client.close()
    await engine.dispose()


app = FastAPI(title="TrueConf Gateway", lifespan=lifespan)
app.include_router(users.router)
app.include_router(conferences.router)


@app.exception_handler(TrueConfError)
async def trueconf_error_handler(request: Request, exc: TrueConfError) -> JSONResponse:
    logger.error("Ошибка TrueConf: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health", tags=["service"])
async def health() -> dict:
    return {"status": "ok"}
