"""Har bir tur firma admini uchun oʻzimizning ML yordamchi (LLM ishlatmaydi).

Toʻliq 0 dan qurilgan NLU + dialog tizimi:
  1) Intent klassifikatsiyasi — TF-IDF (char n-gram) + LogisticRegression,
     qolda yozilgan ozbekcha dataset ustida oʻqitilgan (scikit-learn).
  2) Slot ajratish — son, narx (mln/ming), kun, joy, sana uchun qoidalar/regex.
  3) Dialog menejeri — yetishmayotgan maydonni ketma-ket soraydi, yozuvchi
     amaldan oldin tasdiq soraydi.
  4) Javob — shablonli ozbekcha matn (tutuq belgisisiz) + xisobot tahlili.

Tashqi API yoʻq, kalit kerak emas — hammasi shu serverda ishlaydi. Holat
(pending) mijoz bilan har soʻrovda almashiladi, shuning uchun server holatsiz.
"""

import logging
import re
import time
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.models.assistant_example import AssistantExample
from app.models.booking import Booking, BookingStatus
from app.models.company import Company
from app.models.tour import Tour
from app.models.user import User
from app.services.reports_service import ReportsService
from app.services.tariff import DEFAULT_TARIFF, get_tariff, within_tour_limit

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 1) Intent klassifikatori — qolda yozilgan dataset
# --------------------------------------------------------------------------- #

INTENT_TRAINING: list[tuple[str, str]] = [
    # greeting
    ("salom", "greeting"), ("assalomu alaykum", "greeting"), ("assalom", "greeting"),
    ("salom yordamchi", "greeting"), ("hayrli kun", "greeting"), ("privet", "greeting"),
    # help
    ("nima qila olasan", "help"), ("yordam", "help"), ("qanday ishlaysan", "help"),
    ("nima qilish mumkin", "help"), ("imkoniyatlaring", "help"), ("komandalar", "help"),
    # report / analytics
    ("xisobot", "report"), ("hisobot ber", "report"), ("statistika", "report"),
    ("umumiy korsatkich", "report"), ("qanday ketyapti", "report"),
    ("daromad qancha", "report"), ("bu oy qancha daromad", "report"),
    ("nechta bron boldi", "report"), ("bronlar qancha", "report"),
    ("necha kishi tashrif buyurdi", "report"), ("tashriflar soni", "report"),
    ("faol foydalanuvchi", "report"), ("natijalar", "report"),
    ("yetishmovchilik", "report"), ("qanaqa muammolar bor", "report"),
    ("umumiy hisobot ber", "report"), ("savdo qanday", "report"),
    # count_tours
    ("nechta tur bor", "count_tours"), ("turlar soni", "count_tours"),
    ("qancha tur paket bor", "count_tours"), ("tur soni qancha", "count_tours"),
    ("nechta tur paketim bor", "count_tours"),
    # list_tours
    ("turlar royxati", "list_tours"), ("turlarimni korsat", "list_tours"),
    ("qanday turlar bor", "list_tours"), ("tur paketlar royxati", "list_tours"),
    ("mavjud turlar", "list_tours"), ("turlarim", "list_tours"),
    # count_customers
    ("nechta mijoz bor", "count_customers"), ("mijozlar soni", "count_customers"),
    ("qancha mijozim bor", "count_customers"), ("mijoz soni qancha", "count_customers"),
    # recent_bookings
    ("oxirgi bronlar", "recent_bookings"), ("songgi bronlar", "recent_bookings"),
    ("kim bron qildi", "recent_bookings"), ("bronlar royxati", "recent_bookings"),
    ("yangi bronlar", "recent_bookings"),
    # get_plan
    ("tarifim qaysi", "get_plan"), ("qaysi tarifdaman", "get_plan"),
    ("tarif holati", "get_plan"), ("limitim qancha", "get_plan"),
    ("obuna holati", "get_plan"),
    # create_tour
    ("yangi tur qosh", "create_tour"), ("tur qoshmoqchiman", "create_tour"),
    ("tur paket qosh", "create_tour"), ("yangi tur paket yarat", "create_tour"),
    ("tur qoshish", "create_tour"), ("yangi yonalish qosh", "create_tour"),
    ("dubay turi qosh", "create_tour"), ("tur yarat", "create_tour"),
    # update_price
    ("narxni ozgartir", "update_price"), ("narx ozgartir", "update_price"),
    ("narxini yangila", "update_price"), ("tur narxini ozgartir", "update_price"),
    ("qimmatlashtir", "update_price"), ("arzonlashtir", "update_price"),
    ("narxni yangilash", "update_price"), ("yangi narx qoy", "update_price"),
    # set_active
    ("turni faollashtir", "set_active"), ("turni yoq", "set_active"),
    ("turni nofaol qil", "set_active"), ("turni yashir", "set_active"),
    ("turni faol qil", "set_active"), ("turni ochib qoy", "set_active"),
]

