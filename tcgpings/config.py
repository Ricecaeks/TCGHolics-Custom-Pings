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
    members_role_id: int = 0  # may use /spotted, as well as staff
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
    # One ScrapFly project per retailer, so the dashboard shows where credits go. Blank uses the key above.
    scrapfly_api_key_kmart: str = ""
    scrapfly_api_key_farmers: str = ""
    scrapfly_api_key_warehouse: str = ""
    scrapfly_country: str = "nz"
    scrapfly_usd_per_credit: float = 0.00015  # Discovery plan: US$30 for 200k credits
    scrapfly_cost_budget: int = 0  # max credits per request; 0 = no per-request cap
    zyte_api_key: str = ""
    zyte_geolocation: str = ""  # e.g. NZ; blank lets Zyte choose (an explicit country can cost more)
    zyte_usd_per_request: float = 0.00127  # hardest site tier, plain HTTP, pay as you go
    # Each paid route stops for the rest of the month at its own cap: the ScrapFly plan's credits, and
    # the monthly usage limit set in Zyte's dashboard.
    scrapfly_monthly_credits: int = 200_000
    zyte_monthly_budget_usd: float = 70.0  # the rest of the US$100 total after ScrapFly's US$30 plan
    # All paid routes stop at this monthly total (US$), across every retailer; past 80% Farmers checks fewer
    # regions. Each route also stops at its own cap above, and each retailer at its own config
    # "unblocker_monthly_usd" limit (/retailer set unblocker_limit_usd:), so one store can't eat it all.
    unblocker_monthly_budget_usd: float = 100.0
    unblocker_low_budget_ratio: float = 0.8
    # How long a route rests after the site blocks it, before it's tried again on its own.
    browser_block_cooldown: int = 24 * 3600
    unblocker_block_cooldown: int = 3600

    worker_concurrency: int = 8
    lease_seconds: int = 120
    heartbeat_seconds: int = 15
    node_stale_seconds: int = 60
    leader_lock_key: int = 72_4242_01

    # Sends every alert to this one webhook (a catch-all route), e.g. a beta channel. Works without the bot.
    alert_webhook_url: str = ""
    # The leader creates channels and routes for newly enabled retailers by itself (same as /setup).
    auto_setup: bool = True
    # Link and sync the alert channels in tcgpings/discord/layout.json every 10 minutes.
    channel_layout: bool = True

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
    # `run` also writes here (inside the mounted data folder, so it survives redeploys).
    # A new file each day or at log_file_max_mb; the newest log_file_keep old ones are kept. "" turns it off.
    log_dir: str = "data/logs"
    log_file_max_mb: int = 25
    log_file_keep: int = 7

    @property
    def proxies(self) -> list[str]:
        return [p for p in re.split(r"[\s,]+", self.proxy_urls) if p]


@lru_cache
def get_settings() -> Settings:
    return Settings()
