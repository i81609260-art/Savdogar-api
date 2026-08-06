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
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.models.assistant_example import AssistantExample
from app.models.booking import Booking, BookingStatus
from app.models.company import Company
from app.models.tour import Tour
from app.models.user import User
from app.schemas.crm import CustomerCreateRequest
from app.schemas.tour import TourCreate, TourUpdate
from app.services.crm_service import CRMService
from app.services.reports_service import ReportsService
from app.services.offer_service import group_by_hotel, search_by_query
from app.services.tariff import DEFAULT_TARIFF, get_tariff, within_tour_limit
from app.services.tella_tour_search import (
    SEARCH_INTENT,
    SEARCH_KEYWORDS,
    SEARCH_TRAINING,
    extract_query,
    next_question,
    summarize,
)
from app.services.tour_service import TourService

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
    ("nimalarga yordam berasan", "help"), ("qanday yordam berasan", "help"),
    ("vazifang nima", "help"), ("nima ish qilasan", "help"),
    ("qanaqa buyruqlar bor", "help"), ("qanday komandalar bor", "help"),
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
    # list_customers
    ("mijozlar royxati", "list_customers"), ("mijozlarni korsat", "list_customers"),
    ("mijozlarim", "list_customers"), ("mijozlar kimlar", "list_customers"),
    ("mijozlar royxatini ber", "list_customers"),
    # instagram_leads
    ("instagram lidlari", "instagram_leads"), ("instagramdan nechta lead", "instagram_leads"),
    ("instagram sorovlari", "instagram_leads"), ("instagramdan kim yozdi", "instagram_leads"),
    ("instagram leadlari", "instagram_leads"), ("instagram statistikasi", "instagram_leads"),
    # create_customer
    ("mijoz qosh", "create_customer"), ("yangi mijoz qosh", "create_customer"),
    ("mijoz qoshmoqchiman", "create_customer"), ("mijoz qoshish", "create_customer"),
    ("yangi mijoz yarat", "create_customer"), ("mijozni royxatga ol", "create_customer"),
    ("mijoz royxatdan otkaz", "create_customer"), ("mijoz kirit", "create_customer"),
    # update_tour — narxdan tashqari maydonlarni tahrirlash
    ("turni tahrirla", "update_tour"), ("tur nomini ozgartir", "update_tour"),
    ("nomini ozgartir", "update_tour"), ("shahrini ozgartir", "update_tour"),
    ("yonalishini ozgartir", "update_tour"), ("muddatini ozgartir", "update_tour"),
    ("kunini ozgartir", "update_tour"), ("joylar sonini ozgartir", "update_tour"),
    ("sanasini ozgartir", "update_tour"), ("turni ozgartir", "update_tour"),
    ("tur malumotini yangila", "update_tour"), ("turni tahrirlamoqchiman", "update_tour"),
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
    # unknown / notegishli — firma ishiga aloqasi yoq (Tella AI rad etadi)
    ("bugun ob-havo qanday", "unknown"), ("ertaga yomgir yogadimi", "unknown"),
    ("python kod yoz", "unknown"), ("kod yozib ber", "unknown"),
    ("dastur yoz", "unknown"), ("sayt yasab ber", "unknown"),
    ("prezident kim", "unknown"), ("poytaxt qayer", "unknown"),
    ("2 qoshuv 2 nechchi", "unknown"), ("matematika masala yech", "unknown"),
    ("hazil ayt", "unknown"), ("sher yoz", "unknown"),
    ("qanday odamsan", "unknown"), ("seni kim yaratgan", "unknown"),
    ("futbol natijalari", "unknown"), ("yangiliklar nima", "unknown"),
    ("retsept ber", "unknown"), ("kino tavsiya qil", "unknown"),
    ("tarjima qilib ber", "unknown"), ("ingliz tili organaman", "unknown"),
    ("qanaqa telefon olay", "unknown"), ("salomatlik maslahat ber", "unknown"),
    ("kripto valyuta narxi", "unknown"), ("dollar kursi qancha", "unknown"),
]

# Tur operatorlardan qidirish — misollar alohida modulda, taksonomiya bilan
# birga turadi. Shu bilan ma'lumotnoma va o'quv misollari bir joyda saqlanadi.
INTENT_TRAINING += SEARCH_TRAINING

_CONF_THRESHOLD = 0.18  # past ishonchda -> unknown