_CONF_THRESHOLD = 0.18  # past ishonchda -> unknown

# Kritik intentlar uchun kalit soʻz tayanchi (kichik dataset ishonchsizligiga qarshi).
_KEYWORDS: list[tuple[str, str]] = [
    ("qosh", "create_tour"), ("yarat", "create_tour"),
    ("narx", "update_price"),
    ("faollashtir", "set_active"), ("nofaol", "set_active"), ("yashir", "set_active"),
    ("xisobot", "report"), ("hisobot", "report"), ("daromad", "report"), ("statistika", "report"),
    ("royxat", "list_tours"),
    ("nechta tur", "count_tours"), ("tur soni", "count_tours"),
    ("mijoz", "count_customers"),
    ("bron", "recent_bookings"),
    ("tarif", "get_plan"),
]


# Oʻrgangan misollarni DB dan qayta yuklash oraligʻi (worker'lar orasida tarqalishi uchun).
_RELOAD_SECONDS = 20
# Faqat shu ishonchdan yuqori sorovlardan oʻrganamiz (xato mustahkamlanmasin).
_LEARN_CONF = 0.40


class _LearningStore:
    """Oʻz-oʻzini kuchaytiruvchi intent klassifikatori.

    Boshlangʻich dataset (INTENT_TRAINING) + DB dagi oʻrgangan misollar ustida
    oʻqiydi. Yangi (takrorlanmagan) ibora oʻrganilganda model qayta quriladi,
    shuning uchun ishlatilgani sari kuchayadi. Boshlangʻich dataset doim
    saqlanadi — model undan uzoqlashib ketmaydi (drift'ga qarshi langar).
    """

    def __init__(self) -> None:
        self.seed_norm = {_norm(t) for t, _ in INTENT_TRAINING}
        self.learned: list[tuple[str, str]] = []      # (norm_text, intent)
        self.learned_norm: set[str] = set()
        self.vec: Optional[TfidfVectorizer] = None
        self.clf: Optional[LogisticRegression] = None
        self.last_reload = 0.0
        self._build()

    def _build(self) -> None:
        data = [(_norm(t), l) for t, l in INTENT_TRAINING] + self.learned
        texts = [t for t, _ in data]
        labels = [l for _, l in data]
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        X = vec.fit_transform(texts)
        clf = LogisticRegression(max_iter=1000)
        clf.fit(X, labels)
        self.vec, self.clf = vec, clf

    def predict(self, text: str) -> tuple[str, float]:
        t = _norm(text)
        proba = self.clf.predict_proba(self.vec.transform([t]))[0]
        idx = int(proba.argmax())
        intent = self.clf.classes_[idx]
        conf = float(proba[idx])
        # Kalit soʻz tayanchi — ishonch past yoki aniq kalit boʻlsa ustuvor.
        for kw, kw_intent in _KEYWORDS:
            if kw in t:
                if conf < 0.5 or kw_intent in ("create_tour", "update_price", "set_active"):
                    return kw_intent, max(conf, 0.6)
        if conf < _CONF_THRESHOLD:
            return "unknown", conf
        return intent, conf

    async def ensure_fresh(self, db: AsyncSession) -> None:
        """Vaqti-vaqti bilan DB dan yangi misollarni yuklab, modelni yangilaydi."""
        now = time.monotonic()
        if self.clf is not None and (now - self.last_reload) < _RELOAD_SECONDS:
            return
        self.last_reload = now
        total = (await db.execute(select(func.count(AssistantExample.id)))).scalar() or 0
        if self.clf is not None and total == len(self.learned):
            return  # oʻzgarish yoʻq
        rows = (await db.execute(select(AssistantExample.text, AssistantExample.intent))).all()
        seen: set[str] = set()
        learned: list[tuple[str, str]] = []
        for text, intent in rows:
            nt = _norm(text)
            if nt in seen or nt in self.seed_norm:
                continue
            seen.add(nt)
            learned.append((nt, intent))
        self.learned = learned
        self.learned_norm = seen
        self._build()

    async def learn(self, db: AsyncSession, company_id: Optional[int], text: str, intent: str) -> None:
        """Yangi (matn -> intent) misolini saqlaydi va modelni qayta quradi.

        Faqat takrorlanmagan, real intentli ibora oʻrganiladi.
        """
        if not intent or intent in ("greeting", "help", "unknown"):
            return
        nt = _norm(text)
        if not nt or nt in self.seed_norm or nt in self.learned_norm:
            return
        db.add(AssistantExample(company_id=company_id, text=text[:500], intent=intent))
        await db.commit()
        self.learned.append((nt, intent))
        self.learned_norm.add(nt)
        self._build()


