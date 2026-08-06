"""Tur paketlar kategoriyasi — yagona ma'lumotnoma.

Nima uchun kerak
----------------
18 ta operator bir narsani 18 xil ataydi: kimdir "AI", kimdir "все включено",
kimdir "hammasi kiritilgan". Kimdir "Анталия", kimdir "Antalya", kimdir
"ANTALYA/KEMER". Taqqoslash uchun ularning hammasi BITTA kanonik qiymatga
keltirilishi shart — aks holda "eng arzoni" ni topib bo'lmaydi.

Bu modul o'sha ma'lumotnoma: kanonik kod + har til/yozuvdagi taxalluslar.

Bozor ma'lumoti
---------------
Ro'yxat va tartib O'zbekiston chiqish turizmining haqiqiy raqamlariga
asoslangan (2025 yil to'liq va 2026 yil boshi):

  * Saudiya Arabistoni — 2026 yanvar-aprelda 1-o'rin (138 113 kishi).
    Bu **umra/haj**, oddiy dam olish emas. Shuning uchun `UMRA` va `HAJ`
    alohida kategoriya — universal taksonomiyalarda bu bo'lmaydi, lekin
    O'zbekiston bozorida eng katta segment.
  * Rossiya — 115 094
  * Turkiya — 2025 da 268 900 (eng ko'p), 2026 boshida 70 340
  * BAA — 2025 da 139 400, 2026 boshida 31 073
  * Misr — 2025 da 65 400, 2026 boshida 20% pasaygan

Manbalar: kun.uz, daryo.uz, travelandtourworld.com (2026 yanvar-may).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


# ==========================================================================
# Ovqatlanish turi (board)
# ==========================================================================
class Board(StrEnum):
    """Ovqatlanish. Narxga eng ko'p ta'sir qiladigan omil."""

    RO = "RO"    # faqat yashash
    BB = "BB"    # nonushta
    HB = "HB"    # 2 mahal
    HBP = "HB+"  # 2 mahal + mahalliy ichimlik
    FB = "FB"    # 3 mahal
    FBP = "FB+"
    AI = "AI"    # hammasi kiritilgan
    UAI = "UAI"  # ultra hammasi kiritilgan


BOARD_ALIASES: dict[Board, tuple[str, ...]] = {
    Board.UAI: (
        "uai", "ultra all inclusive", "ultra ai", "ultra hammasi kiritilgan",
        "ультра все включено", "ультра всё включено", "ultra all",
    ),
    Board.AI: (
        "ai", "all inclusive", "all-inclusive", "hammasi kiritilgan",
        "hammasi kirgan", "все включено", "всё включено", "vse vklyucheno",
    ),
    Board.FBP: ("fb+", "fb plus", "full board plus", "полный пансион плюс"),
    Board.FB: (
        "fb", "full board", "3 mahal", "uch mahal", "3 maxal",
        "полный пансион", "трехразовое питание", "3-х разовое",
    ),
    Board.HBP: ("hb+", "hb plus", "half board plus", "полупансион плюс"),
    Board.HB: (
        "hb", "half board", "2 mahal", "ikki mahal", "2 maxal",
        "полупансион", "полу-пансион", "двухразовое питание",
    ),
    Board.BB: (
        "bb", "bed and breakfast", "bed & breakfast", "nonushta",
        "faqat nonushta", "завтрак", "только завтрак", "zavtrak",
    ),
    Board.RO: (
        "ro", "room only", "ao", "bo", "ep", "faqat yashash", "ovqatsiz",
        "без питания", "только проживание",
    ),
}

BOARD_LABELS: dict[Board, str] = {
    Board.RO: "Faqat yashash",
    Board.BB: "Nonushta",
    Board.HB: "2 mahal",
    Board.HBP: "2 mahal +",
    Board.FB: "3 mahal",
    Board.FBP: "3 mahal +",
    Board.AI: "All Inclusive",
    Board.UAI: "Ultra All Inclusive",
}


# ==========================================================================
# Tur toifasi
# ==========================================================================
class TourCategory(StrEnum):
    """Sayohat maqsadi. Narx mantiqini butunlay o'zgartiradi."""

    BEACH = "plyaj"
    UMRA = "umra"
    HAJ = "haj"
    EXCURSION = "ekskursiya"
    MEDICAL = "davolanish"
    SKI = "changi"
    SHOPPING = "shop"
    HONEYMOON = "asal_oyi"
    BUSINESS = "biznes"
    EDUCATION = "talim"
    CRUISE = "kruiz"