# Kritik intentlar uchun kalit soʻz tayanchi (kichik dataset ishonchsizligiga qarshi).
# DIQQAT: birinchi mos kelgan kalit gʻalaba qiladi, shuning uchun aniqroq
# (koʻp soʻzli) iboralar umumiylaridan OLDIN turishi shart. Masalan
# "mijoz qosh" — "qosh" dan oldin boʻlmasa, tur qoshishga ketib qoladi.
_KEYWORDS: list[tuple[str, str]] = [
    # --- Operatorlardan tur qidirish ---
    # "qosh" dan OLDIN turishi shart: "arzon tur topib qosh" kabi ibora
    # aks holda tur yaratishga ketib qolardi.
    *((kw, SEARCH_INTENT) for kw in SEARCH_KEYWORDS),
    # --- Instagram (oʻziga xos soʻz, hech narsa bilan chalkashmaydi) ---
    ("instagram", "instagram_leads"), ("insta", "instagram_leads"),
    # --- Mijoz amallari (eng aniq) ---
    ("mijoz qosh", "create_customer"), ("mijoz qoshish", "create_customer"),
    ("yangi mijoz", "create_customer"), ("mijoz yarat", "create_customer"),
    ("mijozni royxatga", "create_customer"), ("mijoz kirit", "create_customer"),
    ("mijozlar royxati", "list_customers"), ("mijozlarni korsat", "list_customers"),
    ("mijozlarim", "list_customers"),
    # --- Tur tahrirlash — aniq iboralar ---
    # "narx" oʻzi juda keng (masalan "kripto narxi") — narx oʻzgartirishni
    # klassifikatorga qoldiramiz, faqat aniq iboralarni tayanch qilamiz.
    ("narxni ozgartir", "update_price"), ("narxini ozgartir", "update_price"),
    ("narxini yangila", "update_price"), ("narx ozgartir", "update_price"),
    ("nomini ozgartir", "update_tour"), ("nomini yangila", "update_tour"),
    ("shahrini ozgartir", "update_tour"), ("yonalishini ozgartir", "update_tour"),
    ("kunini ozgartir", "update_tour"), ("muddatini ozgartir", "update_tour"),
    ("joyini ozgartir", "update_tour"), ("joylarini ozgartir", "update_tour"),
    ("joylar sonini", "update_tour"), ("sanasini ozgartir", "update_tour"),
    ("turni tahrirla", "update_tour"), ("tahrirla", "update_tour"),
    # --- Tur qoshish (umumiy "qosh" shu yerda) ---
    ("tur qosh", "create_tour"), ("qosh", "create_tour"), ("yarat", "create_tour"),
    ("faollashtir", "set_active"), ("nofaol", "set_active"), ("yashir", "set_active"),
    ("xisobot", "report"), ("hisobot", "report"), ("daromad", "report"), ("statistika", "report"),
    ("royxat", "list_tours"),
    ("nechta tur", "count_tours"), ("tur soni", "count_tours"),
    ("nechta mijoz", "count_customers"), ("mijozlar soni", "count_customers"),
    ("mijoz", "count_customers"),
    ("bron", "recent_bookings"),
    ("tarif", "get_plan"),
]

# Yozuvchi (oʻzgartiruvchi) intentlar — kalit soʻz topilsa klassifikatordan ustun.
_WRITE_INTENTS = ("create_tour", "update_price", "set_active", "create_customer", "update_tour")

# Qoshish maʼnosini beruvchi feʼllar.
_CREATE_VERBS = ("qosh", "yarat", "kirit", "royxatga", "royxatdan")


def _pair_intent(t: str) -> Optional[str]:
    """Ikki soʻzli qoida — soʻzlar yonma-yon kelmasa ham ishlaydi.

    "Alini mijoz qilib kirit" kabi gapda "mijoz kirit" ketma-ket emas, shuning
    uchun oddiy kalit soʻz mos kelmay, "mijoz" -> count_customers ga tushib
    ketardi. Bu yerda "mijoz" + qoshish feʼli birgalikda tekshiriladi.
    """
    if "mijoz" in t and any(v in t for v in _CREATE_VERBS):
        return "create_customer"
    return None


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
        # Ikki soʻzli qoida kalit soʻzlardan ustun turadi.
        pair = _pair_intent(t)
        if pair:
            return pair, max(conf, 0.6)
        # Kalit soʻz tayanchi — ishonch past yoki aniq kalit boʻlsa ustuvor.
        for kw, kw_intent in _KEYWORDS:
            if kw in t:
                if conf < 0.5 or kw_intent in _WRITE_INTENTS:
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

_APOSTROPHES = "'‘’ʻʼ`´"


def _norm(text: str) -> str:
    """Matnni solishtirish uchun bir shaklga keltiradi.

    Tutuq belgilari BUTUNLAY olib tashlanadi — dataset va kalit soʻzlar
    tutuqsiz yozilgan, foydalanuvchi esa "qo'sh", "o'zgartir" deb yozadi.
    Shusiz bunday xabarlar hech bir kalit soʻzga mos kelmay qolardi.
    """
    t = (text or "").lower()
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    return re.sub(r"\s+", " ", t).strip()

_AFFIRM = {"ha", "xa", "ha ha", "mayli", "boladi", "ok", "okay", "hop", "xop",
           "tasdiqlayman", "tasdiq", "davom", "albatta", "roziman", "qosh", "qoshaver"}
_DENY = {"yoq", "yo", "kerakmas", "kerak emas", "bekor", "bekor qil", "xohlamayman",
         "kerakmagan", "yoq kerak emas"}


def is_affirm(text: str) -> bool:
    t = _norm(text)
    return t in _AFFIRM or any(t.startswith(a + " ") or t == a for a in _AFFIRM)


def is_deny(text: str) -> bool:
    t = _norm(text)
    if t in _DENY or t.startswith("bekor"):
        return True
    # Faqat aniq "yoq" / "yoq ..." rad hisoblanadi. Oldin startswith("yoq")
    # edi — mijoz ismi "Yoqubjon" boʻlsa suhbatni bekor qilib yuborardi.
    return t == "yoq" or t.startswith("yoq ")


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


