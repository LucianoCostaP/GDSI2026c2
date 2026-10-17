from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    front_origin: str = "http://localhost:5173"
    app_env: str = "local"
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
    initial_admin_email: str | None = None
    initial_admin_name: str | None = None


settings = Settings()
