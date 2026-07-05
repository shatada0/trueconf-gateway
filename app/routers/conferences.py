from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Conference
from ..schemas import ConferenceCreate, ConferenceOut
from ..trueconf import client

router = APIRouter(tags=["conferences"])


@router.post(
    "/conferences",
    response_model=ConferenceOut,
    status_code=201,
    summary="Создать конференцию и сохранить ссылку",
)
async def create_conference(
    payload: ConferenceCreate, session: AsyncSession = Depends(get_session)
) -> Conference:
    resp = await client.request(
        "POST",
        "/conferences",
        json={"title": payload.title, "participants": payload.participant_ids},
    )
    if resp.status_code == 422:
        # Несуществующие участники - пробрасываем ответ мока как есть
        raise HTTPException(status_code=422, detail=resp.json().get("detail"))
    if resp.status_code != 201:
        raise HTTPException(status_code=502, detail="Неожиданный ответ TrueConf")

    data = resp.json()
    conf = Conference(
        trueconf_id=data["id"],
        title=data["title"],
        participant_ids=data["participants"],
        join_url=data["join_url"],
    )
    session.add(conf)
    await session.commit()
    await session.refresh(conf)
    return conf


@router.get("/conferences", response_model=list[ConferenceOut], summary="Сохранённые конференции")
async def list_conferences(session: AsyncSession = Depends(get_session)) -> list[Conference]:
    result = await session.execute(select(Conference).order_by(Conference.created_at))
    return list(result.scalars())


@router.get("/conferences/{conference_id}", response_model=ConferenceOut, summary="Конференция по id")
async def get_conference(
    conference_id: str, session: AsyncSession = Depends(get_session)
) -> Conference:
    conf = await session.get(Conference, conference_id)
    if conf is None:
        raise HTTPException(status_code=404, detail="Конференция не найдена")
    return conf
