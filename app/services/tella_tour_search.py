"""Tella — tur qidiruv so'rovini erkin matndan ajratib olish.

Tashqi API yo'q, kalit kerak emas. `ml_assistant.py` dagi yondashuvning
davomi: qoidalar + regex + ma'lumotnoma. Yo'nalish/ovqat/toifa/yulduz
`tour_taxonomy` dan keladi, bu modul ustiga **sonli** slotlarni qo'shadi —
kecha, kishi, byudjet, sana.

Nega LLM emas
-------------
Agent kuniga o'nlab qidiruv qiladi. Har biriga tashqi model chaqirilsa bu
ham pul, ham kechikish. Bu yerdagi ish esa aslida oddiy: matndan sanoqli
maydonni ajratish. Qoida bilan yechiladigan narsaga model shart emas.

Model kerak bo'lgan joy — **intent aniqlash** ("bu qidiruvmi yoki hisobot
so'rovimi"), va uni Tella allaqachon o'zining TF-IDF + LogisticRegression
klassifikatori bilan qiladi. Bu modul o'sha klassifikatorga qo'shiladigan
o'quv misollarini ham beradi (`SEARCH_TRAINING`), ya'ni Tella ishlatilgani
sari qidiruv so'rovlarini ham yaxshiroq tanib boradi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.tour_taxonomy import (
    Board,
    Destination,
    TourCategory,
    match_all,
    normalize,
)

# --------------------------------------------------------------------------
# Tella intent klassifikatoriga qo'shiladigan o'quv misollari
# --------------------------------------------------------------------------
SEARCH_INTENT = "search_tours"

SEARCH_TRAINING: list[tuple[str, str]] = [
    ("tur qidir", SEARCH_INTENT),
    ("tur paket qidir", SEARCH_INTENT),
    ("operatorlardan qidir", SEARCH_INTENT),
    ("hamma operatordan qidir", SEARCH_INTENT),
    ("eng arzon turni top", SEARCH_INTENT),
    ("arzon paket topib ber", SEARCH_INTENT),
    ("narx solishtir", SEARCH_INTENT),
    ("narxlarni solishtir", SEARCH_INTENT),
    ("antalyaga tur bormi", SEARCH_INTENT),
    ("turkiyaga paket qidir", SEARCH_INTENT),
    ("dubayga tur top", SEARCH_INTENT),
    ("umraga paket qidir", SEARCH_INTENT),
    ("misrga arzon tur", SEARCH_INTENT),
    ("mijozga tur qidiryapman", SEARCH_INTENT),
    ("qaysi operatorda arzon", SEARCH_INTENT),
    ("nayti tur", SEARCH_INTENT),
    ("podbor tur", SEARCH_INTENT),
    ("najdi tur", SEARCH_INTENT),
    ("podobrat tur", SEARCH_INTENT),
    ("sravni tseni", SEARCH_INTENT),
]

# `_KEYWORDS` uchun — ishonch past bo'lganda tayanch bo'ladi.
SEARCH_KEYWORDS: tuple[str, ...] = (
    "qidir", "topib ber", "solishtir", "eng arzon", "podbor", "najdi",
)


# --------------------------------------------------------------------------
# Natija
# --------------------------------------------------------------------------
@dataclass
class TourSearchQuery:
    """Operatorlarga yuboriladigan normallashtirilgan qidiruv so'rovi."""

    destinations: list[Destination] = field(default_factory=list)
    category: Optional[TourCategory] = None
    board: Optional[Board] = None
    star: Optional[str] = None

    nights: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None

    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    currency: Optional[str] = None

    date_from: Optional[str] = None   # "YYYY-MM-DD" yoki "YYYY-MM"
    month: Optional[int] = None

    # Matndan olinmagan, mantiqan xulosa qilingan maydonlar.
    inferred: set[str] = field(default_factory=set)
    raw_text: str = ""

    @property
    def country_codes(self) -> list[str]:
        seen, out = set(), []
        for d in self.destinations:
            if d.country_code not in seen:
                seen.add(d.country_code)
                out.append(d.country_code)
        return out

    @property
    def pax(self) -> int:
        """Jami mehmon. Ko'rsatilmagan bo'lsa 2 — eng keng tarqalgan holat."""
        return (self.adults or 2) + (self.children or 0)

    def to_dict(self) -> dict:
        return {
            "destinations": [d.code for d in self.destinations],
            "countries": self.country_codes,
            "category": self.category.value if self.category else None,
            "board": self.board.value if self.board else None,
            "star": self.star,
            "nights": self.nights,
            "adults": self.adults,
            "children": self.children,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "currency": self.currency,
            "date_from": self.date_from,
            "month": self.month,
            "inferred": sorted(self.inferred),
            # Suhbat davom etganda kerak: agent yetishmagan shartni aytsa,
            # yangi xabar shu matn ustiga qo'shiladi va avval aytilgan
            # shartlar (kecha, kishi, byudjet) yo'qolmaydi.
            "raw_text": self.raw_text,
        }


