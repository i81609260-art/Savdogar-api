"""Subscription plan (tariff) definitions and limit helpers.

Plans are defined in code (not the DB) so limits/features stay in one place.
A company stores only its plan *key* in `companies.tariff`; the limits are
resolved from here on every request, so a plan switch takes effect immediately.
"""

from typing import Any, Dict

DEFAULT_TARIFF = "boshlangich"

# Ordered cheapest → most capable. `max_*` of None means unlimited.
# `site_level`: "optional" (paid add-on) | "standard" | "professional".
TARIFFS: Dict[str, Dict[str, Any]] = {
    "boshlangich": {
        "key": "boshlangich",
        "name": "Boshlang'ich",
        "price": 199990,
        "order": 1,
        "tagline": "Kichik agentliklar uchun",
        "max_tours": 50,
        "max_branches": 1,
        "site_level": "optional",
        "site_addon_price": 20000,
        "features": {
            "crm": True,
            "bookings": True,
            "unlimited_customers": True,
            "telegram_bot": True,
            "reports": False,
            "website": False,          # optional add-on (+20 000)
            "ai_chat": False,
            "white_label": False,
            "api_access": False,
            "priority_support": False,
        },
    },
    "biznes": {
        "key": "biznes",
        "name": "Biznes",
        "price": 499990,
        "order": 2,
        "tagline": "O'sayotgan firmalar uchun",
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
        "name": "Premium",
        "price": 999990,
        "order": 3,
        "tagline": "Cheksiz — yetakchi firmalar uchun",
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
    """All plans, cheapest first."""
    return sorted(TARIFFS.values(), key=lambda t: t["order"])


def within_tour_limit(tariff_key: str | None, current_tour_count: int) -> bool:
    """True if the company can still create another tour under its plan."""
    limit = get_tariff(tariff_key)["max_tours"]
    return limit is None or current_tour_count < limit
