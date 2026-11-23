import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'inventory.db'}")
    model_path: Path = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "forecast_model.joblib"))
    seed_data_path: Path = Path(os.getenv("SEED_DATA_PATH", BASE_DIR / "data" / "sales.csv"))
    require_model_manifest: bool = os.getenv("REQUIRE_MODEL_MANIFEST", "true").lower() == "true"
    seed_on_start: bool = os.getenv("SEED_ON_START", "true").lower() == "true"

    forecast_window_days: int = int(os.getenv("FORECAST_WINDOW_DAYS", "7"))
    service_level_z: float = float(os.getenv("SERVICE_LEVEL_Z", "1.65"))

    app_env: str = os.getenv("APP_ENV", "dev")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_minutes: int = int(os.getenv("JWT_MINUTES", "30"))
    initial_manager_password: str = os.getenv("INITIAL_MANAGER_PASSWORD", "")
    initial_viewer_password: str = os.getenv("INITIAL_VIEWER_PASSWORD", "")
    login_max_failures: int = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    login_window_seconds: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))

    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    app_version: str = os.getenv("APP_VERSION", "dev")


settings = Settings()