CATEGORY_ALIASES: dict[TourCategory, tuple[str, ...]] = {
    TourCategory.UMRA: ("umra", "umrah", "умра", "умрах", "ziyorat", "зиёрат", "ziyarat"),
    TourCategory.HAJ: ("haj", "hajj", "хадж", "хаж"),
    TourCategory.BEACH: (
        "plyaj", "plaj", "dengiz", "пляж", "пляжный", "beach", "dam olish",
        "otdix", "отдых",
    ),
    TourCategory.EXCURSION: (
        "ekskursiya", "экскурсия", "экскурсионный", "excursion", "sayohat",
        "sightseeing", "tur",
    ),
    TourCategory.MEDICAL: (
        "davolanish", "лечение", "лечебный", "санаторий", "sanatoriy",
        "medical", "termal", "термальный",
    ),
    TourCategory.SKI: (
        "changi", "chang'i", "горнолыжный", "лыжи", "ski", "snowboard",
        "gornolyzhnyy",
    ),
    TourCategory.SHOPPING: ("shop", "shopping", "шоп", "шоп-тур", "xarid"),
    TourCategory.HONEYMOON: (
        "asal oyi", "asal_oyi", "медовый месяц", "honeymoon", "свадебное",
        "kelin kuyov",
    ),
    TourCategory.BUSINESS: ("biznes", "бизнес", "деловой", "business", "konferensiya"),
    TourCategory.EDUCATION: ("talim", "ta'lim", "образовательный", "education", "oquv"),
    TourCategory.CRUISE: ("kruiz", "круиз", "cruise", "layner"),
}

CATEGORY_LABELS: dict[TourCategory, str] = {
    TourCategory.BEACH: "Plyaj / dam olish",
    TourCategory.UMRA: "Umra",
    TourCategory.HAJ: "Haj",
    TourCategory.EXCURSION: "Ekskursiya",
    TourCategory.MEDICAL: "Davolanish",
    TourCategory.SKI: "Chang'i",
    TourCategory.SHOPPING: "Shop-tur",
    TourCategory.HONEYMOON: "Asal oyi",
    TourCategory.BUSINESS: "Biznes",
    TourCategory.EDUCATION: "Ta'lim",
    TourCategory.CRUISE: "Kruiz",
}


# ==========================================================================
# Davlat va kurort
# ==========================================================================
@dataclass(frozen=True)
class Destination:
    """Yo'nalish — davlat yoki uning ichidagi kurort."""

    code: str
    name_uz: str
    country_code: str          # o'zi davlat bo'lsa `code` bilan bir xil
    aliases: tuple[str, ...] = ()
    # O'zbekiston bozoridagi ommaboplik (1 = eng ko'p). Standart tartiblash
    # va "mashhur yo'nalishlar" ro'yxati uchun.
    rank: int = 999
    categories: tuple[TourCategory, ...] = ()
    visa_free: bool | None = None

    @property
    def is_country(self) -> bool:
        return self.code == self.country_code


def _c(code, name_uz, *aliases, rank=999, categories=(), visa_free=None) -> Destination:
    """Davlat."""
    return Destination(code, name_uz, code, tuple(aliases), rank, tuple(categories), visa_free)


def _r(code, name_uz, country, *aliases, rank=999, categories=()) -> Destination:
    """Kurort/shahar."""
    return Destination(code, name_uz, country, tuple(aliases), rank, tuple(categories))


