"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Savdogar platform settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Savdogar"
    debug: bool = False
    secret_key: str = "dev-secret-key-change-in-production-min-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    database_url: str = "sqlite+aiosqlite:///./savdogar.db"
    # Railway persistent volume mount path (set to /data in Railway Variables)
    data_dir: str = ""

    @property
    def async_database_url(self) -> str:
        """Use persistent volume path for SQLite, or convert postgres:// for asyncpg."""
        url = self.database_url
        # If data_dir is set (Railway volume), store SQLite there
        if self.data_dir and url.startswith("sqlite"):
            return f"sqlite+aiosqlite:///{self.data_dir}/savdogar.db"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # SAIR tashqi platforma integratsiyasi
    sair_api_url: str = "http://localhost:8001"
    sair_api_key: str = ""
    sair_webhook_secret: str = ""
    savdogar_public_url: str = "http://localhost:8000"

    # Instagram / Meta integratsiyasi (lead yigish).
    # DIQQAT: bularni hech qachon kodga yozmang — faqat environment variable.
    # App Secret Meta konsolida ochilib qolsa, darhol Reset App Secret qiling.
    # Meta'da ikki xil yol bor va ikkalasining OZ app secret'i bor:
    #   1) "Instagram API with Instagram login"  -> graph.instagram.com
    #      Webhook imzosi INSTAGRAM_APP_SECRET bilan hisoblanadi.
    #   2) "API setup with Facebook login"       -> graph.facebook.com
    #      Webhook imzosi FACEBOOK_APP_SECRET bilan hisoblanadi.
    # Qaysi biri ishlatilsa oshanisi toldiriladi; ikkalasi ham bolsa — ikkalasi
    # ham tekshiriladi, shuning uchun yolni almashtirsangiz ham buzilmaydi.
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    # Meta webhook'ni tasdiqlash uchun ozingiz oylab topadigan maxfiy matn.
    # Meta konsolidagi "Verify token" maydoniga aynan shu qiymat yoziladi.
    instagram_verify_token: str = ""
    # Graph API versiyasi.
    facebook_graph_version: str = "v21.0"

    @property
    def webhook_secrets(self) -> List[str]:
        """Webhook imzosini tekshirishda sinaladigan barcha secret'lar."""
        return [s for s in (self.instagram_app_secret, self.facebook_app_secret) if s]

    # Telegram bot
    telegram_bot_token: str = ""
    # Platforma egasiga xabar boradigan chat ID(lar), vergul bilan.
    # Bo'sh bo'lsa tarif o'zgarishi haqidagi xabarnoma o'chiq turadi.
    telegram_admin_chat_ids: str = ""
    cors_origins: str = (
        "http://localhost:3000,"
        "https://savdogar-sable.vercel.app,"
        "https://savdogar-five.vercel.app,"
        "https://savdogar-agentligi.vercel.app"
    )

    # Qo'ng'iroq tahlili (Gemini audio'ni to'g'ridan-to'g'ri qabul qiladi).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Ommaviy sayt manzili (email/telegram havolalarida ishlatiladi).
    frontend_url: str = "https://turify.xyz"

    upload_dir: str = "uploads"
    max_upload_size_mb: int = 5
    max_audio_upload_mb: int = 15

    @property
    def persistent_upload_dir(self) -> str:
        """Use persistent volume for uploads if available, otherwise use default."""
        if self.data_dir:
            return f"{self.data_dir}/uploads"
        return self.upload_dir

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_email: str = "mailto:admin@sayr.uz"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@savdogar.uz"

    socket_cors_origins: str = (
        "http://localhost:3000,"
        "https://savdogar-sable.vercel.app,"
        "https://savdogar-five.vercel.app,"
        "https://savdogar-agentligi.vercel.app"
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def socket_cors_list(self) -> List[str]:
        """Parse comma-separated Socket.io CORS origins."""
        return [o.strip() for o in self.socket_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