def _valid_date(y: int, mo: int, d: int) -> Optional[str]:
    """Haqiqiy sana bolsagina YYYY-MM-DD qaytaradi.

    Oldin tekshiruv yoq edi va "2026-00-00" kabi mavjud bolmagan sana
    qaytardi — keyin u jimgina None ga aylanib, baza NOT NULL xatosini
    berardi. Endi yaroqsiz sana darhol None.
    """
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_date(text: str) -> Optional[str]:
    """Sanani YYYY-MM-DD ga keltiradi. Yil berilmasa joriy yildan boshlab tanlaydi."""
    t = _norm(text)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # kk.oo[.yyyy] — atrofida boshqa raqam bolmasligi shart, aks holda
    # "600.000" (narx) ichidan "00.00" sana sifatida ajratilib ketardi.
    # Ortidan pul birligi kelsa bu narx, sana emas ("1.5 mln").
    m = re.search(
        r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)"
        r"(?!\s*(?:mln|million|mil|ming|min|so|som|usd|eur)\b)",
        t,
    )
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else _this_year()
        if y < 100:
            y += 2000
        return _valid_date(y, mo, d)
    m = re.search(r"\b(\d{1,2})[-\s]*([a-z]+)", t)
    if m and m.group(2) in _UZ_MONTHS:
        return _valid_date(_this_year(), _UZ_MONTHS[m.group(2)], int(m.group(1)))
    return None


def _this_year() -> int:
    # Test qiligʻanda barqaror boʻlsin uchun alohida — datetime.now() ishlatamiz.
    return datetime.utcnow().year


_PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def parse_phone(text: str) -> Optional[str]:
    """"+998 90 123 45 67", "901234567" -> "+998901234567"."""
    m = _PHONE_RE.search(text or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    if len(digits) == 9:  # operator kodi bilan yozilgan lokal raqam
        digits = "998" + digits
    if len(digits) < 9:
        return None
    return "+" + digits


def parse_email(text: str) -> Optional[str]:
    m = _EMAIL_RE.search(text or "")
    return m.group(0) if m else None


def _strip_contacts(text: str) -> str:
    """Ism ajratishda telefon/email matn ichida qolib ketmasin."""
    t = _EMAIL_RE.sub(" ", text or "")
    t = _PHONE_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


# Mijoz qoshish buyrugʻidan tur nomini ajratishda buyruq soʻzlari xalaqit
# bermasin (masalan "Dubay turiga mijoz qosh" -> "dubay turiga").
_CMD_WORDS_RE = re.compile(
    r"\b(mijoz|mijozni|mijozga|qosh|qoshish|qoshaver|qoshmoqchiman|yangi|yarat|"
    r"royxatga|royxatdan|otkaz|ol|kirit)\b"
)


def _strip_cmd_words(text: str) -> str:
    return re.sub(r"\s+", " ", _CMD_WORDS_RE.sub(" ", _norm(text))).strip()


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


async def _tour_not_found_hint(db: AsyncSession, cid: int) -> str:
    """Tur topilmasa — mavjudlarini korsatamiz yoki tur yoqligini aytamiz."""
    rows = (await db.execute(
        select(Tour.id, Tour.title).where(Tour.company_id == cid)
        .order_by(Tour.created_at.desc()).limit(5)
    )).all()
    if not rows:
        return ("Sizda hali tur yoq — mijozni turga yozib bolmaydi. "
                "Avval 'tur qosh' deb tur paket qoshing.")
    lines = ["Bunday tur topilmadi. Mavjud turlaringiz:"]
    lines += [f"- #{r[0]} {r[1]}" for r in rows]
    lines.append("Nomini yoki id sini yozing.")
    return "\n".join(lines)


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
# "Sana korsatilmagan" belgisi — None dan farqli, chunki None bolsa
# _advance_create maydonni yana soraydi.
_NO_DATE = "-"

_CREATE_STEPS: list[tuple[str, str]] = [
    ("title", "Tur nomini yozing (masalan: Dubay sayohati)"),
    ("city", "Qaysi shahar yoki yonalish?"),
    ("price", "Narxi qancha? (masalan: 6 mln yoki 6000000)"),
    ("duration_days", "Necha kunlik tur?"),
    ("available_slots", "Necha kishilik (nechta joy)?"),
    # Sana soraladi: bazada bu maydon majburiy bolishi mumkin (eski
    # migratsiyada NOT NULL edi), soralmasa tur qoshilmay qolardi.
    ("start_date", "Qachon boshlanadi? (masalan: 2026-08-15). Sana hali nomaʼlum bolsa 'yoq' deng"),
]


def _extract_create_slots(text: str, slots: dict, with_date: bool = True) -> None:
    """Erkin matndan create_tour maydonlarini toʻldiradi.

    `with_date=False` — aniq maydon soralayotganda (narx, kun, joy) sanani
    qidirmaymiz. Aks holda "1.5 mln" kabi javob sana deb talqin qilinib,
    sana bosqichi jimgina otkazib yuborilardi.
    """
    dur = parse_int_near(text, "kun", "kunlik")
    if dur:
        slots.setdefault("duration_days", dur)
    seats = parse_int_near(text, "joy", "kishi", "orin", "odam", "nafar")
    if seats:
        slots.setdefault("available_slots", seats)
    price = parse_amount(_strip_used(text, dur, seats))
    if price:
        slots.setdefault("price", price)
    if with_date:
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
    t = re.sub(r"\d+\s*(joy|kishi|orin|odam|nafar)", " ", t)
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
    sd = slots.get("start_date")
    parts.append(f"boshlanish: {sd}" if sd and sd != _NO_DATE else "boshlanish: korsatilmagan")
    return "Yangi tur — " + ", ".join(parts) + ". Qoshaymi? (ha / yoq)"


# --- Mijoz qoshish ----------------------------------------------------------

# tour_ref alohida ishlanadi (slots ga tour_id sifatida yoziladi).
_CUSTOMER_STEPS: list[tuple[str, str]] = [
    ("full_name", "Mijozning ism-familiyasini yozing"),
    ("phone", "Telefon raqami? (masalan: +998901234567)"),
    ("tour_ref", "Qaysi turga yozamiz? Tur nomini yoki id sini yozing"),
    ("guests_count", "Necha kishi? (masalan: 2)"),
]


def _extract_customer_slots(text: str, slots: dict) -> None:
    """Erkin matndan mijoz maydonlarini toʻldiradi (bor qiymat ustiga yozmaydi)."""
    ph = parse_phone(text)
    if ph:
        slots.setdefault("phone", ph)
    em = parse_email(text)
    if em:
        slots.setdefault("email", em)
    g = parse_int_near(text, "kishi", "odam", "nafar")
    if g:
        slots.setdefault("guests_count", g)


def _customer_summary(slots: dict) -> str:
    parts = [
        f"ism: {slots.get('full_name')}",
        f"telefon: {slots.get('phone')}",
        f"tur: {slots.get('tour_title')}",
        f"kishi: {slots.get('guests_count')}",
    ]
    if slots.get("email"):
        parts.append(f"email: {slots['email']}")
    return "Yangi mijoz — " + ", ".join(parts) + ". Qoshaymi? (ha / yoq)"


def _advance_create_customer(slots: dict) -> dict:
    for field, prompt in _CUSTOMER_STEPS:
        if field == "tour_ref":
            if not slots.get("tour_id"):
                return _reply(prompt, pending={"intent": "create_customer", "slots": slots,
                                               "stage": "collect", "awaiting": "tour_ref"})
            continue
        if slots.get(field) in (None, ""):
            return _reply(prompt, pending={"intent": "create_customer", "slots": slots,
                                           "stage": "collect", "awaiting": field})
    return _reply(_customer_summary(slots),
                  pending={"intent": "create_customer", "slots": slots, "stage": "confirm"})


# --- Tur tahrirlash (narxdan tashqari maydonlar) -----------------------------

# (maydon, kalit soʻzlar, soʻrov matni). Tartib muhim — birinchi mos kelgan
# maydon tanlanadi, shuning uchun aniqroq kalitlar yuqorida.
_TOUR_FIELDS: list[tuple[str, tuple[str, ...], str]] = [
    ("title", ("nom", "sarlavha"), "Yangi nomni yozing"),
    ("city", ("shahar", "shahr", "yonalish"), "Yangi shahar yoki yonalish?"),
    ("price", ("narx",), "Yangi narx qancha? (masalan: 6 mln)"),
    ("duration_days", ("kun", "muddat"), "Necha kunlik? (masalan: 5)"),
    ("available_slots", ("joy", "orin", "kishi"), "Necha kishilik (nechta joy)?"),
    ("start_date", ("sana", "boshlanish"), "Boshlanish sanasi? (masalan: 2026-08-15)"),
]

_FIELD_LABEL = {
    "title": "nomi", "city": "shahri", "price": "narxi",
    "duration_days": "muddati", "available_slots": "joylar soni",
    "start_date": "boshlanish sanasi",
}


def _detect_tour_field(text: str) -> Optional[str]:
    t = _norm(text)
    for field, kws, _ in _TOUR_FIELDS:
        for kw in kws:
            if re.search(r"\b" + kw, t):
                return field
    return None


def _parse_tour_value(field: str, text: str) -> Any:
    if field == "price":
        return parse_amount(text)
    if field == "duration_days":
        return parse_int_near(text, "kun", "kunlik", "muddat") or parse_bare_int(text)
    if field == "available_slots":
        return parse_int_near(text, "joy", "kishi", "orin", "nafar") or parse_bare_int(text)
    if field == "start_date":
        return parse_date(text)
    return text.strip() or None


def _format_tour_value(field: str, value: Any) -> str:
    if field == "price":
        return f"{_money(float(value))} som"
    return str(value)


def _advance_update_tour(slots: dict) -> dict:
    if not slots.get("tour_id"):
        return _reply("Qaysi turni tahrirlaymiz? Nomini yoki id sini yozing.",
                      pending={"intent": "update_tour", "slots": slots,
                               "stage": "collect", "awaiting": "tour_ref"})
    if not slots.get("field"):
        return _reply("Nimani ozgartiramiz? (nomi / shahri / narxi / muddati / joylar soni / sanasi)",
                      pending={"intent": "update_tour", "slots": slots,
                               "stage": "collect", "awaiting": "field"})
    field = slots["field"]
    if slots.get("value") in (None, ""):
        prompt = next((p for f, _, p in _TOUR_FIELDS if f == field), "Yangi qiymatni yozing")
        return _reply(prompt, pending={"intent": "update_tour", "slots": slots,
                                       "stage": "collect", "awaiting": "value"})
    label = _FIELD_LABEL.get(field, field)
    return _reply(
        f"'{slots['tour_title']}' turining {label}ni "
        f"{_format_tour_value(field, slots['value'])} ga ozgartiraymi? (ha / yoq)",
        pending={"intent": "update_tour", "slots": slots, "stage": "confirm"},
    )


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

    if intent == "list_customers":
        rows = (await db.execute(
            select(
                User.full_name,
                User.phone,
                func.count(Booking.id).label("cnt"),
                func.coalesce(func.sum(Booking.total_price), 0).label("spent"),
            )
            .join(Booking, Booking.user_id == User.id)
            .where(Booking.company_id == cid)
            .group_by(User.id, User.full_name, User.phone)
            .order_by(func.max(Booking.created_at).desc())
            .limit(15)
        )).all()
        if not rows:
            return "Hali mijoz yoq. Yangi mijoz qoshish uchun 'mijoz qosh' deng."
        lines = ["Mijozlaringiz:"]
        for r in rows:
            tel = r[1] or "telefon yoq"
            lines.append(f"- {r[0]} — {tel}, {r[2]} bron, {_money(float(r[3] or 0))} som")
        return "\n".join(lines)

    if intent == "instagram_leads":
        from app.models.request import TourRequest

        total = (await db.execute(
            select(func.count(TourRequest.id)).where(
                TourRequest.company_id == cid, TourRequest.source == "instagram"
            )
        )).scalar() or 0
        if not total:
            return ("Instagramdan hali lead kelmagan. Integratsiyalar bolimida "
                    "Instagram akkauntni ulaganingizni tekshiring.")
        yangi = (await db.execute(
            select(func.count(TourRequest.id)).where(
                TourRequest.company_id == cid,
                TourRequest.source == "instagram",
                TourRequest.status == "Yangi",
            )
        )).scalar() or 0
        rows = (await db.execute(
            select(TourRequest.lead_name, TourRequest.lead_phone,
                   TourRequest.destination, TourRequest.status)
            .where(TourRequest.company_id == cid, TourRequest.source == "instagram")
            .order_by(TourRequest.created_at.desc()).limit(10)
        )).all()
        lines = [f"Instagramdan {total} ta lead keldi ({yangi} tasi yangi).", "", "Oxirgilari:"]
        for r in rows:
            tel = r[1] or "telefon yoq"
            yon = r[2] or "yonalish korsatilmagan"
            lines.append(f"- {r[0]} — {tel}, {yon} ({r[3]})")
        return "\n".join(lines)

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


_CAPABILITIES = (
    "- Xisobot: 'bu oy qancha daromad', 'yetishmovchiliklar'\n"
    "- Turlar: 'nechta tur bor', 'turlar royxati'\n"
    "- Mijozlar: 'nechta mijoz', 'mijozlar royxati', 'oxirgi bronlar'\n"
    "- Instagram: 'instagram lidlari'\n"
    "- Tur amallari: 'yangi tur qosh', 'narxni ozgartir', 'nomini ozgartir',\n"
    "  'muddatini ozgartir', 'turni nofaol qil'\n"
    "- Mijoz amallari: 'mijoz qosh'"
)

_HELP = (
    "Men Tella AI — tur firmangiz yordamchisiman. Mana nima soray olasiz:\n"
    + _CAPABILITIES
    + "\nKerakli malumotni oʻzim ketma-ket sorayman."
)

# Notegishli (firma ishiga aloqasiz) savolga aniq rad javobi.
_OFFTOPIC = (
    "Kechirasiz, men Tella AI — faqat tur firmangiz ishlariga yordam beraman "
    "(turlar, mijozlar, bronlar, xisobot). Boshqa mavzular yoki umumiy "
    "savollarga javob bermayman.\n\nMana nima soray olasiz:\n" + _CAPABILITIES
)


# Yumshatilgan shartlarni agentga tushunarli aytish uchun.
_RELAXED_LABELS = {
    "nights": "kecha soni",
    "board": "ovqatlanish",
    "star": "yulduz",
    "price": "narx chegarasi",
    "city": "kurort",
}


async def _start_tour_search(db: AsyncSession, cid: int, message: str) -> dict:
    """So'rovni tahlil qiladi va yig'ilgan narxlar ichidan javob topadi.

    Manba — price-list'lardan yig'ilgan `tour_offers`. Jonli operator
    qidiruvi (RPA) qo'shilganda natijalar AYNAN shu jadvalga tushadi, ya'ni
    bu funksiya o'zgarmaydi.
    """
    query = extract_query(message)

    question = next_question(query)
    if question:
        return _reply(
            f"Qidiruv uchun yana bir narsa kerak.\n{question}",
            pending={"intent": SEARCH_INTENT, "stage": "collect",
                     "query": query.to_dict()},
        )

    offers, dropped = await search_by_query(db, company_id=cid, query=query)
    if not offers:
        return _reply(
            f"«{summarize(query)}» bo'yicha narx topilmadi.\n\n"
            "Operatordan kelgan price-list'ni yuklang: panel → <b>Narxlar</b>, "
            "yoki price-list'ni firma botiga forward qiling."
        )

    lines = [f"🔎 {summarize(query)}"]

    # Yumshatilgan shartni JIM qoldirish mumkin emas — agent natijani
    # so'raganiga to'liq mos deb o'ylab qolardi.
    if dropped:
        relaxed = ", ".join(_RELAXED_LABELS.get(d, d) for d in sorted(dropped))
        lines.append(f"⚠️ Aynan mos topilmadi — {relaxed} sharti olib tashlandi.")
    lines.append("")

    groups = group_by_hotel(offers)
    for group in groups[:5]:
        best = group[0]
        star = f"{best.star}*" if best.star else ""
        head = " ".join(p for p in (best.hotel_name, star, best.board) if p)
        lines.append(f"🏨 <b>{head}</b>")

        for offer in group[:3]:
            # Minglik ajratgichni almashtirish HAR DOIM faqat raqamga
            # qo'llanadi — butun satrga qo'llansa matndagi vergullar ham
            # yo'qoladi.
            price = f"{offer.price_gross:,.0f}".replace(",", " ")
            source = offer.operator_name or "price-list"
            margin = ""
            if offer.agent_margin:
                margin = f" · foyda {offer.agent_margin:,.0f}".replace(",", " ")
            lines.append(f"   {price} {offer.currency} — {source}{margin}")

        # Bir mehmonxona bir necha operatorda bo'lsa — tejash ko'rsatiladi.
        if len(group) > 1 and group[0].price_gross and group[-1].price_gross:
            diff = group[-1].price_gross - group[0].price_gross
            if diff > 0:
                # `replace` FAQAT raqamga — butun satrga qo'llansa
                # "bor, farq" dagi vergul ham yo'qolardi.
                pretty = f"{diff:,.0f}".replace(",", " ")
                lines.append(
                    f"   💡 {len(group)} operatorda bor, "
                    f"farq {pretty} {group[0].currency}"
                )
        lines.append("")

    if len(groups) > 5:
        lines.append(f"… va yana {len(groups) - 5} ta variant")
    lines.append("To'liq ro'yxat: panel → <b>Narxlar</b>")

    return _reply("\n".join(lines), actions=["open_prices"])


async def _handle_no_pending(db: AsyncSession, cid: int, message: str) -> dict:
    intent, conf = _store().predict(message)

    if intent == "greeting":
        return _reply("Salom! Men Tella AI, firmangiz yordamchisiman. Masalan: 'nechta tur bor' yoki 'yangi tur qosh'.")
    if intent == "help":
        return _reply(_HELP)
    if intent == "unknown":
        # Firma ishiga aloqasiz savol — qatʼiy rad javobi.
        return _reply(_OFFTOPIC)

    # Oʻqish intentlari — javob berilgach ishonchli boʻlsa oʻrganamiz.
    if intent == "report":
        reply = await _run_report(db, cid)
        if conf >= _LEARN_CONF:
            await _store().learn(db, cid, message, intent)
        return _reply(reply)
    if intent in ("count_tours", "list_tours", "count_customers", "list_customers",
                  "recent_bookings", "get_plan", "instagram_leads"):
        reply = await _run_read_intent(db, cid, intent)
        if conf >= _LEARN_CONF:
            await _store().learn(db, cid, message, intent)
        return _reply(reply)

    # Operatorlardan qidirish — shartlarni matndan ajratib, tasdiqqa qo'yamiz.
    # Qidiruvning o'zi konnektor qatlamida, fon jarayonida ketadi.
    if intent == SEARCH_INTENT:
        if conf >= _LEARN_CONF:
            await _store().learn(db, cid, message, intent)
        return await _start_tour_search(db, cid, message)

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

    if intent == "update_tour":
        slots = {"_trigger": message}
        field = _detect_tour_field(message)
        if field:
            slots["field"] = field
        await _resolve_and_store(db, cid, slots, message)
        return _advance_update_tour(slots)

    if intent == "create_customer":
        slots = {"_trigger": message}
        _extract_customer_slots(message, slots)
        # Tur nomini buyruq soʻzlarisiz qidiramiz, aks holda "mijoz qosh"
        # dagi "qosh" tasodifan tur nomiga mos kelib qolishi mumkin.
        ref = _strip_cmd_words(message)
        if ref:
            await _resolve_and_store(db, cid, slots, ref)
        return _advance_create_customer(slots)

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


async def _handle_pending(db: AsyncSession, user: User, message: str, pending: dict) -> dict:
    cid = user.company_id
    intent = pending.get("intent")
    slots = dict(pending.get("slots") or {})
    stage = pending.get("stage")
    awaiting = pending.get("awaiting")

    # Sana soralganda "yoq" — bu suhbatni bekor qilish emas, "sana hali
    # nomaʼlum" degani. Shuning uchun umumiy bekor tekshiruvidan OLDIN turadi.
    if intent == "create_tour" and stage == "collect" and awaiting == "start_date" and is_deny(message):
        slots["start_date"] = _NO_DATE
        return _advance_create(slots)

    # Qidiruv shartlarini to'ldirish. Yangi xabar avvalgi so'rov ustiga
    # qo'shiladi — agent "Antalya" deb javob bersa oldingi shartlar
    # (kecha, kishi, byudjet) saqlanib qoladi.
    if intent == SEARCH_INTENT and not is_deny(message):
        previous = pending.get("query") or {}
        return await _start_tour_search(
            db, cid, f"{previous.get('raw_text', '')} {message}".strip()
        )

    if is_deny(message):
        return _reply("Bekor qilindi.")

    if stage == "confirm":
        if is_affirm(message):
            return await _execute(db, user, intent, slots)
        # Tasdiq emas — qayta soraymiz.
        if intent == "create_tour":
            return _reply(_create_summary(slots), pending={"intent": intent, "slots": slots, "stage": "confirm"})
        if intent == "create_customer":
            return _reply(_customer_summary(slots), pending={"intent": intent, "slots": slots, "stage": "confirm"})
        return _reply("Tasdiqlash uchun 'ha', bekor uchun 'yoq' deng.",
                      pending={"intent": intent, "slots": slots, "stage": "confirm"})

    # stage == collect: kutilayotgan maydonni toʻldiramiz
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
        elif awaiting == "start_date":
            d = parse_date(message)
            if d:
                slots["start_date"] = d
            else:
                return _reply(
                    "Sanani tushunmadim. Masalan: 2026-08-15 yoki 15.08.2026. "
                    "Sana hali nomaʼlum bolsa 'yoq' deng.",
                    pending={"intent": intent, "slots": slots,
                             "stage": "collect", "awaiting": "start_date"},
                )
        elif awaiting in ("title", "city"):
            slots[awaiting] = message.strip()
        # Qolgan maydonlarni ham matndan qidiramiz, lekin sanani emas —
        # u faqat oz bosqichida yuqorida ajratiladi.
        _extract_create_slots(message, slots, with_date=False)
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

    if intent == "update_tour":
        if awaiting == "tour_ref":
            if not await _resolve_and_store(db, cid, slots, message):
                return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.",
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
        elif awaiting == "field":
            field = _detect_tour_field(message)
            if not field:
                return _reply(
                    "Tushunmadim. Quyidagilardan birini yozing: "
                    "nomi / shahri / narxi / muddati / joylar soni / sanasi",
                    pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "field"},
                )
            slots["field"] = field
        elif awaiting == "value":
            v = _parse_tour_value(slots.get("field", ""), message)
            if v is None:
                prompt = next((p for f, _, p in _TOUR_FIELDS if f == slots.get("field")),
                              "Yangi qiymatni yozing")
                return _reply(f"Qiymatni tushunmadim. {prompt}",
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "value"})
            slots["value"] = v
        return _advance_update_tour(slots)

    if intent == "create_customer":
        if awaiting == "tour_ref":
            if not await _resolve_and_store(db, cid, slots, message):
                # Mavjud turlarni sanab beramiz — aks holda foydalanuvchi
                # "topilmadi" xabarini qayta-qayta olib, ilinib qolardi.
                return _reply(await _tour_not_found_hint(db, cid),
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "tour_ref"})
        elif awaiting == "full_name":
            # Telefon/email bir xabarda kelsa ism ichida qolib ketmasin.
            slots["full_name"] = _strip_contacts(message) or message.strip()
        elif awaiting == "phone":
            ph = parse_phone(message)
            if not ph:
                return _reply("Telefon raqamini tushunmadim. Masalan: +998901234567",
                              pending={"intent": intent, "slots": slots, "stage": "collect", "awaiting": "phone"})
            slots["phone"] = ph
        elif awaiting == "guests_count":
            v = parse_int_near(message, "kishi", "odam", "nafar") or parse_bare_int(message)
            if v:
                slots["guests_count"] = v
        # Qolgan maydonlarni ham shu xabardan qidiramiz (bor qiymatga tegmaydi).
        _extract_customer_slots(message, slots)
        return _advance_create_customer(slots)

    return _reply(_HELP)