_B, _E, _U, _H, _M, _S, _K = (
    TourCategory.BEACH, TourCategory.EXCURSION, TourCategory.UMRA,
    TourCategory.HAJ, TourCategory.MEDICAL, TourCategory.SKI,
    TourCategory.SHOPPING,
)

COUNTRIES: tuple[Destination, ...] = (
    _c("SA", "Saudiya Arabistoni", "saudi", "saudiya", "саудовская аравия",
       "саудия", "ksa", rank=1, categories=(_U, _H)),
    _c("RU", "Rossiya", "russia", "россия", "рф", rank=2, categories=(_E, _M, _S)),
    _c("TR", "Turkiya", "turkey", "turkiye", "турция", "туркия", rank=3,
       categories=(_B, _E, _M, _S, _K), visa_free=True),
    _c("AE", "BAA", "uae", "emirates", "оаэ", "эмираты", "birlashgan arab amirliklari",
       rank=4, categories=(_B, _E, _K), visa_free=True),
    _c("EG", "Misr", "egypt", "египет", "misr", rank=5, categories=(_B, _E)),
    _c("KZ", "Qozogiston", "kazakhstan", "казахстан", "qozoq", rank=6,
       categories=(_E, _S, _M), visa_free=True),
    _c("KG", "Qirgiziston", "kyrgyzstan", "киргизия", "кыргызстан", rank=7,
       categories=(_B, _E, _S), visa_free=True),
    _c("CN", "Xitoy", "china", "китай", "xitoy", rank=8, categories=(_E, _K)),
    _c("TH", "Tailand", "thailand", "таиланд", "тайланд", rank=9, categories=(_B, _E)),
    _c("GE", "Gruziya", "georgia", "грузия", rank=10, categories=(_B, _E, _S),
       visa_free=True),
    _c("AZ", "Ozarbayjon", "azerbaijan", "азербайджан", "ozarbayjon", rank=11,
       categories=(_E, _M), visa_free=True),
    _c("TJ", "Tojikiston", "tajikistan", "таджикистан", rank=12, categories=(_E,),
       visa_free=True),
    _c("VN", "Vetnam", "vietnam", "вьетнам", rank=13, categories=(_B, _E)),
    _c("MV", "Maldiv", "maldives", "мальдивы", "maldiv orollari", rank=14,
       categories=(_B,)),
    _c("MY", "Malayziya", "malaysia", "малайзия", rank=15, categories=(_B, _E)),
    _c("ID", "Indoneziya", "indonesia", "индонезия", "bali", rank=16, categories=(_B,)),
    _c("LK", "Shri-Lanka", "sri lanka", "шри-ланка", "шри ланка", rank=17,
       categories=(_B, _E)),
    _c("IN", "Hindiston", "india", "индия", rank=18, categories=(_E, _M)),
    _c("QA", "Qatar", "катар", rank=19, categories=(_E, _K)),
    _c("AM", "Armaniston", "armenia", "армения", rank=20, categories=(_E,)),
    _c("TM", "Turkmaniston", "turkmenistan", "туркменистан", rank=21, categories=(_E,)),
    _c("JP", "Yaponiya", "japan", "япония", rank=22, categories=(_E,)),
    _c("KR", "Janubiy Koreya", "korea", "корея", "южная корея", rank=23,
       categories=(_E, _M)),
    _c("EU", "Yevropa", "europe", "европа", "shengen", "шенген", "schengen",
       rank=24, categories=(_E,)),
)

