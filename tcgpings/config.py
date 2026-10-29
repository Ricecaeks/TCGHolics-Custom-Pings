import re
import socket
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Blank lines in .env (e.g. `GUILD_ID=`) fall back to the defaults below.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    node_name: str = Field(default_factory=socket.gethostname)
    database_url: str = ""
    db_pool_size: int = 4

    discord_token: str = ""
    guild_id: int = 0
    staff_role_id: int = 0
    log_channel_id: int = 0

    proxy_urls: str = ""
    # Skips the public-IP lookup used to split rate limits between nodes on the same connection.
    egress_ip: str = ""
    egress_lookup_url: str = "https://api.ipify.org"

    worker_concurrency: int = 8
    lease_seconds: int = 120
    heartbeat_seconds: int = 15
    node_stale_seconds: int = 60
    leader_lock_key: int = 72_4242_01

    default_sku_interval: int = 60
    default_search_interval: int = 300
    store_sync_interval: int = 86_400
    # Repeat alerts for the same product/store/state are suppressed within this window.
    alert_cooldown_seconds: int = 900

    retention_days: int = 30
    backup_enabled: bool = True
    backup_dir: str = "data/backups"
    backup_keep: int = 7
    db_size_warn_mb: int = 400

    data_dir: str = "data"
    dry_run: bool = False
    log_level: str = "INFO"

    @property
    def proxies(self) -> list[str]:
        return [p for p in re.split(r"[\s,]+", self.proxy_urls) if p]


@lru_cache
def get_settings() -> Settings:
    return Settings()
