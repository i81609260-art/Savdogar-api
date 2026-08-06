"""Tur operator konnektorlari — umumiy shartnoma va reyestr.

Konnektor — bu bitta operatorning B2B kabinetidan natija oladigan modul.
Bu fayl ularning **umumiy interfeysi**: kirish nima, chiqish nima, xato
qanday qaytadi. Aniq operator mantiqi alohida modullarda.

Ikkita qaror bu yerda muhrlangan
--------------------------------

**1. Konnektor brauzer qayerda ishlashini bilmaydi.**
Bir xil konnektor kodi ham serverda (headless), ham turagentning o'z
mashinasida ishlaydi. Farq faqat `runner` da. Shuning uchun konnektorda
`playwright` global import qilinmaydi va sahifa obyekti tashqaridan
beriladi — keyinchalik "brauzer agent tomonida" qaroriga o'tsak, konnektor
kodi umuman o'zgarmaydi.

**2. Konnektor dvigatelga yoziladi, operatorga emas.**
Ko'p operator o'z qidiruv tizimini yozmagan — tayyor B2B dvigatel
ishlatadi. Shuning uchun reyestr `OperatorEngine` bo'yicha: bitta konnektor
o'nlab operatorga xizmat qiladi.

Captcha
-------
Captcha yechish xizmati **ataylab yo'q**. Brauzer turagent ko'rib turgan
haqiqiy brauzer bo'lgani uchun captcha chiqsa agent o'zi bosadi. Konnektor
shunchaki `CAPTCHA` holatini qaytaradi va Socket.IO orqali agentga
"tasdiqlang" tugmasi ko'rsatiladi.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

from app.models.tour_operator import OperatorEngine
from app.services.tella_tour_search import TourSearchQuery

log = logging.getLogger(__name__)


class ConnectorStatus(StrEnum):
    """Konnektor ishining natijasi."""

    OK = "ok"
    AUTH_FAILED = "auth_failed"     # login/parol noto'g'ri
    CAPTCHA = "captcha"             # agent o'zi bosishi kerak
    NO_RESULTS = "no_results"       # ishladi, lekin mos taklif yo'q
    UNSUPPORTED = "unsupported"     # bu operator uchun konnektor yo'q
    TIMEOUT = "timeout"
    ERROR = "error"

    @property
    def is_success(self) -> bool:
        return self in (ConnectorStatus.OK, ConnectorStatus.NO_RESULTS)

    @property
    def needs_agent(self) -> bool:
        """Turagent aralashuvi kerakmi (captcha, parol)."""
        return self in (ConnectorStatus.CAPTCHA, ConnectorStatus.AUTH_FAILED)


@dataclass
class RawOffer:
    """Operatordan olingan **xom** taklif.

    Ataylab hech narsa normallashtirilmagan — operator nima bersa shu.
    Kanonik ko'rinishga o'tkazish alohida bosqichda bo'ladi, shunda
    normalizatsiya qoidasi o'zgarganda konnektorlarga tegilmaydi va
    `raw` saqlangani uchun eski natijalarni qayta ishlash mumkin.
    """

    hotel_name: str
    price_gross: Optional[float] = None
    price_net: Optional[float] = None
    currency: Optional[str] = None
    board: Optional[str] = None
    star: Optional[str] = None
    room: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    date_from: Optional[str] = None
    nights: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    flight_included: Optional[bool] = None
    transfer_included: Optional[bool] = None
    commission_pct: Optional[float] = None
    deep_link: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorContext:
    """Konnektorga beriladigan hamma narsa.

    Parol shu yerga **ochilgan holda** keladi — bazada shifrlangan, xotirada
    ochiq. Loglarga hech qachon tushmasligi kerak, `__repr__` shuning uchun
    qayta yozilgan.
    """

    query: TourSearchQuery
    login: Optional[str] = None
    password: Optional[str] = None
    # Playwright `storage_state` — oldingi seansdan saqlangan cookie'lar.
    # Bo'lsa login bosqichi butunlay o'tkazib yuboriladi.
    storage_state: Optional[dict] = None
    login_url: Optional[str] = None
    # Brauzer sahifasi. Server rejimida runner beradi; test rejimida `None`.
    page: Any = None
    timeout_ms: int = 60_000

    def __repr__(self) -> str:  # noqa: D105 — parol sizib chiqmasin
        return (
            f"ConnectorContext(login={'bor' if self.login else 'yoq'}, "
            f"password=***, session={'bor' if self.storage_state else 'yoq'})"
        )


@dataclass
class ConnectorResult:
    """Konnektor javobi."""

    status: ConnectorStatus
    offers: list[RawOffer] = field(default_factory=list)
    # Yangilangan sessiya — bo'lsa bazaga shifrlab yoziladi va keyingi
    # qidiruvda login bosqichi tashlab ketiladi.
    storage_state: Optional[dict] = None
    error: Optional[str] = None
    # Diagnostika: qancha vaqt ketdi, nechta sahifa ochildi.
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, offers: list[RawOffer], **kw) -> "ConnectorResult":
        status = ConnectorStatus.OK if offers else ConnectorStatus.NO_RESULTS
        return cls(status=status, offers=offers, **kw)

    @classmethod
    def failure(cls, status: ConnectorStatus, error: str, **kw) -> "ConnectorResult":
        return cls(status=status, offers=[], error=error[:500], **kw)


class OperatorConnector(ABC):
    """Bitta B2B dvigatel uchun konnektor.

    Amalga oshirishda ikki narsani unutmang:

    * `search()` **hech qachon istisno tashlamasin** — har qanday nosozlik
      `ConnectorResult.failure(...)` bo'lib qaytsin. Bitta operator sinsa
      qolgan 17 tasi ishlashda davom etishi kerak.
    * Parolni logga yozmang. `ctx` ning `__repr__` i himoyalangan, lekin
      `ctx.password` ni to'g'ridan-to'g'ri yozib yuborish mumkin.
    """

    #: Qaysi dvigatel uchun. Reyestr shu bo'yicha topadi.
    engine: OperatorEngine = OperatorEngine.CUSTOM
    #: Brauzer kerakmi. `False` bo'lsa (masalan RFQ/price-list) runner
    #: brauzer ochmaydi — bu tejamkorlik uchun muhim.
    needs_browser: bool = True

    @abstractmethod
    async def search(self, ctx: ConnectorContext) -> ConnectorResult:
        """Qidiruvni bajaradi va xom takliflarni qaytaradi."""

    async def check_login(self, ctx: ConnectorContext) -> ConnectorResult:
        """Login ishlayotganini tekshiradi (agent hisob qo'shganda).

        Standart amalga oshirish — bo'sh so'rov bilan qidirish. Konnektor
        arzonroq yo'lni bilsa qayta yozadi.
        """
        return await self.search(ctx)


class ManualConnector(OperatorConnector):
    """Sayti/kabineti yo'q operator uchun.

    Bunday operatorlar bor va ular yo'qolmaydi: narxni Telegram yoki
    telefon orqali beradi. Ular avtomatik qidiruvga qo'shilmaydi, lekin
    reyestrda turadi — keyinchalik RFQ (so'rov yuborish) va price-list
    tahlili shu yerga ulanadi.
    """

    engine = OperatorEngine.MANUAL
    needs_browser = False

    async def search(self, ctx: ConnectorContext) -> ConnectorResult:
        return ConnectorResult.failure(
            ConnectorStatus.UNSUPPORTED,
            "Bu operatorda avtomatik qidiruv yo'q — so'rov qo'lda yuboriladi.",
        )


# --------------------------------------------------------------------------
# Reyestr
# --------------------------------------------------------------------------
class ConnectorRegistry:
    """Dvigatel -> konnektor moslamasi."""

    def __init__(self) -> None:
        self._by_engine: dict[str, OperatorConnector] = {}

    def register(self, connector: OperatorConnector) -> OperatorConnector:
        """Konnektorni ro'yxatga oladi. Dekorator sifatida ham ishlaydi."""
        engine = str(connector.engine)
        if engine in self._by_engine:
            log.warning("Konnektor almashtirildi: %s", engine)
        self._by_engine[engine] = connector
        return connector

    def get(self, engine: str | OperatorEngine) -> Optional[OperatorConnector]:
        return self._by_engine.get(str(engine))

    def supports(self, engine: str | OperatorEngine) -> bool:
        return str(engine) in self._by_engine

    @property
    def engines(self) -> list[str]:
        return sorted(self._by_engine)


registry = ConnectorRegistry()
registry.register(ManualConnector())


async def run_connector(
    engine: str | OperatorEngine, ctx: ConnectorContext
) -> ConnectorResult:
    """Konnektorni xavfsiz chaqiradi.

    Bu yagona kirish nuqtasi bo'lishi shart: shu yerda har qanday istisno
    tutiladi. Aks holda bitta operatorning kutilmagan xatosi butun
    qidiruvni yiqitardi — 18 tadan 17 tasi ishlagan bo'lsa ham.
    """
    connector = registry.get(engine)
    if connector is None:
        return ConnectorResult.failure(
            ConnectorStatus.UNSUPPORTED, f"'{engine}' uchun konnektor yo'q"
        )
    try:
        return await connector.search(ctx)
    except TimeoutError as exc:
        return ConnectorResult.failure(ConnectorStatus.TIMEOUT, str(exc) or "vaqt tugadi")
    except Exception as exc:  # noqa: BLE001 — bitta operator butunini yiqitmasin
        log.exception("Konnektor xatosi: %s", engine)
        return ConnectorResult.failure(ConnectorStatus.ERROR, f"{type(exc).__name__}: {exc}")
