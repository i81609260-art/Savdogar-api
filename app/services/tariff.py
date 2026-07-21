"""Subscription plan (tariff) definitions and limit helpers.

Plans are defined in code (not the DB) so limits/features stay in one place.
A company stores only its plan *key* in `companies.tariff`; the limits are
resolved from here on every request, so a plan switch takes effect immediately.

NOTE: the keys ("boshlangich" / "biznes" / "premium") are frozen — companies
already store them. Only the display `name` changed to Start / Komfort / Biznes.
"""

from typing import Any, Dict

DEFAULT_TARIFF = "boshlangich"

# Ordered cheapest → most capable. `max_*` of None means unlimited.
# `site_level`: "optional" (opt-in) | "standard" | "professional".
TARIFFS: Dict[str, Dict[str, Any]] = {
    # Maxsus reja — OpenTour kabi flagman kompaniyalar uchun: tekin, cheksiz,
    # hamma imkoniyat ochiq. Sotib olib bo'lmaydi (`purchasable=False`), shuning
    # uchun oddiy firmalarga tarif ro'yxatida ko'rinmaydi.
    "cheksiz": {
        "key": "cheksiz",
        "name": "Cheksiz",
        # Ko'rsatiladigan narx; sotilmaydi va to'lovdan ozod (purchasable=False),
        # shuning uchun bu faqat panelda ko'rinadi, hech qachon undirilmaydi.
        "price": 200000,
        "price_usd": None,
        "order": 0,
        "purchasable": False,
        "audience": "Maxsus / hamkor kompaniya",
        "promise": "Hamma imkoniyat ochiq — cheksiz",
        "tagline": "Maxsus cheksiz reja",
        "max_tours": None,
        "max_branches": None,
        "site_level": "professional",
        "features": {
            "crm": True,
            "bookings": True,
            "unlimited_customers": True,
            "telegram_bot": True,
            "reports": True,
            "website": True,
            "ai_chat": True,
            "white_label": True,
            "api_access": True,
            "priority_support": True,
        },
    },
    "boshlangich": {
        "key": "boshlangich",
        "name": "Start",
        "price": 199990,
        # Stripe (xalqaro) uchun oylik dollar narxi. MB kursi bo'yicha
        # so'm narxidan hisoblangan (1 USD ≈ 11 960 so'm) — kurs o'zgarsa
        # shu yerni yangilang.
        "price_usd": 16.72,
        "order": 1,
        "audience": "Yangi yoki kichik tur firma",
        "promise": "Lead va buyurtmani yo'qotmang",
        "tagline": "Yangi yoki kichik tur firma",
        "max_tours": None,
        "max_branches": 1,
        "site_level": "optional",
        "site_addon_price": 20000,
        "features": {
            "crm": True,
            "bookings": True,
            "unlimited_customers": True,
            "telegram_bot": True,
            "reports": True,          # basic analytics
            "website": False,         # opt-in landing (+20 000)
            "ai_chat": False,
            "white_label": False,
            "api_access": False,
            "priority_support": False,
        },
    },
    "biznes": {
        "key": "biznes",
        "name": "Komfort",
        "price": 499990,
        "price_usd": 41.80,
        "order": 2,
        "audience": "O'sayotgan kompaniya",
        "promise": "Sotuvni tizimlashtiring, filiallarni ushlang",
        "tagline": "O'sayotgan kompaniya",
        "max_tours": 300,
        "max_branches": 3,
        "site_level": "standard",
        "features": {
            "crm": True,
            "bookings": True,
            "unlimited_customers": True,
            "telegram_bot": True,
            "reports": True,
            "website": True,
            "ai_chat": True,
            "white_label": False,
            "api_access": False,
            "priority_support": False,
        },
    },
    "premium": {
        "key": "premium",
        "name": "Biznes",
        "price": 999990,
        "price_usd": 83.61,
        "order": 3,
        "audience": "Katta yoki ko'p filialli firma",
        "promise": "Avtomatizatsiya, nazorat, o'sish",
        "tagline": "Katta yoki ko'p filialli firma",
        "max_tours": None,       # unlimited
        "max_branches": None,    # unlimited
        "site_level": "professional",
        "features": {
            "crm": True,
            "bookings": True,
            "unlimited_customers": True,
            "telegram_bot": True,
            "reports": True,
            "website": True,
            "ai_chat": True,
            "white_label": True,
            "api_access": True,
            "priority_support": True,
        },
    },
}


def get_tariff(key: str | None) -> Dict[str, Any]:
    """Resolve a plan by key, falling back to the default plan."""
    return TARIFFS.get(key or "", TARIFFS[DEFAULT_TARIFF])


def tariff_list() -> list[Dict[str, Any]]:
    """Sotib olish mumkin bo'lgan rejalar, arzonidan boshlab.

    Maxsus rejalar (`purchasable=False`, masalan "cheksiz") ro'yxatga kirmaydi.
    """
    return sorted(
        (t for t in TARIFFS.values() if t.get("purchasable", True)),
        key=lambda t: t["order"],
    )


def within_tour_limit(tariff_key: str | None, current_tour_count: int) -> bool:
    """True if the company can still create another tour under its plan."""
    limit = get_tariff(tariff_key)["max_tours"]
    return limit is None or current_tour_count < limit


def within_branch_limit(tariff_key: str | None, current_branch_count: int) -> bool:
    """True if the company can still create another branch under its plan."""
    limit = get_tariff(tariff_key)["max_branches"]
    return limit is None or current_branch_count < limit
