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

    # Real-browser fetching for sites behind Akamai/DataDome (Farmers, Kmart, ...). Headed Chrome is
    # far less detectable than headless; in Docker it renders into a virtual display (Xvfb).
    browser_headless: bool = False
    browser_channel: str = "chrome"
    browser_profile_dir: str = "data/browser"
    browser_idle_seconds: int = 600

    # Paid unblockers, tried when our own Chrome is denied (net/chain.py). Each is off until its key is set.
    scrapfly_api_key: str = ""
    scrapfly_country: str = "nz"
    scrapfly_usd_per_credit: float = 0.00015  # Discovery plan: US$30 for 200k credits
    scrapfly_cost_budget: int = 0  # max credits per request; 0 = no per-request cap
    zyte_api_key: str = ""
    zyte_geolocation: str = ""  # e.g. NZ; blank lets Zyte choose (an explicit country can cost more)
    zyte_usd_per_request: float = 0.00127  # hardest site tier, plain HTTP, pay as you go
    # Paid routes stop for the rest of the month at this spend; past 80% Farmers checks fewer regions.
    unblocker_monthly_budget_usd: float = 20.0
    unblocker_low_budget_ratio: float = 0.8
    # How long a route rests after the site blocks it, before it's tried again on its own.
    browser_block_cooldown: int = 24 * 3600
    unblocker_block_cooldown: int = 3600

    worker_concurrency: int = 8
    lease_seconds: int = 120
    heartbeat_seconds: int = 15
    node_stale_seconds: int = 60
    leader_lock_key: int = 72_4242_01

    # The leader creates channels and routes for newly enabled retailers by itself (same as /setup).
    auto_setup: bool = True

    default_sku_interval: int = 60
    default_search_interval: int = 300
    default_discover_interval: int = 180
    # Store-level tracking for products found by discovery that match a keyword route.
    max_tracked_per_retailer: int = 150
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