RESORTS: tuple[Destination, ...] = (
    # Turkiya
    _r("TR-AYT", "Antalya", "TR", "анталия", "анталья", "antaliya", rank=1, categories=(_B,)),
    _r("TR-KMR", "Kemer", "TR", "кемер", rank=2, categories=(_B,)),
    _r("TR-BLK", "Belek", "TR", "белек", rank=3, categories=(_B,)),
    _r("TR-SID", "Side", "TR", "сиде", rank=4, categories=(_B,)),
    _r("TR-ALA", "Alanya", "TR", "аланья", "алания", rank=5, categories=(_B,)),
    _r("TR-BJM", "Bodrum", "TR", "бодрум", rank=6, categories=(_B,)),
    _r("TR-MRM", "Marmaris", "TR", "мармарис", rank=7, categories=(_B,)),
    _r("TR-FET", "Fethiye", "TR", "фетхие", "фethiye", rank=8, categories=(_B,)),
    _r("TR-KUS", "Kushadasi", "TR", "кушадасы", "kusadasi", rank=9, categories=(_B,)),
    _r("TR-IST", "Istanbul", "TR", "стамбул", "istambul", rank=10, categories=(_E, _K)),
    _r("TR-TZX", "Trabzon", "TR", "трабзон", rank=11, categories=(_E,)),
    # BAA
    _r("AE-DXB", "Dubay", "AE", "dubai", "дубай", rank=1, categories=(_B, _K)),
    _r("AE-AUH", "Abu-Dabi", "AE", "abu dhabi", "абу-даби", "абу даби", rank=2,
       categories=(_B, _E)),
    _r("AE-SHJ", "Sharja", "AE", "sharjah", "шарджа", rank=3, categories=(_B,)),
    _r("AE-RKT", "Ras al-Xayma", "AE", "ras al khaimah", "рас-эль-хайма", rank=4,
       categories=(_B,)),
    _r("AE-FJR", "Fujayra", "AE", "fujairah", "фуджейра", rank=5, categories=(_B,)),
    _r("AE-AJM", "Ajman", "AE", "аджман", rank=6, categories=(_B,)),
    # Misr
    _r("EG-SSH", "Sharm ash-Shayx", "EG", "sharm el sheikh", "шарм-эль-шейх",
       "шарм", "sharm", rank=1, categories=(_B,)),
    _r("EG-HRG", "Hurgada", "EG", "hurghada", "хургада", rank=2, categories=(_B,)),
    _r("EG-RMF", "Marsa Alam", "EG", "марса алам", rank=3, categories=(_B,)),
    _r("EG-CAI", "Qohira", "EG", "cairo", "каир", rank=4, categories=(_E,)),
    # Saudiya
    _r("SA-MKK", "Makka", "SA", "mecca", "makkah", "мекка", rank=1, categories=(_U, _H)),
    _r("SA-MED", "Madina", "SA", "medina", "madinah", "медина", rank=2, categories=(_U, _H)),
    _r("SA-JED", "Jidda", "SA", "jeddah", "джидда", rank=3, categories=(_U,)),
    # Tailand
    _r("TH-HKT", "Puket", "TH", "phuket", "пхукет", rank=1, categories=(_B,)),
    _r("TH-PYX", "Pattayya", "TH", "pattaya", "паттайя", rank=2, categories=(_B,)),
    _r("TH-BKK", "Bangkok", "TH", "бангкок", rank=3, categories=(_E, _K)),
    _r("TH-USM", "Samui", "TH", "самуи", "koh samui", rank=4, categories=(_B,)),
    _r("TH-KBV", "Krabi", "TH", "краби", rank=5, categories=(_B,)),
    # Gruziya
    _r("GE-BUS", "Batumi", "GE", "батуми", rank=1, categories=(_B,)),
    _r("GE-TBS", "Tbilisi", "GE", "тбилиси", rank=2, categories=(_E,)),
    _r("GE-GDR", "Gudauri", "GE", "гудаури", rank=3, categories=(_S,)),
    _r("GE-BKR", "Bakuriani", "GE", "бакуриани", rank=4, categories=(_S,)),
    # Boshqalar
    _r("VN-NHA", "Nyachang", "VN", "nha trang", "нячанг", rank=1, categories=(_B,)),
    _r("VN-PQC", "Fukuok", "VN", "phu quoc", "фукуок", rank=2, categories=(_B,)),
    _r("ID-DPS", "Bali", "ID", "бали", "denpasar", rank=1, categories=(_B,)),
    _r("MY-KUL", "Kuala-Lumpur", "MY", "kuala lumpur", "куала-лумпур", rank=1,
       categories=(_E, _K)),
    _r("MY-LGK", "Langkavi", "MY", "langkawi", "лангкави", rank=2, categories=(_B,)),
    _r("KG-IKL", "Issiqko'l", "KG", "issyk kul", "иссык-куль", "issiqkol", rank=1,
       categories=(_B,)),
    _r("KZ-ALA", "Almati", "KZ", "almaty", "алматы", rank=1, categories=(_E, _S, _K)),
    _r("AZ-BAK", "Boku", "AZ", "baku", "баку", rank=1, categories=(_E,)),
    _r("AE-DXB2", "Dubai Marina", "AE", "марина", rank=90, categories=(_B,)),
)

