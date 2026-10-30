from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    database_url: str

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"

    salute_speech_credentials: str = ""
    salute_speech_scope: str = "SALUTE_SPEECH_PERS"

    sber_ca_bundle: str = ""

    default_timezone: str = "Europe/Moscow"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
