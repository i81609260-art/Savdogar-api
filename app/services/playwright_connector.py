"""Retsept bilan ishlaydigan brauzer konnektori.

Har operatorga alohida kod yozish o'rniga — bitta umumiy konnektor va
operatorga xos **JSON retsept**. Sabab amaliy: operator sayti oyiga bir
marta o'zgaradi, va har safar kodni tahrirlab, deploy qilish kerak
bo'lmasligi kerak. Retsept — ma'lumot, panelda tahrirlanadi.

Login retseptsiz ham ishlaydi
-----------------------------
B2B kabinetlarining login formasi deyarli bir xil: parol maydoni va uning
yonida login maydoni. Shuning uchun login **umumiy qoidalar** bilan
topiladi. Retsept faqat qidiruv qismiga kerak — u har saytda o'ziga xos.

Brauzer qayerda ishlaydi
------------------------
Bu modul buni bilmaydi. `page` tashqaridan beriladi: server (headless),
turagentning mashinasi yoki kelajakdagi brauzer kengaytmasi — konnektor
kodi uchalasida ham bir xil.

Captcha
-------
Yechish xizmati yo'q va rejada ham yo'q: brauzer turagent ko'rib turgan
haqiqiy brauzer bo'lgani uchun captcha chiqsa u o'zi bosadi. Konnektor
shunchaki `CAPTCHA` holatini qaytaradi.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.tour_operator import OperatorEngine
from app.services.operator_connector import (
    ConnectorContext,
    ConnectorResult,
    ConnectorStatus,
    OperatorConnector,
    RawOffer,
    registry,
)
from app.services.pricelist_parser import parse_price
from app.services.tour_taxonomy import match_board, match_star

log = logging.getLogger(__name__)

# Login formasini umumiy qoidalar bilan topish uchun. Tartib muhim:
# aniqroq selektorlar oldinda.
PASSWORD_SELECTORS = (
    "input[type=password]",
    "input[name*=pass i]",
    "input[id*=pass i]",
)
LOGIN_SELECTORS = (
    "input[type=email]",
    "input[name*=login i]",
    "input[name*=email i]",
    "input[name*=user i]",
    "input[id*=login i]",
    "input[id*=user i]",
    "input[type=text]",
)
SUBMIT_SELECTORS = (
    "button[type=submit]",
    "input[type=submit]",
    "button:has-text('Kirish')",
    "button:has-text('Войти')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
)

# Sahifada shular ko'rinsa — login o'tmagan.
AUTH_FAIL_MARKERS = (
    "invalid", "incorrect", "неверн", "ошибка входа", "noto'g'ri",
    "wrong password", "authentication failed",
)
CAPTCHA_MARKERS = (
    "captcha", "recaptcha", "hcaptcha", "капча", "robot",
    "i'm not a robot", "я не робот",
)


# --------------------------------------------------------------------------
# Retsept
# --------------------------------------------------------------------------
@dataclass
class SearchRecipe:
    """Operatorga xos qidiruv ko'rsatmasi.

    Hech bir maydon majburiy emas — retsept bosqichma-bosqich to'ldiriladi.
    `is_usable` faqat eng zarurlari borligini tekshiradi.
    """

    search_url: Optional[str] = None
    # {"destination": "#city", "nights": "#nights", ...}
    fields: dict[str, str] = field(default_factory=dict)
    # Ochiladigan ro'yxatlar uchun: {"board": {"AI": "3", "UAI": "7"}}
    field_values: dict[str, dict[str, str]] = field(default_factory=dict)
    submit: Optional[str] = None
    # Natija qatorlari va ular ichidagi maydonlar.
    row: Optional[str] = None
    row_fields: dict[str, str] = field(default_factory=dict)
    # Natija chiqishini kutish uchun.
    wait_for: Optional[str] = None
    timeout_ms: int = 30_000

    @classmethod
    def from_json(cls, raw: str | dict | None) -> "SearchRecipe":
        """Bazadagi JSON dan yasaydi. Buzuq bo'lsa bo'sh retsept."""
        if not raw:
            return cls()
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            log.warning("Konnektor retsepti buzuq JSON")
            return cls()

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def is_usable(self) -> bool:
        """Qidiruv uchun yetarli ma'lumot bormi?

        Natija qatori va undagi mehmonxona nomi bo'lmasa hech narsa
        o'qib bo'lmaydi — bunday retsept foydasiz.
        """
        return bool(self.row and self.row_fields.get("hotel_name"))


# --------------------------------------------------------------------------
# Konnektor
# --------------------------------------------------------------------------
class PlaywrightConnector(OperatorConnector):
    """Umumiy brauzer konnektori.

    `page` — Playwright `Page` obyekti, lekin bu modul uni faqat bir necha
    metod orqali ishlatadi (`goto`, `fill`, `click`, `content`,
    `query_selector_all`). Shu tufayli testlarda soxta obyekt bilan
    sinash mumkin va brauzer o'rnatish shart emas.
    """

    engine = OperatorEngine.CUSTOM
    needs_browser = True

    def __init__(self, recipe: Optional[SearchRecipe] = None) -> None:
        self.recipe = recipe or SearchRecipe()

    # ---- Login ----------------------------------------------------------
    async def login(self, ctx: ConnectorContext) -> ConnectorStatus:
        """Kabinetga kiradi. Sessiya bo'lsa o'tkazib yuboradi."""
        page = ctx.page
        if page is None:
            return ConnectorStatus.ERROR

        # Saqlangan sessiya bor — login formasi umuman ochilmaydi.
        if ctx.storage_state:
            return ConnectorStatus.OK

        if not (ctx.login and ctx.password and ctx.login_url):
            return ConnectorStatus.AUTH_FAILED

        await page.goto(ctx.login_url)

        password_field = await _first_match(page, PASSWORD_SELECTORS)
        if password_field is None:
            # Parol maydoni yo'q — ehtimol allaqachon kirilgan.
            return ConnectorStatus.OK

        login_field = await _first_match(page, LOGIN_SELECTORS)
        if login_field is None:
            return ConnectorStatus.AUTH_FAILED

        await login_field.fill(ctx.login)
        await password_field.fill(ctx.password)

        submit = await _first_match(page, SUBMIT_SELECTORS)
        if submit is not None:
            await submit.click()
        else:
            await password_field.press("Enter")

        return await self._check_login_result(page)

    async def _check_login_result(self, page: Any) -> ConnectorStatus:
        """Login natijasini sahifa mazmunidan aniqlaydi."""
        try:
            content = (await page.content() or "").lower()
        except Exception:  # noqa: BLE001
            return ConnectorStatus.OK

        # Captcha avval tekshiriladi: captcha sahifasida "xato" so'zi ham
        # bo'lishi mumkin va u AUTH_FAILED deb noto'g'ri belgilanardi —
        # agent esa parolini beso'naqay qayta terardi.
        if any(marker in content for marker in CAPTCHA_MARKERS):
            return ConnectorStatus.CAPTCHA
        if any(marker in content for marker in AUTH_FAIL_MARKERS):
            return ConnectorStatus.AUTH_FAILED
        return ConnectorStatus.OK

    # ---- Qidiruv --------------------------------------------------------
    async def search(self, ctx: ConnectorContext) -> ConnectorResult:
        if ctx.page is None:
            return ConnectorResult.failure(
                ConnectorStatus.ERROR, "Brauzer sahifasi berilmagan"
            )
        if not self.recipe.is_usable:
            return ConnectorResult.failure(
                ConnectorStatus.UNSUPPORTED,
                "Bu operator uchun konnektor retsepti to'ldirilmagan",
            )

        status = await self.login(ctx)
        if status is not ConnectorStatus.OK:
            return ConnectorResult.failure(status, f"Kirish muvaffaqiyatsiz: {status}")

        page = ctx.page
        if self.recipe.search_url:
            await page.goto(self.recipe.search_url)

        await self._fill_form(page, ctx)

        if self.recipe.submit:
            element = await _first_match(page, (self.recipe.submit,))
            if element is not None:
                await element.click()

        if self.recipe.wait_for:
            try:
                await page.wait_for_selector(
                    self.recipe.wait_for, timeout=self.recipe.timeout_ms
                )
            except Exception:  # noqa: BLE001 — natija chiqmadi, xato emas
                return ConnectorResult.ok([])

        offers = await self._read_rows(page)
        return ConnectorResult.ok(offers, meta={"rows": len(offers)})

    async def _fill_form(self, page: Any, ctx: ConnectorContext) -> None:
        """Qidiruv formasini so'rov bo'yicha to'ldiradi."""
        values = _query_values(ctx)
        for name, selector in self.recipe.fields.items():
            value = values.get(name)
            if value in (None, ""):
                continue
            # Ochiladigan ro'yxat bo'lsa saytdagi kodga o'giriladi
            # ("AI" -> "3"): har saytda o'z kodlari bor.
            mapping = self.recipe.field_values.get(name)
            if mapping:
                value = mapping.get(str(value), str(value))
            element = await _first_match(page, (selector,))
            if element is None:
                continue
            try:
                await element.fill(str(value))
            except Exception:  # noqa: BLE001 — select bo'lishi mumkin
                try:
                    await element.select_option(str(value))
                except Exception:  # noqa: BLE001
                    log.debug("Maydon to'ldirilmadi: %s", name)

    async def _read_rows(self, page: Any) -> list[RawOffer]:
        """Natija qatorlarini xom takliflarga o'giradi."""
        try:
            rows = await page.query_selector_all(self.recipe.row)
        except Exception:  # noqa: BLE001
            return []

        offers: list[RawOffer] = []
        for row in rows:
            offer = await self._row_to_offer(row)
            if offer is not None:
                offers.append(offer)
        return offers

    async def _row_to_offer(self, row: Any) -> Optional[RawOffer]:
        raw: dict[str, str] = {}
        for name, selector in self.recipe.row_fields.items():
            raw[name] = (await _text_of(row, selector)) or ""

        hotel = (raw.get("hotel_name") or "").strip()
        if not hotel:
            return None

        price_gross, currency = parse_price(raw.get("price_gross"))
        price_net, _ = parse_price(raw.get("price_net"))
        if price_gross is None and price_net is None:
            return None

        combined = " ".join(raw.values())
        return RawOffer(
            hotel_name=hotel[:300],
            price_gross=price_gross,
            price_net=price_net,
            currency=currency,
            board=(match_board(raw.get("board", "")) or match_board(combined)),
            star=(match_star(raw.get("star", "")) or match_star(combined)),
            room=(raw.get("room") or "").strip()[:120] or None,
            city=(raw.get("city") or "").strip()[:120] or None,
            nights=_int_or_none(raw.get("nights")),
            deep_link=(raw.get("deep_link") or "").strip() or None,
            raw=raw,
        )


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------
async def _first_match(page: Any, selectors: tuple[str, ...]) -> Optional[Any]:
    """Ro'yxatdagi birinchi mos elementni qaytaradi."""
    for selector in selectors:
        if not selector:
            continue
        try:
            element = await page.query_selector(selector)
        except Exception:  # noqa: BLE001 — noto'g'ri selektor
            continue
        if element is not None:
            return element
    return None