ALL_DESTINATIONS: tuple[Destination, ...] = COUNTRIES + RESORTS


# ==========================================================================
# Yulduz
# ==========================================================================
STAR_VALUES = ("2", "3", "4", "5")

STAR_ALIASES: dict[str, tuple[str, ...]] = {
    "5": ("5*", "5 *", "5 yulduz", "5 star", "5 звезд", "5 звёзд", "five star",
          "beshyulduz"),
    "4": ("4*", "4 *", "4 yulduz", "4 star", "4 звезды", "4 звезд", "four star"),
    "3": ("3*", "3 *", "3 yulduz", "3 star", "3 звезды", "3 звезд", "three star"),
    "2": ("2*", "2 *", "2 yulduz", "2 star", "2 звезды", "two star"),
}


# ==========================================================================
# Valyuta
# ==========================================================================
CURRENCY_ALIASES: dict[str, tuple[str, ...]] = {
    "USD": ("usd", "$", "dollar", "доллар", "долл"),
    "UZS": ("uzs", "so'm", "som", "sum", "сум", "сўм"),
    "EUR": ("eur", "€", "evro", "euro", "евро"),
    "RUB": ("rub", "₽", "rubl", "рубль", "руб"),
}


# ==========================================================================
# Matn moslashtirish
# ==========================================================================
def normalize(text: str) -> str:
    """Taqqoslash uchun matnni soddalashtiradi.

    Operatorlar bir so'zni turlicha yozadi: "Anta­lya", "ANTALYA", "Анталия",
    "Antal'ya". Bularning hammasi bir xil ko'rinishga keltiriladi.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    # O'zbek apostroflari va tirelar
    text = text.replace("ʻ", "'").replace("ʼ", "'").replace("`", "'")
    text = re.sub(r"[''‛]", "'", text)
    text = re.sub(r"[-–—_/\\]+", " ", text)
    # `*`, `+` va valyuta belgilari SAQLANADI — ular ma'no tashiydi:
    # "5*" (yulduz), "HB+" (ovqat), "$500" (valyuta). Ilgari `$`, `€`, `₽`
    # o'chib ketardi va `CURRENCY_ALIASES` dagi belgi-taxalluslar hech qachon
    # ishlamasdi.
    text = re.sub(r"[^\w\s'*+&$€₽]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(normalize(text).split())


@dataclass
class TaxonomyMatch:
    """Matndan topilgan kategoriyalar."""

    destinations: list[Destination] = field(default_factory=list)
    board: Board | None = None
    category: TourCategory | None = None
    star: str | None = None
    currency: str | None = None
    # Matnda to'g'ridan-to'g'ri yozilmagan, mantiqan xulosa qilingan
    # maydonlar (masalan "umra" -> Saudiya). UI'da ularni tasdiqlatish
    # mumkin bo'lsin deb alohida belgilanadi.
    inferred: set[str] = field(default_factory=set)

    @property
    def country_codes(self) -> list[str]:
        seen, out = set(), []
        for d in self.destinations:
            if d.country_code not in seen:
                seen.add(d.country_code)
                out.append(d.country_code)
        return out


# Shundan uzun taxalluslarga qo'shimcha yopishishi mumkin. Qisqalari
# (ai, hb, ro, 5*, $) qat'iy chegara talab qiladi — aks holda "ai" so'zi
# "aeroport" ichidan topilib ketardi.
_SUFFIXABLE_MIN_LEN = 4
# Ildizga tushirish uchun minimal uzunlik: "грузия"(6) -> "грузи"(5).
_STEMMABLE_MIN_LEN = 6
_VOWELS = set("aeiouаяуюоыэеёи")


def _alias_pattern(alias_n: str) -> str:
    """Taxallusdan qidiruv naqshini yasaydi.

    Uchta til uchligi ishlashi kerak, har biri boshqacha buziladi:

    * **O'zbek** — qo'shimcha so'zga yopishadi, o'zak o'zgarmaydi:
      "Antalya**ga**", "500 dollar**gacha**", "Turkiya**da**".
      Yechim: o'ngdagi chegarani ochiq qoldirish.

    * **Rus** — so'z **oxiri almashadi**, qo'shimcha qo'shilmaydi:
      "Грузи**я**" -> "Грузи**ю**" -> "Грузи**и**". Ochiq chegara buni
      topmaydi, chunki "грузия" degan ketma-ketlik matnda umuman yo'q.
      Yechim: oxirgi unlini kesib, ildiz bo'yicha qidirish.

    * **Qisqa kodlar** — "ai", "hb", "5*" qat'iy chegarada qolishi shart.
    """
    # Sof ramz ("$", "€", "₽") — so'z chegarasi ma'nosiz va ZARARLI:
    # `(?!\w)` "$500" dagi "$" dan keyin raqam turgani uchun rad etardi.
    if not re.search(r"\w", alias_n):
        return re.escape(alias_n)
    if len(alias_n) >= _STEMMABLE_MIN_LEN and alias_n[-1] in _VOWELS:
        return r"(?<!\w)" + re.escape(alias_n[:-1]) + r"\w*"
    if len(alias_n) >= _SUFFIXABLE_MIN_LEN:
        return r"(?<!\w)" + re.escape(alias_n)
    return r"(?<!\w)" + re.escape(alias_n) + r"(?!\w)"


def _alias_hit(haystack: str, alias: str) -> bool:
    """Taxallus matnda uchraydimi.

    `re.escape` shart: taxalluslarda `*`, `+`, `$` bor ("5*", "HB+", "$").
    Ularsiz naqsh buzilardi yoki noto'g'ri joyga tushardi.
    """
    alias_n = normalize(alias)
    if not alias_n:
        return False
    return re.search(_alias_pattern(alias_n), haystack) is not None


def match_board(text: str) -> Board | None:
    """Ovqatlanish turini topadi. Aniqrog'i ustun (UAI > AI, HB+ > HB)."""
    h = normalize(text)
    for board in (Board.UAI, Board.AI, Board.FBP, Board.FB, Board.HBP,
                  Board.HB, Board.BB, Board.RO):
        if any(_alias_hit(h, a) for a in BOARD_ALIASES[board]):
            return board
    return None