_STORE: Optional[_LearningStore] = None


def _store() -> _LearningStore:
    global _STORE
    if _STORE is None:
        _STORE = _LearningStore()
    return _STORE


def is_configured() -> bool:
    """ML yordamchi doim mavjud — tashqi kalit kerak emas."""
    return True


# --------------------------------------------------------------------------- #
# 2) Slot ajratish — qoidalar / regex
# --------------------------------------------------------------------------- #

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ʻ", "'").replace("’", "'")).strip()

_AFFIRM = {"ha", "xa", "ha ha", "mayli", "boladi", "ok", "okay", "hop", "xop",
           "tasdiqlayman", "tasdiq", "davom", "albatta", "roziman", "qosh", "qoshaver"}
_DENY = {"yoq", "yo", "kerakmas", "kerak emas", "bekor", "bekor qil", "xohlamayman",
         "kerakmagan", "yoq kerak emas"}


def is_affirm(text: str) -> bool:
    t = _norm(text)
    return t in _AFFIRM or any(t.startswith(a + " ") or t == a for a in _AFFIRM)


def is_deny(text: str) -> bool:
    t = _norm(text)
    return t in _DENY or t.startswith("yoq") or t.startswith("bekor")


def parse_amount(text: str) -> Optional[float]:
    """"6 mln", "6.5 mln", "500 ming", "6000000", "6 000 000" -> son."""
    t = _norm(text)
    m = re.search(r"(\d+[.,]?\d*)\s*(mln|million|mil|m)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000
    m = re.search(r"(\d+[.,]?\d*)\s*(ming|min|k)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000
    # Katta yaxlit son (bosh joylar bilan): 6 000 000
    m = re.search(r"\b(\d[\d\s]{3,}\d)\b", t)
    if m:
        return float(m.group(1).replace(" ", ""))
    m = re.search(r"\b(\d{4,})\b", t)
    if m:
        return float(m.group(1))
    return None


def parse_int_near(text: str, *keywords: str) -> Optional[int]:
    """Kalit soʻz yonidagi butun son: "3 kun" -> 3, "20 joy" -> 20."""
    t = _norm(text)
    for kw in keywords:
        m = re.search(r"(\d+)\s*" + kw, t)
        if m:
            return int(m.group(1))
    return None


def parse_bare_int(text: str) -> Optional[int]:
    m = re.search(r"\b(\d+)\b", _norm(text))
    return int(m.group(1)) if m else None


_UZ_MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}


def parse_date(text: str) -> Optional[str]:
    """Sanani YYYY-MM-DD ga keltiradi. Yil berilmasa joriy yildan boshlab tanlaydi."""
    t = _norm(text)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else _this_year()
        if y < 100:
            y += 2000
        return f"{y}-{mo:02d}-{d:02d}"
    m = re.search(r"(\d{1,2})[-\s]*([a-z]+)", t)
    if m and m.group(2) in _UZ_MONTHS:
        d, mo = int(m.group(1)), _UZ_MONTHS[m.group(2)]
        return f"{_this_year()}-{mo:02d}-{d:02d}"
    return None


def _this_year() -> int:
    # Test qiligʻanda barqaror boʻlsin uchun alohida — datetime.now() ishlatamiz.
    return datetime.utcnow().year


# --------------------------------------------------------------------------- #
# 3) Tool'lar — hammasi company_id bilan chegaralangan
# --------------------------------------------------------------------------- #

_CUR = {"USD": "$", "EUR": "€", "RUB": "₽"}


def _sym(c: Optional[str]) -> str:
    return _CUR.get(c or "UZS", "som")


def _money(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


async def _resolve_tour(db: AsyncSession, cid: int, ref: str) -> Optional[Tour]:
    """Tur nomini yoki id sini haqiqiy turga bogʻlaydi (faqat shu firma)."""
    ref = (ref or "").strip()
    if not ref:
        return None
    m = re.search(r"\b(\d+)\b", ref)
    if m:
        t = (await db.execute(
            select(Tour).where(Tour.id == int(m.group(1)), Tour.company_id == cid)
        )).scalar_one_or_none()
        if t:
            return t
    rows = (await db.execute(select(Tour).where(Tour.company_id == cid))).scalars().all()
    low = _norm(ref)
    for t in rows:
        if _norm(t.title) in low or low in _norm(t.title):
            return t
    # Nom soʻzma-soʻz mos kelmasa, birinchi soʻz boʻyicha ham urinamiz.
    for t in rows:
        first = _norm(t.title).split(" ")[0]
        if len(first) >= 3 and first in low:
            return t
    return None


async def _resolve_and_store(db: AsyncSession, cid: int, slots: dict, ref: str) -> bool:
    """Berilgan matndan turni topib, uning id va nomini slots ga yozadi."""
    tour = await _resolve_tour(db, cid, ref)
    if not tour:
        return False
    slots["tour_id"] = tour.id
    slots["tour_title"] = tour.title
    return True


# --------------------------------------------------------------------------- #
# 4) Dialog menejeri
# --------------------------------------------------------------------------- #

# create_tour uchun ketma-ket soraladigan maydonlar.
_CREATE_STEPS: list[tuple[str, str]] = [
    ("title", "Tur nomini yozing (masalan: Dubay sayohati)"),
    ("city", "Qaysi shahar yoki yonalish?"),
    ("price", "Narxi qancha? (masalan: 6 mln yoki 6000000)"),
    ("duration_days", "Necha kunlik tur?"),
    ("available_slots", "Necha kishilik (nechta joy)?"),
]


def _extract_create_slots(text: str, slots: dict) -> None:
    """Erkin matndan create_tour maydonlarini toʻldiradi."""
    dur = parse_int_near(text, "kun", "kunlik")
    if dur:
        slots.setdefault("duration_days", dur)
    seats = parse_int_near(text, "joy", "kishi", "orin", "o'rin", "odam")
    if seats:
        slots.setdefault("available_slots", seats)
    price = parse_amount(_strip_used(text, dur, seats))
    if price:
        slots.setdefault("price", price)
    d = parse_date(text)
    if d:
        slots.setdefault("start_date", d)
    city = _detect_city(text)
    if city:
        slots.setdefault("city", city)


def _strip_used(text: str, dur: Optional[int], seats: Optional[int]) -> str:
    """Narxni chalkashtirmaslik uchun kun/joy sonlarini matndan olib tashlaydi."""
    t = _norm(text)
    t = re.sub(r"\d+\s*(kun|kunlik)", " ", t)
    t = re.sub(r"\d+\s*(joy|kishi|orin|o'rin|odam)", " ", t)
    return t


_KNOWN_CITIES = [
    "dubay", "istanbul", "istambul", "antalya", "sharm", "bali", "turkiya", "misr",
    "malayziya", "tailand", "gruziya", "batumi", "makka", "madina", "umra", "haj",
    "parij", "rim", "moskva", "toshkent", "samarqand", "buxoro", "xiva", "qoradengiz",
]


def _detect_city(text: str) -> Optional[str]:
    t = _norm(text)
    for c in _KNOWN_CITIES:
        if c in t:
            return c.capitalize()
    return None


def _create_summary(slots: dict) -> str:
    parts = [
        f"nomi: {slots.get('title')}",
        f"shahar: {slots.get('city')}",
        f"narx: {_money(slots.get('price', 0))} som",
        f"muddat: {slots.get('duration_days')} kun",
        f"joylar: {slots.get('available_slots')}",
    ]
    if slots.get("start_date"):
        parts.append(f"boshlanish: {slots['start_date']}")
    return "Yangi tur — " + ", ".join(parts) + ". Qoshaymi? (ha / yoq)"


async def _run_report(db: AsyncSession, cid: int) -> str:
    ov = await ReportsService(db).overview(company_id=cid, range_key="28d")
    lines = [
        "Xisobot (oxirgi 28 kun):",
        f"- Sayt tashriflari: {ov.total_visits}",
        f"- Mijozlar: {ov.total_users}",
        f"- Bronlar: {ov.total_bookings}",
        f"- Daromad: {_money(ov.total_revenue)} som",
        f"- Kunlik faol: {ov.daily_active}, oylik faol: {ov.monthly_active}",
        f"- Turlar: {ov.total_tours}",
    ]
    # Yetishmovchilik tahlili — oddiy qoidalar.
    tips: list[str] = []
    if ov.total_tours == 0:
        tips.append("Hali tur yoq — birinchi turingizni qoshing.")
    if ov.total_bookings == 0:
        tips.append("Bron yoq — turlarni ijtimoiy tarmoqda ulashing yoki reklama qiling.")
    if ov.total_visits < 20:
        tips.append("Sayt tashrifi kam — havolangizni mijozlarga tarqating.")
    if ov.total_tours and ov.daily_active == 0:
        tips.append("Bugun faollik yoq — mijozlarga eslatma yuboring.")
    if ov.top:
        best = ov.top[0]
        tips.append(f"Eng kop sotilgan: {best.name} ({best.bookings} bron) — oxshash yonalish qoshing.")
    if not tips:
        tips.append("Korsatkichlar barqaror — shu suratda davom eting.")
    lines.append("")
    lines.append("Tavsiyalar:")
    lines += [f"- {t}" for t in tips]
    return "\n".join(lines)


async def _run_read_intent(db: AsyncSession, cid: int, intent: str) -> str:
    if intent == "count_tours":
        n = (await db.execute(select(func.count(Tour.id)).where(Tour.company_id == cid))).scalar() or 0
        active = (await db.execute(
            select(func.count(Tour.id)).where(Tour.company_id == cid, Tour.is_active == True)  # noqa: E712
        )).scalar() or 0
        return f"Sizda jami {n} ta tur bor ({active} tasi faol)."

    if intent == "list_tours":
        rows = (await db.execute(
            select(Tour).where(Tour.company_id == cid).order_by(Tour.created_at.desc()).limit(15)
        )).scalars().all()
        if not rows:
            return "Hali tur yoq. Yangi tur qoshish uchun 'tur qosh' deng."
        lines = ["Turlaringiz:"]
        for t in rows:
            holat = "faol" if t.is_active else "nofaol"
            lines.append(f"- #{t.id} {t.title} — {t.city}, {_money(t.price)} {_sym(t.currency)}, {t.available_slots} joy ({holat})")
        return "\n".join(lines)

    if intent == "count_customers":
        n = (await db.execute(
            select(func.count(func.distinct(Booking.user_id))).where(Booking.company_id == cid)
        )).scalar() or 0
        return f"Sizda {n} ta mijoz bron qilgan."

    if intent == "recent_bookings":
        rows = (await db.execute(
            select(Booking.id, Booking.status, Booking.total_price, Booking.created_at, Tour.title)
            .join(Tour, Tour.id == Booking.tour_id)
            .where(Booking.company_id == cid)
            .order_by(Booking.created_at.desc()).limit(8)
        )).all()
        if not rows:
            return "Hozircha bron yoq."
        lines = ["Oxirgi bronlar:"]
        for r in rows:
            holat = r[1].value if hasattr(r[1], "value") else str(r[1])
            sana = r[3].strftime("%d.%m") if r[3] else "-"
            lines.append(f"- {r[4]} — {_money(float(r[2] or 0))} som, {holat}, {sana}")
        return "\n".join(lines)

    if intent == "get_plan":
        company = (await db.execute(select(Company).where(Company.id == cid))).scalar_one_or_none()
        plan = get_tariff(getattr(company, "tariff", DEFAULT_TARIFF) if company else DEFAULT_TARIFF)
        used = (await db.execute(select(func.count(Tour.id)).where(Tour.company_id == cid))).scalar() or 0
        mx = plan.get("max_tours")
        limit_txt = "cheksiz" if mx is None else str(mx)
        return f"Tarifingiz: {plan['name']}. Turlar: {used} / {limit_txt}."

    return "Tushunmadim."


_HELP = (
    "Men firmangiz yordamchisiman. Mana nima soray olasiz:\n"
    "- Xisobot: 'bu oy qancha daromad', 'yetishmovchiliklar'\n"
    "- Turlar: 'nechta tur bor', 'turlar royxati'\n"
    "- Mijozlar: 'nechta mijoz', 'oxirgi bronlar'\n"
    "- Amal: 'yangi tur qosh', 'narxni ozgartir', 'turni nofaol qil'\n"
    "Kerakli malumotni oʻzim ketma-ket sorayman."
)


async def _handle_no_pending(db: AsyncSession, cid: int, message: str) -> dict:
    intent, conf = _store().predict(message)

    if intent == "greeting":
        return _reply("Salom! Firmangiz boyicha savol bering yoki buyruq bering. Masalan: 'nechta tur bor' yoki 'yangi tur qosh'.")
    if intent == "help" or intent == "unknown":
        return _reply(_HELP)

    # Oʻqish intentlari — javob berilgach ishonchli boʻlsa oʻrganamiz.
    if intent == "report":
        reply = await _run_report(db, cid)
        if conf >= _LEARN_CONF:
            await _store().learn(db, cid, message, intent)
        return _reply(reply)
    if intent in ("count_tours", "list_tours", "count_customers", "recent_bookings", "get_plan"):
        reply = await _run_read_intent(db, cid, intent)
        if conf >= _LEARN_CONF:
            await _store().learn(db, cid, message, intent)
        return _reply(reply)

    # Yozuvchi intentlar — asl buyruqni saqlaymiz, tasdiqlangach oʻrganamiz.
    if intent == "create_tour":
        slots: dict = {"_trigger": message}
        _extract_create_slots(message, slots)
        if not slots.get("title") and slots.get("city"):
            slots["title"] = f"{slots['city']} sayohati"
        return _advance_create(slots)

    if intent == "update_price":
        slots = {"_trigger": message}
        price = parse_amount(message)
        if price:
            slots["price"] = price
        await _resolve_and_store(db, cid, slots, message)
        return _advance_update_price(slots)

    if intent == "set_active":
        t = _norm(message)
        slots = {"_trigger": message,
                 "is_active": not any(w in t for w in ("nofaol", "yashir", "ochir", "yoq"))}
        await _resolve_and_store(db, cid, slots, message)
        return _advance_set_active(slots)

    return _reply(_HELP)


def _advance_create(slots: dict) -> dict:
    for field, prompt in _CREATE_STEPS:
        if slots.get(field) in (None, ""):
            return _reply(prompt, pending={"intent": "create_tour", "slots": slots, "stage": "collect", "awaiting": field})
    return _reply(_create_summary(slots), pending={"intent": "create_tour", "slots": slots, "stage": "confirm"})


def _advance_update_price(slots: dict) -> dict:
    if not slots.get("tour_id"):
        return _reply("Qaysi turning narxini ozgartiramiz? Nomini yoki id sini yozing.",
                      pending={"intent": "update_price", "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
    if not slots.get("price"):
        return _reply("Yangi narx qancha? (masalan: 6 mln)",
                      pending={"intent": "update_price", "slots": slots, "stage": "collect", "awaiting": "price"})
    return _reply(f"'{slots['tour_title']}' narxini {_money(slots['price'])} som ga ozgartiraymi? (ha / yoq)",
                  pending={"intent": "update_price", "slots": slots, "stage": "confirm"})


def _advance_set_active(slots: dict) -> dict:
    if not slots.get("tour_id"):
        return _reply("Qaysi turni ozgartiramiz? Nomini yoki id sini yozing.",
                      pending={"intent": "set_active", "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
    holat = "faollashtiraymi" if slots.get("is_active") else "nofaol qilaymi"
    return _reply(f"'{slots['tour_title']}' turini {holat}? (ha / yoq)",
                  pending={"intent": "set_active", "slots": slots, "stage": "confirm"})


async def _handle_pending(db: AsyncSession, cid: int, message: str, pending: dict) -> dict:
    intent = pending.get("intent")
    slots = dict(pending.get("slots") or {})
    stage = pending.get("stage")

    if is_deny(message):
        return _reply("Bekor qilindi.")

    if stage == "confirm":
        if is_affirm(message):
            return await _execute(db, cid, intent, slots)
        # Tasdiq emas — qayta soraymiz.
        if intent == "create_tour":
            return _reply(_create_summary(slots), pending={"intent": intent, "slots": slots, "stage": "confirm"})
        return _reply("Tasdiqlash uchun 'ha', bekor uchun 'yoq' deng.",
                      pending={"intent": intent, "slots": slots, "stage": "confirm"})

    # stage == collect: kutilayotgan maydonni toʻldiramiz
    awaiting = pending.get("awaiting")
    if intent == "create_tour":
        if awaiting == "price":
            v = parse_amount(message)
            if v:
                slots["price"] = v
        elif awaiting == "duration_days":
            v = parse_int_near(message, "kun", "kunlik") or parse_bare_int(message)
            if v:
                slots["duration_days"] = v
        elif awaiting == "available_slots":
            v = parse_int_near(message, "joy", "kishi", "orin") or parse_bare_int(message)
            if v:
                slots["available_slots"] = v
        elif awaiting in ("title", "city"):
            slots[awaiting] = message.strip()
        # Har ehtimolga qarshi qolgan maydonlarni ham matndan qidiramiz.
        _extract_create_slots(message, slots)
        return _advance_create(slots)

    if intent == "update_price":
        if awaiting == "tour_ref":
            if not await _resolve_and_store(db, cid, slots, message):
                return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.",
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
        elif awaiting == "price":
            v = parse_amount(message)
            if v:
                slots["price"] = v
        return _advance_update_price(slots)

    if intent == "set_active":
        if awaiting == "tour_ref":
            if not await _resolve_and_store(db, cid, slots, message):
                return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.",
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
        return _advance_set_active(slots)

    return _reply(_HELP)


async def _execute(db: AsyncSession, cid: int, intent: str, slots: dict) -> dict:
    try:
        if intent == "create_tour":
            res = await _do_create(db, cid, slots)
        elif intent == "update_price":
            res = await _do_update_price(db, cid, slots)
        elif intent == "set_active":
            res = await _do_set_active(db, cid, slots)
        else:
            return _reply("Tushunmadim.")
    except Exception:  # noqa: BLE001 — amal xatosi suhbatni buzmasin
        logger.exception("ML assistant amal xatosi: %s", intent)
        await db.rollback()
        return _reply("Amalni bajarishda xatolik boldi. Qaytadan urinib koring.")
    # Amal muvaffaqiyatli bajarildi — asl buyruqni oʻrganamiz (tasdiqlangan misol).
    if res.get("actions"):
        await _store().learn(db, cid, str(slots.get("_trigger", "")), intent)
    return res


async def _do_create(db: AsyncSession, cid: int, slots: dict) -> dict:
    try:
        price = float(slots["price"])
        duration = int(slots["duration_days"])
        seats = int(slots["available_slots"])
    except (KeyError, TypeError, ValueError):
        return _reply("Malumot toliq emas, qaytadan boshlaymiz. 'tur qosh' deng.")
    if price <= 0 or duration < 1 or seats < 1:
        return _reply("Narx musbat, kun va joylar kamida 1 boʻlishi kerak.")

    used = (await db.execute(select(func.count(Tour.id)).where(Tour.company_id == cid))).scalar() or 0
    tariff = (await db.execute(select(Company.tariff).where(Company.id == cid))).scalar_one_or_none()
    if not within_tour_limit(tariff, used):
        return _reply("Tarif boyicha turlar limiti tugagan — yuqori tarifga oting.")

    start_date: Optional[date] = None
    if slots.get("start_date"):
        try:
            start_date = datetime.strptime(str(slots["start_date"]), "%Y-%m-%d").date()
        except ValueError:
            start_date = None

    title = str(slots.get("title") or f"{slots.get('city', 'Yangi')} sayohati")
    city = str(slots.get("city") or title)
    tour = Tour(
        company_id=cid, title=title, description=f"{title} — {city}. {duration} kunlik tur.",
        city=city, country="Uzbekistan", price=price, currency="UZS",
        duration_days=duration, available_slots=seats, booking_type="group",
        start_date=start_date, is_active=True,
    )
    db.add(tour)
    await db.commit()
    await db.refresh(tour)
    return _reply(f"Tayyor! '{tour.title}' turi qoshildi (#{tour.id}).",
                  actions=[f"Tur qoshildi: {tour.title}"])


async def _do_update_price(db: AsyncSession, cid: int, slots: dict) -> dict:
    tour = await _resolve_tour(db, cid, str(slots.get("tour_id") or slots.get("tour_ref", "")))
    if not tour:
        return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.")
    try:
        price = float(slots["price"])
    except (KeyError, TypeError, ValueError):
        return _reply("Yangi narx notogri.")
    if price <= 0:
        return _reply("Narx musbat boʻlishi kerak.")
    old = tour.price
    tour.price = price
    await db.commit()
    return _reply(f"'{tour.title}' narxi {_money(old)} -> {_money(price)} som ga ozgartirildi.",
                  actions=[f"{tour.title} narxi yangilandi: {_money(price)} som"])


async def _do_set_active(db: AsyncSession, cid: int, slots: dict) -> dict:
    tour = await _resolve_tour(db, cid, str(slots.get("tour_id") or slots.get("tour_ref", "")))
    if not tour:
        return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.")
    is_active = bool(slots.get("is_active", True))
    tour.is_active = is_active
    await db.commit()
    holat = "faollashtirildi" if is_active else "nofaol qilindi"
    return _reply(f"'{tour.title}' {holat}.", actions=[f"{tour.title} {holat}"])


def _reply(text: str, actions: Optional[list[str]] = None, pending: Optional[dict] = None) -> dict:
    return {"reply": text, "actions": actions or [], "pending": pending}


# --------------------------------------------------------------------------- #
# Commumiy kirish nuqtasi
# --------------------------------------------------------------------------- #

async def run_assistant(
    db: AsyncSession, user: User, message: str, pending: Optional[dict] = None
) -> dict:
    """Bitta suhbat qadamini bajaradi. {reply, actions, pending} qaytaradi."""
    cid = user.company_id
    if not cid:
        return _reply("Kompaniyaga biriktirilmagansiz.")
    message = (message or "").strip()
    if not message:
        return _reply("Savol yoki buyruq yozing.")

    # Oʻrgangan misollarni yangilab olamiz (boshqa worker qoshgan boʻlishi mumkin).
    await _store().ensure_fresh(db)

    if pending and pending.get("intent"):
        return await _handle_pending(db, cid, message, pending)
    return await _handle_no_pending(db, cid, message)
