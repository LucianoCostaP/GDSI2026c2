from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    front_origin: str = "http://localhost:5173"
    app_env: str = "local"


settings = Settings()