async def _text_of(row: Any, selector: str) -> Optional[str]:
    """Qator ichidagi elementning matni."""
    if not selector:
        return None
    try:
        element = await row.query_selector(selector)
        if element is None:
            return None
        return await element.inner_text()
    except Exception:  # noqa: BLE001
        return None


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"\d{1,2}", value)
    return int(match.group()) if match else None


def _query_values(ctx: ConnectorContext) -> dict[str, Any]:
    """So'rovni forma maydonlariga mos nomlarga o'giradi."""
    query = ctx.query
    city = next((d.name_uz for d in query.destinations if not d.is_country), None)
    country = next((d.name_uz for d in query.destinations if d.is_country), None)
    return {
        "destination": city or country,
        "city": city,
        "country": country,
        "date_from": query.date_from,
        "nights": query.nights,
        "adults": query.adults or 2,
        "children": query.children or 0,
        "star": query.star,
        "board": str(query.board) if query.board else None,
        "price_min": query.budget_min,
        "price_max": query.budget_max,
    }


def build_connector(operator_config: str | dict | None) -> PlaywrightConnector:
    """Operatorning `connector_config` idan konnektor yasaydi."""
    return PlaywrightConnector(SearchRecipe.from_json(operator_config))


# Retseptsiz ham ro'yxatda tursin: login qismi ishlaydi va "konnektor bor"
# belgisi UI da to'g'ri ko'rinadi.
registry.register(PlaywrightConnector())
