from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    test_database_url: str = "postgresql+psycopg://app:app@localhost:5432/app_test"
    db_engine: str = "postgres"
    front_origin: str = "http://localhost:5173"
    app_env: str = "local"
    freshness_hours_limit: int = 24
    app_name: str = "Pasión de 10 - API Unificada"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "Pasión de 10 <no-reply@pasionde10.local>"
    # Pedidos de código (activación y login), cross-cutting sección 3.
    ip_rate_limit: int = 10
    ip_rate_window_seconds: int = 60
    identifier_rate_limit: int = 5
    identifier_rate_window_seconds: int = 3600
    access_code_expiry_minutes: int = 10
    access_code_max_attempts: int = 5
    access_code_resend_seconds: int = 60
    identifier_lock_minutes: int = 15
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    admin_invitation_expiry_hours: int = 48
    # Primer admin (tarea de arranque): se crea al iniciar si todavía no hay ningún admin.
    initial_admin_email: str | None = "admin@club.com"
    initial_admin_name: str | None = "Admin Demo"

    # Parámetros de publicación de eventos (HU-22 / Cross-cutting sección 8)
    default_partido_clase: str = "B"
    default_institucional_puntos: int = 20
    min_publication_lead_hours: int = 48
    publication_window_hours: int = 24

    # Compatibilidad con alias en mayúsculas
    @property
    def APP_NAME(self) -> str:
        return self.app_name

    @property
    def APP_VERSION(self) -> str:
        return self.app_version

    @property
    def API_V1_PREFIX(self) -> str:
        return self.api_v1_prefix

    @property
    def DB_ENGINE(self) -> str:
        return self.db_engine

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url

    @property
    def TEST_DATABASE_URL(self) -> str:
        return self.test_database_url

    @property
    def HOST(self) -> str:
        return self.host

    @property
    def PORT(self) -> int:
        return self.port

    @property
    def DEBUG(self) -> bool:
        return self.debug


settings = Settings()
