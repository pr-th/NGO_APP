from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    mongodb_url: str
    db_name: str = "ngo_db"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