def match_category(text: str) -> TourCategory | None:
    """Tur toifasini topadi. Umra/haj birinchi — ular aniqroq belgi."""
    h = normalize(text)
    order = (
        TourCategory.HAJ, TourCategory.UMRA, TourCategory.SKI,
        TourCategory.MEDICAL, TourCategory.HONEYMOON, TourCategory.SHOPPING,
        TourCategory.EDUCATION, TourCategory.CRUISE, TourCategory.BUSINESS,
        TourCategory.EXCURSION, TourCategory.BEACH,
    )
    for cat in order:
        if any(_alias_hit(h, a) for a in CATEGORY_ALIASES[cat]):
            return cat
    return None


def match_star(text: str) -> str | None:
    h = normalize(text)
    for star in ("5", "4", "3", "2"):
        if any(_alias_hit(h, a) for a in STAR_ALIASES[star]):
            return star
    return None


def match_currency(text: str) -> str | None:
    h = normalize(text)
    for code, aliases in CURRENCY_ALIASES.items():
        if any(_alias_hit(h, a) for a in aliases):
            return code
    return None


def match_destinations(text: str) -> list[Destination]:
    """Yo'nalishlarni topadi — kurort davlatdan ustun.

    "Antalya" yozilsa Turkiya ham qo'shiladi (kurort orqali), lekin ro'yxatda
    kurort birinchi turadi — u aniqroq.
    """
    h = normalize(text)
    found: list[Destination] = []
    for dest in RESORTS + COUNTRIES:
        names = (dest.name_uz, dest.code) + dest.aliases
        if any(_alias_hit(h, n) for n in names):
            found.append(dest)
    # Kurort topilgan bo'lsa uning davlatini ham qo'shamiz.
    codes = {d.code for d in found}
    for dest in list(found):
        if not dest.is_country and dest.country_code not in codes:
            country = get_destination(dest.country_code)
            if country:
                found.append(country)
                codes.add(country.code)
    found.sort(key=lambda d: (d.is_country, d.rank))
    return found