def _is_missing_date_error(exc: Exception) -> bool:
    """Baza sanani majburiy deb rad etdimi?"""
    low = str(exc).lower()
    return ("not null" in low or "notnullviolation" in low) and (
        "start_date" in low or "end_date" in low
    )


def _friendly_error(exc: Exception) -> str:
    """Texnik xatoni foydalanuvchi tushunadigan (va tuzata oladigan) matnga aylantiradi.

    Oldin hamma xato uchun bitta umumiy jumla qaytardik — admin nima notogri
    ketganini bilolmasdi. Endi eng koʻp uchraydigan sabablar ajratiladi.
    """
    low = str(exc).lower()
    if "not null" in low or "notnullviolation" in low:
        if "start_date" in low or "end_date" in low:
            return ("Bazada tur sanasi majburiy ekan. Qaytadan 'tur qosh' deng va "
                    "boshlanish sanasini korsating (masalan: 2026-08-15).")
        return ("Bazada bir maydon majburiy, lekin toldirilmadi. "
                "Malumotlarni toliq kiritib, qaytadan urinib koring.")
    if "unique" in low or "duplicate" in low:
        return "Bunday yozuv allaqachon mavjud."
    if "foreign key" in low:
        return "Bogliq yozuv topilmadi (masalan filial). Sozlamalarni tekshiring."
    return "Amalni bajarishda xatolik boldi. Qaytadan urinib koring."


