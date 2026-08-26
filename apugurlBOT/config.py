from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    bot_token: str
    jetton_master_address: str
    tonapi_key: str | None
    tonconnect_manifest_url: str
    tonconnect_public_url: str
    database_path: str
    admin_ids: frozenset[int]
    deposit_wallet_address: str = "UQAuvRd6hDlvppwQh7vqB_el0u-Rjtd50q-0HpfaWOgfTlAO"
    hot_wallet_mnemonic: str = ""
    jetton_decimals: int = 9
    deposit_poll_interval_seconds: int = 60
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    internal_divisor: int = 100
    rain_duration_seconds: int = 30
    duel_result_delay_seconds: int = 3
    duel_accept_timeout_seconds: int = 60
    required_channel_username: str = "ApuGurlOnTon"
    required_group_username: str = "ApugurlCHAT"
    pollinations_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        jetton_master_address = os.getenv("JETTON_MASTER_ADDRESS", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN is required")
        if not jetton_master_address:
            raise RuntimeError("JETTON_MASTER_ADDRESS is required")
        admin_ids = frozenset(
            int(value.strip())
            for value in os.getenv("ADMIN_IDS", "6293460980").split(",")
            if value.strip()
        )
        return cls(
            bot_token=bot_token,
            jetton_master_address=jetton_master_address,
            tonapi_key=os.getenv("TONAPI_KEY") or None,
            tonconnect_manifest_url=os.getenv(
                "TONCONNECT_MANIFEST_URL",
                "https://example.com/tonconnect-manifest.json",
            ),
            tonconnect_public_url=os.getenv("TONCONNECT_PUBLIC_URL", "").strip().rstrip("/"),
            database_path=os.getenv("DATABASE_PATH", "apugurl.sqlite3"),
            admin_ids=admin_ids,
            deposit_wallet_address=os.getenv(
                "DEPOSIT_WALLET_ADDRESS", "UQAuvRd6hDlvppwQh7vqB_el0u-Rjtd50q-0HpfaWOgfTlAO"
            ),
            hot_wallet_mnemonic=os.getenv("HOT_WALLET_MNEMONIC", "").strip(),
            jetton_decimals=int(os.getenv("JETTON_DECIMALS", "9")),
            deposit_poll_interval_seconds=int(os.getenv("DEPOSIT_POLL_INTERVAL_SECONDS", "60")),
            web_host=os.getenv("WEB_HOST", "0.0.0.0"),
            web_port=int(os.getenv("WEB_PORT", "8080")),
            rain_duration_seconds=int(os.getenv("RAIN_DURATION_SECONDS", "30")),
            duel_result_delay_seconds=int(os.getenv("DUEL_RESULT_DELAY_SECONDS", "3")),
            duel_accept_timeout_seconds=int(os.getenv("DUEL_ACCEPT_TIMEOUT_SECONDS", "60")),
            required_channel_username=os.getenv("REQUIRED_CHANNEL_USERNAME", "ApuGurlOnTon").lstrip("@"),
            required_group_username=os.getenv("REQUIRED_GROUP_USERNAME", "ApugurlCHAT").lstrip("@"),
            pollinations_api_key=os.getenv("POLLINATIONS_API_KEY", "").strip(),
        )
