import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TokenPair(Base):
    """Единственная активная пара токенов TrueConf (одна строка, id=1, upsert)."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    access_token: Mapped[str]
    refresh_token: Mapped[str]
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conference(Base):
    __tablename__ = "conferences"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: uuid.uuid4().hex
    )
    trueconf_id: Mapped[str]
    title: Mapped[str]
    participant_ids: Mapped[list[str]] = mapped_column(JSONB)
    join_url: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