async def _execute(db: AsyncSession, user: User, intent: str, slots: dict) -> dict:
    try:
        if intent == "create_tour":
            res = await _do_create(db, user, slots)
        elif intent == "update_price":
            res = await _do_update_price(db, user.company_id, slots)
        elif intent == "set_active":
            res = await _do_set_active(db, user.company_id, slots)
        elif intent == "update_tour":
            res = await _do_update_tour(db, user, slots)
        elif intent == "create_customer":
            res = await _do_create_customer(db, user, slots)
        else:
            return _reply("Tushunmadim.")
    except Exception as exc:  # noqa: BLE001 — amal xatosi suhbatni buzmasin
        logger.exception("ML assistant amal xatosi: %s", intent)
        await db.rollback()
        # Sana majburiy ekan — foydalanuvchini boshiga qaytarmaymiz, shu
        # yerda sanani sorab, yigilgan malumot ustidan davom etamiz.
        if intent == "create_tour" and _is_missing_date_error(exc):
            retry = dict(slots)
            retry.pop("start_date", None)
            return _reply(
                "Bazada tur sanasi majburiy ekan. Boshlanish sanasini yozing "
                "(masalan: 2026-08-15) — qolgan malumotlar saqlanib turibdi.",
                pending={"intent": "create_tour", "slots": retry,
                         "stage": "collect", "awaiting": "start_date"},
            )
        return _reply(_friendly_error(exc))
    # Amal muvaffaqiyatli bajarildi — asl buyruqni oʻrganamiz (tasdiqlangan misol).
    if res.get("actions"):
        await _store().learn(db, user.company_id, str(slots.get("_trigger", "")), intent)
    return res