# --------------------------------------------------------------------------
# Sonli slotlar
# --------------------------------------------------------------------------
_MONTHS: dict[str, int] = {
    "yanvar": 1, "январ": 1, "january": 1,
    "fevral": 2, "феврал": 2, "february": 2,
    "mart": 3, "март": 3, "march": 3,
    "aprel": 4, "апрел": 4, "april": 4,
    "may": 5, "мая": 5, "маи": 5,
    "iyun": 6, "июн": 6, "june": 6,
    "iyul": 7, "июл": 7, "july": 7,
    "avgust": 8, "август": 8, "august": 8,
    "sentabr": 9, "sentyabr": 9, "сентябр": 9, "september": 9,
    "oktabr": 10, "oktyabr": 10, "октябр": 10, "october": 10,
    "noyabr": 11, "ноябр": 11, "november": 11,
    "dekabr": 12, "декабр": 12, "december": 12,
}

# Katta sonlar so'm bilan yoziladi: "5 mln", "800 ming".
_MULTIPLIERS: tuple[tuple[str, int], ...] = (
    ("mln", 1_000_000), ("million", 1_000_000), ("млн", 1_000_000),
    ("ming", 1_000), ("тыс", 1_000), ("тысяч", 1_000), ("k", 1_000),
)

_NIGHTS_RE = re.compile(
    r"(\d{1,2})\s*(?:kecha|kun(?:lik)?|nochey|noch|ночей|ночи|ноч|дней|дня|день|nights?|days?)"
)
_ADULTS_RE = re.compile(
    r"(\d{1,2})\s*(?:katta|kattalar|nafar\s*katta|kishi|odam|adults?|взрослы[хй]|чел)"
)
_CHILDREN_RE = re.compile(
    r"(\d{1,2})\s*(?:bola|bolalar|child(?:ren)?|kids?|ребен|детей|реб)"
)


def _apply_multiplier(number: float, tail: str) -> float:
    """"5 mln" -> 5 000 000. Ko'paytuvchi sondan keyin keladi."""
    head = tail.lstrip()
    for word, factor in _MULTIPLIERS:
        if head.startswith(word):
            return number * factor
    return number


def _num_at(text: str, match: re.Match) -> float:
    """Moslikdagi sonni ko'paytuvchisi bilan qaytaradi."""
    return _apply_multiplier(float(match.group(1)), text[match.end(1):match.end(1) + 12])


def parse_nights(text: str) -> Optional[int]:
    """Necha kecha. "7 kecha", "10 kunlik", "на 7 ночей"."""
    m = _NIGHTS_RE.search(normalize(text))
    if not m:
        return None
    value = int(m.group(1))
    return value if 1 <= value <= 60 else None


def parse_pax(text: str) -> tuple[Optional[int], Optional[int]]:
    """(kattalar, bolalar). "2 katta 1 bola", "2 kishi", "2 взрослых"."""
    h = normalize(text)
    children = None
    mc = _CHILDREN_RE.search(h)
    if mc:
        value = int(mc.group(1))
        children = value if 0 <= value <= 10 else None
        # Bolalar qismini olib tashlaymiz — "1 bola" ni "1 kishi" deb
        # o'qib yubormaslik uchun.
        h = h[: mc.start()] + " " + h[mc.end():]

    adults = None
    ma = _ADULTS_RE.search(h)
    if ma:
        value = int(ma.group(1))
        adults = value if 1 <= value <= 20 else None
    return adults, children


