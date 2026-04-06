from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chess Analyzer API"
    center_bonus: float = 0.2
    check_bonus: float = 0.5
    checkmate_score: float = 100.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
