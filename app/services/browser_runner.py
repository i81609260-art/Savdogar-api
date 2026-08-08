"""Konnektorlar uchun brauzer seansi.

Bu — yetishmayotgan bo'g'in edi. `PlaywrightConnector` login mantiqini
allaqachon biladi (`login_url` ga o'tish, maydonlarni to'ldirish, captcha va
parol xatosini ajratish), lekin unga `page` obyektini HECH KIM bermasdi:
`ConnectorContext.page` doim `None` bo'lib qolardi. Natijada turagent kabinet
manzili va login-parolni kiritardi, ular shifrlanib saqlanardi — va shu bilan
tamom, hech qayerga kirilmasdi.

Playwright ATAYLAB dangasa import qilinadi. Agar brauzer o'rnatilmagan
bo'lsa, ilova ishga tushishi buzilmasligi kerak — faqat shu funksiya aniq
xato qaytaradi. Aks holda bitta yetishmayotgan kutubxona butun API'ni
yiqitardi.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Brauzer o'rnatilmagan muhitda (mahalliy sinov, eski deploy) aniq xabar.
BROWSER_MISSING = (
    "Brauzer o'rnatilmagan. Serverda `playwright install chromium` "
    "bajarilishi kerak."
)

# Kabinetlar sekin ochiladi — 60 soniya yetarli, lekin cheksiz emas.
DEFAULT_TIMEOUT_MS = 60_000

# Datacenter IP'dan kelayotgani ko'zga tashlanmasin: oddiy brauzer kabi
# ko'rinsin. Bu captcha ehtimolini kamaytiradi, lekin yo'q qilmaydi.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BrowserUnavailable(RuntimeError):
    """Playwright yoki brauzer topilmadi."""


@dataclass
class BrowserOutcome:
    """Seans natijasi va undan keyingi cookie holati."""

    value: Any = None
    storage_state: Optional[dict] = None


async def run_in_browser(
    action: Callable[[Any], Awaitable[T]],
    *,
    storage_state: Optional[dict] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> BrowserOutcome:
    """Brauzer ochib, `action(page)` ni bajaradi va seansni qaytaradi.

    `storage_state` berilsa oldingi seans tiklanadi — shunda login formasi
    umuman ochilmaydi va operator sayti har safar yangi kirishni ko'rmaydi.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # noqa: BLE001
        raise BrowserUnavailable(BROWSER_MISSING) from exc

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                # Konteynerda /dev/shm kichik bo'ladi — busiz Chromium
                # katta sahifalarda kutilmaganda yiqiladi.
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
        except Exception as exc:  # noqa: BLE001
            raise BrowserUnavailable(f"{BROWSER_MISSING} ({exc})") from exc

        try:
            context = await browser.new_context(
                storage_state=storage_state or None,
                user_agent=_USER_AGENT,
                locale="ru-RU",  # kabinetlar asosan rus tilida
            )
            context.set_default_timeout(timeout_ms)
            page = await context.new_page()
            try:
                value = await action(page)
                # Seansni FAQAT amal tugagach olamiz — cookie'lar shu paytda
                # to'liq bo'ladi.
                state = await context.storage_state()
                return BrowserOutcome(value=value, storage_state=state)
            finally:
                await context.close()
        finally:
            await browser.close()
