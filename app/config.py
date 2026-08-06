"""Application configuration loaded from environment variables."""

import hashlib
import hmac
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Kodga yozilgan zaxira kalit. Production'da SECRET_KEY environment
# o'zgaruvchisi ORQALI albatta almashtiriladi — aks holda bu kalitni bilgan
# odam istalgan foydalanuvchi (shu jumladan superadmin) uchun yaroqli JWT
# yasay oladi. `Settings.secret_key_is_default` shuni tekshiradi.
DEV_SECRET_KEY = "dev-secret-key-change-in-production-min-32"


class Settings(BaseSettings):
    """Savdogar platform settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Savdogar"
    debug: bool = False
    secret_key: str = DEV_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Turagentlarning tur operator kabinetidagi login/parol/sessiyasini
    # shifrlash kaliti. Bo'sh bo'lsa SECRET_KEY dan hosil qilinadi — ishlaydi,
    # lekin SECRET_KEY almashtirilsa saqlangan parollar o'qilmay qoladi.
    # Yaratish:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_key: str = ""

    # Superadmin hisobi. Parol FAQAT hisob mavjud bo'lmaganda ishlatiladi —
    # keyinchalik paneldan yoki SUPERADMIN_PASSWORD orqali o'zgartirilgan parol
    # server qayta ishga tushganda tiklanib ketmaydi.
    superadmin_email: str = "admin@turify.xyz"
    superadmin_password: str = "admin123"
    # Login formasiga qisqa "admin" yozilsa shu email'ga o'giriladi.
    superadmin_login_alias: str = "admin"
    # true bo'lsa har startup'da parol SUPERADMIN_PASSWORD ga majburan
    # qaytariladi (parol unutilganda bir martalik tiklash uchun).
    superadmin_force_reset: bool = False

    @property
    def secret_key_is_default(self) -> bool:
        """Kalit almashtirilmaganmi — startup'da ogohlantirish uchun."""
        return self.secret_key == DEV_SECRET_KEY

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
    # OAuth qaytish manzili. Bosh bolsa savdogar_public_url dan yasaladi.
    # Meta konsolidagi "Valid OAuth Redirect URIs" bilan AYNAN mos bolishi shart.
    instagram_redirect_uri: str = ""

    @property
    def webhook_secrets(self) -> List[str]:
        """Webhook imzosini tekshirishda sinaladigan barcha secret'lar."""
        return [s for s in (self.instagram_app_secret, self.facebook_app_secret) if s]

    @property
    def instagram_oauth_redirect(self) -> str:
        """Instagram Business Login qaytish manzili."""
        if self.instagram_redirect_uri:
            return self.instagram_redirect_uri
        return self.savdogar_public_url.rstrip("/") + "/api/instagram/oauth/callback"

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

    @property
    def private_dir(self) -> str:
        """Maxfiy fayllar (qo'ng'iroq yozuvlari) papkasi.

        /uploads dan FARQLI o'laroq bu papka statik tarzda tarqatilmaydi —
        fayllar faqat autentifikatsiyadan o'tgan endpoint orqali beriladi.
        """
        if self.data_dir:
            return f"{self.data_dir}/private"
        return "private"

    def webhook_id_for(self, token: str) -> str:
        """Telegram bot tokenidan webhook yo'li uchun taxallus hosil qiladi.

        Tokenning o'zini URL'da yubormaymiz: URL server/proxy loglariga tushadi
        va log'ni ko'rgan odam botni to'liq egallab olardi.
        """
        return hmac.new(
            self.secret_key.encode(), token.encode(), hashlib.sha256
        ).hexdigest()[:32]

    @property
    def telegram_webhook_secret(self) -> str:
        """Telegram `secret_token` — har so'rov sarlavhasida tekshiriladi."""
        return hmac.new(
            self.secret_key.encode(), b"telegram-webhook", hashlib.sha256
        ).hexdigest()[:48]

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

    # Har bir firmaning o'z subdomeni bo'lgani uchun ro'yxatning o'zi yetmaydi —
    # *.turify.xyz va Vercel preview'lari naqsh orqali ruxsat etiladi.
    cors_origin_regex: str = (
        r"^https://([a-z0-9-]+\.)*turify\.xyz$"
        r"|^https://[a-z0-9-]+\.vercel\.app$"
        r"|^http://localhost:\d+$"
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Socket.io CORS'ini kim boshqaradi.
    #   "app"  — engineio o'z sarlavhalarini qo'shmaydi, CORS'ni ilovaning
    #            CORSMiddleware'i hal qiladi (naqshni ham qo'llaydi, ya'ni
    #            firma subdomenlari ham ishlaydi). Standart va tavsiya etilgan.
    #   "list" — faqat SOCKET_CORS_ORIGINS ro'yxati (qat'iy, lekin firma
    #            subdomenidan ochilgan admin panelni sindiradi).
    #   "any"  — hammasiga ruxsat (eski xatti-harakat, tavsiya etilmaydi).
    socket_cors_mode: str = "app"

    @property
    def socket_cors_list(self):
        """python-socketio ga beriladigan `cors_allowed_origins` qiymati.

        Muhim: admin panel firma subdomenidan ham ochiladi
        (masalan `firma.turify.xyz/admin`), shuning uchun qat'iy ro'yxat
        realtime'ni sindiradi. Standart rejimda engineio CORS'ga umuman
        aralashmaydi ([] shuni bildiradi) va ishni CORSMiddleware bajaradi —
        u naqsh orqali barcha *.turify.xyz subdomenlarini taniydi.

        Socket ulanishning asosiy himoyasi baribir CORS emas: `connect`
        hodisasi yaroqli JWT talab qiladi, xona esa firma bo'yicha
        tekshiriladi.
        """
        if self.socket_cors_mode == "any":
            return "*"
        if self.socket_cors_mode == "list":
            origins = [
                o.strip() for o in self.socket_cors_origins.split(",") if o.strip()
            ]
            base = self.frontend_url.rstrip("/")
            host = base.replace("https://", "").replace("http://", "")
            for extra in (
                base,
                f"https://www.{host}",
                f"https://app.{host}",
                f"https://superadmin.{host}",
            ):
                if extra not in origins:
                    origins.append(extra)
            return origins
        return []


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