def parse_budget(text: str) -> tuple[Optional[float], Optional[float]]:
    """(eng kam, eng ko'p). Oraliq, "gacha", "dan" va yalang'och sonni qo'llab.

    Namunalar:
        "500 dollargacha"        -> (None, 500)
        "300 dan 800 gacha"      -> (300, 800)
        "до 800"                 -> (None, 800)
        "от 300"                 -> (300, None)
        "byudjet 5 mln so'm"     -> (None, 5 000 000)
    """
    h = normalize(text)

    # 1) Oraliq: "300 dan 800 gacha", "от 300 до 800", "300-800"
    rng = re.search(
        r"(\d[\d\s]*)\s*(?:mln|million|млн|ming|тыс|k)?\s*"
        r"(?:dan|до|do|-|–)\s*"
        r"(\d[\d\s]*)\s*(?:mln|million|млн|ming|тыс|k)?\s*(?:gacha|до)?",
        h,
    )
    if rng:
        lo = _apply_multiplier(float(rng.group(1).replace(" ", "")), h[rng.end(1):rng.end(1) + 12])
        hi = _apply_multiplier(float(rng.group(2).replace(" ", "")), h[rng.end(2):rng.end(2) + 12])
        if lo <= hi:
            return lo, hi

    # 2) Yuqori chegara: "500 gacha", "до 500", "500 dollargacha"
    upper = re.search(r"(\d[\d\s]*)\s*(?:mln|million|млн|ming|тыс|k)?[a-zа-я']*\s*gacha", h)
    if not upper:
        upper = re.search(r"(?:до|maksimum|max)\s*(\d[\d\s]*)", h)
    if upper:
        value = _apply_multiplier(
            float(upper.group(1).replace(" ", "")), h[upper.end(1):upper.end(1) + 12]
        )
        return None, value

    # 3) Quyi chegara: "300 dan", "от 300"
    lower = re.search(r"(?:от|minimum|min)\s*(\d[\d\s]*)", h)
    if lower:
        value = _apply_multiplier(
            float(lower.group(1).replace(" ", "")), h[lower.end(1):lower.end(1) + 12]
        )
        return value, None

    # 4) Valyuta yonidagi yalang'och son: "byudjet 500 dollar", "$500"
    near = re.search(
        r"(?:\$|byudjet|budjet|бюджет)\s*(\d[\d\s]*)|"
        r"(\d[\d\s]*)\s*(?:mln|million|млн|ming|тыс)?\s*"
        r"(?:dollar|доллар|so'm|som|sum|сум|евро|euro|eur|usd|uzs)",
        h,
    )
    if near:
        raw = near.group(1) or near.group(2)
        end = near.end(1) if near.group(1) else near.end(2)
        return None, _apply_multiplier(float(raw.replace(" ", "")), h[end:end + 12])

    return None, None


def parse_month(text: str) -> Optional[int]:
    """Oy nomi. "sentabrda", "в сентябре"."""
    h = normalize(text)
    for name, number in _MONTHS.items():
        if re.search(r"(?<!\w)" + re.escape(name), h):
            return number
    return None


def parse_date_from(text: str) -> Optional[str]:
    """Aniq sana: "01.09.2026", "2026-09-01", "1 sentabr".

    DIQQAT: raqamli sana **xom matndan** o'qiladi. `normalize()` tinish
    belgilarini bo'shliqqa aylantiradi, ya'ni "01.09.2026" -> "01 09 2026"
    bo'lib ajratgich yo'qoladi. Faqat oy nomlari normallashtirilgan matnda
    qidiriladi (u yerda kirill/lotin farqi tekislanadi).
    """
    raw = text or ""

    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # "1 sentabr" / "15 сентября" — yilsiz, chaqiruvchi to'ldiradi.
    h = normalize(raw)
    for name, number in _MONTHS.items():
        m = re.search(r"(\d{1,2})\s*[- ]?\s*" + re.escape(name), h)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                return f"{number:02d}-{day:02d}"
    return None


