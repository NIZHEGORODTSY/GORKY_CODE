from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    database_url: str

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-3-Pro"
    gigachat_embeddings_model: str = "Embeddings"

    tts_voice: str = "ru-RU-SvetlanaNeural"

    # Публичный HTTPS-адрес Mini App (календарь); пусто — кнопка календаря не показывается
    webapp_url: str = ""
    webapp_domain: str = ""  # если WEBAPP_URL пуст, адрес собирается как https://<домен>/app/
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8080

    sber_ca_bundle: str = ""

    default_timezone: str = "Europe/Moscow"
    log_level: str = "INFO"


    @property
    def public_webapp_url(self) -> str:
        if self.webapp_url:
            return self.webapp_url
        return f"https://{self.webapp_domain}/app/" if self.webapp_domain else ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
