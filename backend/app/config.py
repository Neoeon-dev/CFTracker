from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    cors_origins: str = "http://localhost:5173"
    default_timezone: str = "Asia/Kolkata"
    sync_page_size: int = 1000
    initial_sync_days: int = 30
    admin_key: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