async def _do_create(db: AsyncSession, user: User, slots: dict) -> dict:
    """Turni qoshadi — qolda forma bilan bir xil TourService yoʻlidan.

    Shu tufayli end_date, branch va tarif tekshiruvi qolda yaratish bilan
    aynan bir xil ishlaydi (productionда ham).
    """
    try:
        price = float(slots["price"])
        duration = int(slots["duration_days"])
        seats = int(slots["available_slots"])
    except (KeyError, TypeError, ValueError):
        return _reply("Malumot toliq emas, qaytadan boshlaymiz. 'tur qosh' deng.")
    if price <= 0 or duration < 1 or seats < 1:
        return _reply("Narx musbat, kun va joylar kamida 1 boʻlishi kerak.")

    start_date: Optional[date] = None
    raw_date = slots.get("start_date")
    if raw_date and raw_date != _NO_DATE:
        try:
            start_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            start_date = None
    # Sana berilgan boʻlsa tugash sanasini muddatdan hisoblaymiz.
    end_date = start_date + timedelta(days=duration) if start_date else None

    title = str(slots.get("title") or f"{slots.get('city', 'Yangi')} sayohati").strip()
    city = str(slots.get("city") or title).strip()
    description = f"{title} — {city}. {duration} kunlik tur paketi."

    try:
        data = TourCreate(
            title=title, description=description, city=city, country="Uzbekistan",
            price=price, currency="UZS", duration_days=duration,
            start_date=start_date, end_date=end_date, available_slots=seats,
            booking_type="group", branch_id=None,
        )
    except ValidationError:
        return _reply("Malumot notogri (masalan tur nomi juda qisqa). Qaytadan 'tur qosh' deng.")

    try:
        result = await TourService(db).create_tour(user, data)
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        return _reply(str(exc.detail))

    return _reply(f"Tayyor! '{result.title}' turi qoshildi (#{result.id}).",
                  actions=[f"Tur qoshildi: {result.title}"])


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