# --------------------------------------------------------------------------
# Asosiy kirish nuqtasi
# --------------------------------------------------------------------------
def extract_query(text: str) -> TourSearchQuery:
    """Erkin matndan to'liq qidiruv so'rovini yig'adi."""
    taxonomy = match_all(text or "")
    adults, children = parse_pax(text or "")
    budget_min, budget_max = parse_budget(text or "")

    query = TourSearchQuery(
        destinations=taxonomy.destinations,
        category=taxonomy.category,
        board=taxonomy.board,
        star=taxonomy.star,
        nights=parse_nights(text or ""),
        adults=adults,
        children=children,
        budget_min=budget_min,
        budget_max=budget_max,
        currency=taxonomy.currency,
        date_from=parse_date_from(text or ""),
        month=parse_month(text or ""),
        inferred=set(taxonomy.inferred),
        raw_text=(text or "").strip(),
    )

    # Byudjet bor, valyuta yo'q — kattaligidan xulosa qilamiz.
    #
    # Operator prays-listlarida narx USD'da, mijoz esa so'mda o'ylaydi
    # ("15 mln"). Doim USD deb olinganda "15 mln" 178 mlrd so'mga
    # aylanardi va byudjet filtri jimgina ishlamay qolardi.
    #
    # Chegara — 100 000: paket tur uchun 100 000 dollar ham,
    # 100 000 so'm ham (~8$) real byudjet emas, shuning uchun oraliqda
    # chalkashlik yo'q.
    if (query.budget_max or query.budget_min) and not query.currency:
        eng_katta = max(query.budget_max or 0, query.budget_min or 0)
        query.currency = "UZS" if eng_katta >= 100_000 else "USD"
        query.inferred.add("currency")

    return query


# Qidiruvni boshlash uchun eng kam kerak bo'lgan maydonlar.
REQUIRED_SLOTS: tuple[str, ...] = ("destinations",)

SLOT_QUESTIONS: dict[str, str] = {
    "destinations": "Qaysi yo'nalish? (masalan: Antalya, Dubay, Umra)",
    "nights": "Necha kecha?",
    "adults": "Necha kishi?",
    "date_from": "Qachon? (sana yoki oy)",
}


def missing_slots(query: TourSearchQuery) -> list[str]:
    """Qidiruvni boshlash uchun yetishmayotgan majburiy maydonlar."""
    return [s for s in REQUIRED_SLOTS if not getattr(query, s, None)]


def next_question(query: TourSearchQuery) -> Optional[str]:
    """Keyingi so'raladigan savol. Hammasi bo'lsa `None`."""
    for slot in missing_slots(query):
        return SLOT_QUESTIONS.get(slot)
    return None


def summarize(query: TourSearchQuery) -> str:
    """Agent tasdiqlashi uchun o'zbekcha qisqacha bayon."""
    parts: list[str] = []

    if query.destinations:
        names = [d.name_uz for d in query.destinations if not d.is_country]
        if not names:
            names = [d.name_uz for d in query.destinations]
        parts.append(", ".join(names[:3]))
    if query.category:
        from app.services.tour_taxonomy import CATEGORY_LABELS

        parts.append(CATEGORY_LABELS[query.category])
    if query.star:
        parts.append(f"{query.star}*")
    if query.board:
        from app.services.tour_taxonomy import BOARD_LABELS

        parts.append(BOARD_LABELS[query.board])
    if query.nights:
        parts.append(f"{query.nights} kecha")

    if query.adults or query.children:
        pax = f"{query.adults or 0} katta"
        if query.children:
            pax += f" + {query.children} bola"
        parts.append(pax)

    if query.budget_max and query.budget_min:
        parts.append(f"{query.budget_min:,.0f}-{query.budget_max:,.0f} {query.currency or ''}".strip())
    elif query.budget_max:
        parts.append(f"{query.budget_max:,.0f} {query.currency or ''} gacha".strip())
    elif query.budget_min:
        parts.append(f"{query.budget_min:,.0f} {query.currency or ''} dan".strip())

    if query.date_from:
        parts.append(query.date_from)
    elif query.month:
        parts.append(f"{query.month}-oy")

    return " · ".join(parts) if parts else "shartlar ko'rsatilmagan"