def match_all(text: str) -> TaxonomyMatch:
    """Matndan hamma kategoriyani bir yo'la ajratadi.

    Bu **LLM'siz** ishlaydi va so'rovlarning katta qismini qoplaydi. AI faqat
    shu topa olmagan joyga chaqiriladi — shunda har qidiruvda pul ketmaydi.
    """
    result = TaxonomyMatch(
        destinations=match_destinations(text),
        board=match_board(text),
        category=match_category(text),
        star=match_star(text),
        currency=match_currency(text),
    )

    # Ba'zi toifa yo'nalishni o'zi belgilaydi: umra va haj faqat Saudiyada
    # bo'ladi. Agent "umraga 14 kun" deb yozsa davlatni qayta so'ramaymiz.
    if result.category in (TourCategory.UMRA, TourCategory.HAJ) and not result.destinations:
        implied = countries_for_category(result.category)
        if implied:
            result.destinations = implied
            result.inferred.add("destinations")

    return result


# ==========================================================================
# Qidirish yordamchilari (UI uchun)
# ==========================================================================
def get_destination(code: str) -> Destination | None:
    code_n = (code or "").strip().upper()
    for dest in ALL_DESTINATIONS:
        if dest.code == code_n:
            return dest
    return None


def popular_countries(limit: int = 10) -> list[Destination]:
    """Eng ommabop davlatlar — sidebar/filtr uchun."""
    return sorted(COUNTRIES, key=lambda d: d.rank)[:limit]


def resorts_of(country_code: str) -> list[Destination]:
    """Davlat ichidagi kurortlar."""
    cc = (country_code or "").strip().upper()
    return sorted(
        (d for d in RESORTS if d.country_code == cc and not d.is_country),
        key=lambda d: d.rank,
    )


def countries_for_category(category: TourCategory) -> list[Destination]:
    """Shu toifa uchun mos davlatlar (masalan umra -> Saudiya)."""
    return sorted(
        (c for c in COUNTRIES if category in c.categories), key=lambda d: d.rank
    )


def taxonomy_snapshot() -> dict:
    """Frontend uchun to'liq ma'lumotnoma (bir marta yuklab olinadi)."""
    return {
        "boards": [
            {"code": b.value, "label": BOARD_LABELS[b]} for b in Board
        ],
        "categories": [
            {"code": c.value, "label": CATEGORY_LABELS[c]} for c in TourCategory
        ],
        "stars": list(STAR_VALUES),
        "currencies": list(CURRENCY_ALIASES),
        "countries": [
            {
                "code": c.code,
                "name": c.name_uz,
                "rank": c.rank,
                "visa_free": c.visa_free,
                "categories": [x.value for x in c.categories],
                "resorts": [
                    {"code": r.code, "name": r.name_uz} for r in resorts_of(c.code)
                ],
            }
            for c in sorted(COUNTRIES, key=lambda d: d.rank)
        ],
    }
