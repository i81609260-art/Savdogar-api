"""Obuna to'lovi sanasi va eslatma hisob-kitobi.

To'lov davri oylik va kompaniyaning `created_at` kuniga bog'langan. Har oy
o'sha kunda to'lov kerak. To'lov qilinganda `paid_until` bir oyga suriladi va
eslatma keyingi oygacha to'xtaydi. Maxsus (sotilmaydigan) rejalar — masalan
OpenTour'ning "cheksiz"i — to'lovdan ozod.
"""

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

# Necha kun oldin ogohlantirish boshlanadi.
WARN_WITHIN_DAYS = 3


def _as_date(value: Optional[datetime | date]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def add_months(d: date, n: int) -> date:
    """Sanaga n oy qo'shadi; oy kuni kelgusi oyda bo'lmasa oxirgi kunga qisadi."""
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last_day = monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def compute_billing(
    company: Any, plan: Dict[str, Any], today: Optional[date] = None
) -> Dict[str, Any]:
    """Kompaniya uchun to'lov holatini qaytaradi.

    status: exempt | ok | due_soon | due_today | overdue
    """
    today = today or datetime.now(timezone.utc).date()

    # Maxsus reja (cheksiz) yoki narxsiz — to'lov talab qilinmaydi.
    if not plan.get("purchasable", True) or not plan.get("price"):
        return {"status": "exempt", "next_payment_date": None, "days_left": None}

    created = _as_date(getattr(company, "created_at", None)) or today
    paid_until = _as_date(getattr(company, "paid_until", None))

    # Keyingi to'lov sanasi: to'langan bo'lsa — paid_until, aks holda
    # created_at dan bir oy keyin (birinchi oy hisobda).
    next_due = paid_until if paid_until else add_months(created, 1)

    days_left = (next_due - today).days
    if days_left < 0:
        status = "overdue"
    elif days_left == 0:
        status = "due_today"
    elif days_left <= WARN_WITHIN_DAYS:
        status = "due_soon"
    else:
        status = "ok"

    return {
        "status": status,
        "next_payment_date": next_due.isoformat(),
        "days_left": days_left,
        "price": plan.get("price"),
        "price_usd": plan.get("price_usd"),
    }


def advance_paid_until(company: Any, today: Optional[date] = None) -> datetime:
    """To'lovdan keyin `paid_until`ni bir oyga suradi va qaytaradi.

    Muddat o'tib ketgan bo'lsa bugundan, aks holda joriy sanadan hisoblanadi —
    shunda erta to'lagan mijoz kunlarini yo'qotmaydi.
    """
    today = today or datetime.now(timezone.utc).date()
    current = _as_date(getattr(company, "paid_until", None))
    if current is None or current < today:
        base = today
    else:
        base = current
    new_until = add_months(base, 1)
    return datetime(new_until.year, new_until.month, new_until.day, tzinfo=timezone.utc)
