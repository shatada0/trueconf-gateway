from fastapi import APIRouter, HTTPException

from ..schemas import User
from ..trueconf import client

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[User], summary="Поиск пользователей TrueConf")
async def search_users(query: str = "") -> list[User]:
    resp = await client.request("GET", "/users", params={"query": query})
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Неожиданный ответ TrueConf")
    return resp.json()
