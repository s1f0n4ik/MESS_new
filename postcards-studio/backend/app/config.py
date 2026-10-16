from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUDIO_", env_file="../.env", extra="ignore")

    secret_key: str = "development-secret-change-me"
    admin_email: str = "admin@example.org"
    admin_password: str = "change-me-now"
    database_url: str = "sqlite:///./data/studio.db"
    storage_dir: Path = Path("./data")
    template_pdf: Path = Path("../../docs/deliverables/Postcards_2x2_template_14_blocks.pdf")
    sync_token: str = "development-sync-token"
    collaboration_secret: str = "development-collaboration-secret"
    public_url: str = "http://localhost:8080"
    token_hours: int = 24
    history_interval_minutes: int = 15
    history_limit: int = 50
    environment: str = "development"
    yandex_webdav_url: str = "https://webdav.yandex.ru"
    yandex_disk_api_url: str = "https://cloud-api.yandex.net/v1/disk"
    yandex_disk_oauth_token: str = ""
    yandex_disk_username: str = ""
    yandex_disk_app_password: str = ""
    yandex_disk_path: str = ""

    @property
    def yandex_delivery_enabled(self) -> bool:
        return bool(
            self.yandex_disk_path and (
                self.yandex_disk_oauth_token
                or (self.yandex_disk_username and self.yandex_disk_app_password)
            )
        )

    def validate_runtime(self) -> None:
        if self.environment.lower() != "production":
            return
        unsafe = {
            "STUDIO_SECRET_KEY": self.secret_key == "development-secret-change-me" or len(self.secret_key) < 32,
            "STUDIO_ADMIN_PASSWORD": self.admin_password == "change-me-now" or len(self.admin_password) < 12,
            "STUDIO_SYNC_TOKEN": self.sync_token == "development-sync-token" or len(self.sync_token) < 24,
            "STUDIO_COLLABORATION_SECRET": self.collaboration_secret == "development-collaboration-secret" or len(self.collaboration_secret) < 24,
        }
        missing = [name for name, bad in unsafe.items() if bad]
        if missing:
            raise RuntimeError(f"Небезопасная production-конфигурация: задайте {', '.join(missing)}")
        webdav_values = (self.yandex_disk_username, self.yandex_disk_app_password)
        if any(webdav_values) and not all(webdav_values):
            raise RuntimeError(
                "Для WebDAV задайте STUDIO_YANDEX_DISK_USERNAME и "
                "STUDIO_YANDEX_DISK_APP_PASSWORD"
            )
        if (self.yandex_disk_oauth_token or any(webdav_values)) and not self.yandex_disk_path:
            raise RuntimeError("Для доставки задайте STUDIO_YANDEX_DISK_PATH")


@lru_cache
def settings() -> Settings:
    value = Settings()
    value.storage_dir.mkdir(parents=True, exist_ok=True)
    return value
