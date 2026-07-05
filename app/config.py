from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Все настройки - из переменных окружения (.env)."""

    trueconf_base_url: str
    trueconf_client_id: str
    trueconf_client_secret: str
    database_url: str  # postgresql+asyncpg://user:pass@host:5432/db
    # За сколько секунд до истечения access_token обновлять его проактивно
    token_refresh_leeway: int = 10


settings = Settings()