async def _do_update_tour(db: AsyncSession, user: User, slots: dict) -> dict:
    """Turning bitta maydonini yangilaydi — qolda tahrirlash bilan bir xil yoʻldan."""
    tour = await _resolve_tour(db, user.company_id, str(slots.get("tour_id") or ""))
    if not tour:
        return _reply("Bunday tur topilmadi. Nomini yoki id sini aniq yozing.")

    field = slots.get("field")
    value = slots.get("value")
    if not field or value in (None, ""):
        return _reply("Malumot toliq emas, qaytadan boshlaymiz. 'turni tahrirla' deng.")

    payload: dict[str, Any] = {}
    if field == "start_date":
        try:
            sd = datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return _reply("Sanani tushunmadim. Masalan: 2026-08-15")
        payload["start_date"] = sd
        # Tugash sanasi turning muddatidan qayta hisoblanadi, aks holda eski
        # end_date yangi boshlanishdan oldin qolib ketardi.
        if tour.duration_days:
            payload["end_date"] = sd + timedelta(days=tour.duration_days)
    elif field == "price":
        price = float(value)
        if price <= 0:
            return _reply("Narx musbat boʻlishi kerak.")
        payload["price"] = price
    elif field in ("duration_days", "available_slots"):
        n = int(value)
        if n < 1:
            return _reply("Qiymat kamida 1 boʻlishi kerak.")
        payload[field] = n
        # Muddat oʻzgarsa, sanasi bor turda tugash sanasi ham suriladi.
        if field == "duration_days" and tour.start_date:
            payload["end_date"] = tour.start_date + timedelta(days=n)
    else:
        text = str(value).strip()
        if len(text) < 2:
            return _reply("Qiymat juda qisqa.")
        payload[field] = text

    try:
        data = TourUpdate(**payload)
    except ValidationError:
        return _reply("Yangi qiymat notogri. Qaytadan urinib koring.")

    # Nom oʻzgarganda xabarda ESKI nomni koʻrsatamiz, aks holda
    # "'Dubay VIP' turining nomi Dubay VIP ga ozgartirildi" degan gap chiqadi.
    old_title = tour.title
    try:
        result = await TourService(db).update_tour(user, tour.id, data)
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        return _reply(str(exc.detail))

    label = _FIELD_LABEL.get(field, field)
    shown = _format_tour_value(field, value)
    return _reply(f"Tayyor! '{old_title}' turining {label} {shown} ga ozgartirildi.",
                  actions=[f"{result.title}: {label} yangilandi"])


async def _do_create_customer(db: AsyncSession, user: User, slots: dict) -> dict:
    """Mijozni qoshadi va uni tanlangan turga bron qiladi (CRM bilan bir xil yoʻl)."""
    name = str(slots.get("full_name") or "").strip()
    phone = str(slots.get("phone") or "").strip()
    tour_id = slots.get("tour_id")
    if not (name and phone and tour_id):
        return _reply("Malumot toliq emas, qaytadan boshlaymiz. 'mijoz qosh' deng.")

    try:
        guests = int(slots.get("guests_count") or 1)
    except (TypeError, ValueError):
        guests = 1
    if guests < 1:
        return _reply("Kishilar soni kamida 1 boʻlishi kerak.")

    # Email majburiy maydon, lekin tur firmalarida mijozda koʻpincha email
    # boʻlmaydi — telefondan barqaror va takrorlanmas manzil yasaymiz.
    email = str(slots.get("email") or "").strip()
    if not email:
        email = f"{re.sub(r'[^0-9]', '', phone)}@mijoz.local"

    try:
        data = CustomerCreateRequest(
            full_name=name, phone=phone, email=email,
            tour_id=int(tour_id), guests_count=guests, notes=None,
        )
    except ValidationError:
        return _reply("Malumot notogri. Qaytadan 'mijoz qosh' deng.")

    try:
        result = await CRMService(db).create_customer(user, data)
    except HTTPException as exc:
        await db.rollback()
        return _reply(str(exc.detail))

    tour_title = slots.get("tour_title") or "tur"
    return _reply(
        f"Tayyor! Mijoz '{result.full_name}' qoshildi va '{tour_title}' turiga "
        f"{guests} kishi uchun bron qilindi.",
        actions=[f"Mijoz qoshildi: {result.full_name}"],
    )


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
        return await _handle_pending(db, user, message, pending)
    return await _handle_no_pending(db, cid, message)
