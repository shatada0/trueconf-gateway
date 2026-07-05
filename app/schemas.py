from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    id: str
    display_name: str
    email: str
    department: str | None = None


class ConferenceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    participant_ids: list[str] = Field(min_length=1)


class ConferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trueconf_id: str
    title: str
    participant_ids: list[str]
    join_url: str
    created_at: datetime
