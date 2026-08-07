"""Tur kategoriyalari ma'lumotnomasiga testlar.

Bu modul 18 ta operatorning turlicha yozuvini bitta kanonik qiymatga
keltiradi. Xato bo'lsa taqqoslash buziladi va "eng arzoni" noto'g'ri
ko'rsatiladi — shuning uchun testlar aniq shu joylarni bosadi:

  * o'zbekcha qo'shimchalar ("Antalya**ga**", "dollar**gacha**");
  * ruscha kelishik ("Грузи**ю**", "Турци**ю**");
  * qisqa kodlar noto'g'ri joyga tushmasligi ("ai" != "**ai**rport").
"""

import pytest

from app.services.tour_taxonomy import (
    ALL_DESTINATIONS,
    COUNTRIES,
    RESORTS,
    Board,
    TourCategory,
    countries_for_category,
    get_destination,
    match_all,
    match_board,
    match_category,
    match_currency,
    match_destinations,
    match_star,
    normalize,
    popular_countries,
    resorts_of,
    taxonomy_snapshot,
)


# --------------------------------------------------------------------------
# Ma'lumotnoma yaxlitligi
# --------------------------------------------------------------------------
def test_destination_codes_unique():
    codes = [d.code for d in ALL_DESTINATIONS]
    assert len(codes) == len(set(codes)), "kod takrorlangan"


def test_every_resort_has_existing_country():
    country_codes = {c.code for c in COUNTRIES}
    for resort in RESORTS:
        assert resort.country_code in country_codes, f"{resort.code} davlatsiz"


def test_countries_are_self_referential():
    for country in COUNTRIES:
        assert country.is_country
        assert country.country_code == country.code


def test_ranking_reflects_market_data():
    """Tartib O'zbekiston bozorining haqiqiy raqamlariga mos bo'lsin.

    2026 yanvar-aprel: Saudiya 138k (umra), Rossiya 115k, Turkiya 70k.
    Universal taksonomiyada Turkiya birinchi bo'lardi — bu bozorda emas.
    """
    top = [d.code for d in popular_countries(5)]
    assert top[0] == "SA", "Saudiya (umra) birinchi bo'lishi kerak"
    assert "TR" in top and "AE" in top and "RU" in top


# --------------------------------------------------------------------------
# Normalizatsiya
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ANTALYA", "antalya"),
        ("Şarm", "sarm"),
        ("Sharm-el-Sheikh", "sharm el sheikh"),
        ("Issiqko'l", "issiqko'l"),
        ("Issiqkoʻl", "issiqko'l"),
        ("  ko'p   bo'sh  ", "ko'p bo'sh"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_keeps_star_and_plus():
    """`5*` va `HB+` belgilarini yo'qotmasin — ular ma'no tashiydi."""
    assert "*" in normalize("5*")
    assert "+" in normalize("HB+")


def test_normalize_keeps_currency_symbols():
    """`$`, `€`, `₽` ham ma'no tashiydi — o'chsa valyuta aniqlanmay qolardi."""
    assert "$" in normalize("$500")
    assert "€" in normalize("€300")
    assert "₽" in normalize("₽10000")


@pytest.mark.parametrize(
    "text,expected", [("$500", "USD"), ("€300", "EUR"), ("₽10000", "RUB")]
)
def test_currency_symbols_match(text, expected):
    assert match_currency(text) == expected


# --------------------------------------------------------------------------
# Ovqatlanish
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("all inclusive", Board.AI),
        ("все включено", Board.AI),
        ("hammasi kiritilgan", Board.AI),
        ("ultra all inclusive", Board.UAI),
        ("ультра все включено", Board.UAI),
        ("2 mahal", Board.HB),
        ("полупансион", Board.HB),
        ("HB+", Board.HBP),
        ("3 mahal", Board.FB),
        ("полный пансион", Board.FB),
        ("faqat nonushta", Board.BB),
        ("только завтрак", Board.BB),
        ("без питания", Board.RO),
        ("hech qanday belgi yo'q", None),
    ],
)
def test_match_board(text, expected):
    assert match_board(text) == expected


def test_uai_wins_over_ai():
    """"ultra all inclusive" ichida "all inclusive" bor — aniqrog'i olinsin."""
    assert match_board("Ultra All Inclusive paket") == Board.UAI


def test_hb_plus_wins_over_hb():
    assert match_board("HB+ ovqatlanish") == Board.HBP


# --------------------------------------------------------------------------
# Toifa
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("umra tur", TourCategory.UMRA),
        ("умра зиёрат", TourCategory.UMRA),
        ("haj safari", TourCategory.HAJ),
        ("хадж", TourCategory.HAJ),
        ("plyaj dam olish", TourCategory.BEACH),
        ("экскурсионный тур", TourCategory.EXCURSION),
        ("горнолыжный курорт", TourCategory.SKI),
        ("changi kurorti", TourCategory.SKI),
        ("лечебный санаторий", TourCategory.MEDICAL),
        ("медовый месяц", TourCategory.HONEYMOON),
        ("шоп-тур", TourCategory.SHOPPING),
    ],
)
def test_match_category(text, expected):
    assert match_category(text) == expected


def test_haj_not_confused_with_umra():
    assert match_category("haj 2026") == TourCategory.HAJ
    assert match_category("umra 2026") == TourCategory.UMRA


@pytest.mark.parametrize(
    "text",
    [
        "tur qidir",
        "Antalyaga tur",
        "eng arzon tur paket",
        "tur operatorlardan qidir",
    ],
)
def test_umumiy_tur_sozi_kategoriya_bermaydi(text):
    """"tur" — o'zbekchada umumiy so'z, kategoriya emas.

    U ilgari EXCURSION taxallusi edi, shuning uchun deyarli HAR BIR so'rov
    "Ekskursiya" deb belgilanardi va agent xulosada mijoz so'ramagan
    kategoriyani ko'rardi.
    """
    assert match_category(text) is None


def test_haqiqiy_ekskursiya_hali_ham_tanaladi():
    """"tur" olib tashlangani aniq so'zlarni buzmasligi kerak."""
    assert match_category("ekskursiya dasturi") == TourCategory.EXCURSION
    assert match_category("экскурсионный тур") == TourCategory.EXCURSION


# --------------------------------------------------------------------------
# Yulduz va valyuta
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [("5*", "5"), ("5 yulduz", "5"), ("4 звезды", "4"), ("3 star otel", "3"),
     ("yulduzsiz", None)],
)
def test_match_star(text, expected):
    assert match_star(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [("500 dollar", "USD"), ("500 dollargacha", "USD"), ("5 mln so'm", "UZS"),
     ("300 евро", "EUR"), ("narx yo'q", None)],
)
def test_match_currency(text, expected):
    assert match_currency(text) == expected


# --------------------------------------------------------------------------
# O'zbek qo'shimchalari — so'zga yopishib yoziladi
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_code",
    [
        ("Antalya", "TR-AYT"),
        ("Antalyaga boramiz", "TR-AYT"),
        ("Antalyada dam olish", "TR-AYT"),
        ("Antalyadan qaytish", "TR-AYT"),
        ("Turkiyaga", "TR"),
        ("Turkiyada", "TR"),
        ("Dubayga", "AE-DXB"),
        ("Batumida", "GE-BUS"),
    ],
)
def test_uzbek_suffixes(text, expected_code):
    codes = [d.code for d in match_destinations(text)]
    assert expected_code in codes, f"{text!r} -> {codes}"


def test_currency_with_uzbek_suffix():
    """"500 dollargacha" — qo'shimcha so'zga yopishgan."""
    assert match_currency("byudjet 500 dollargacha") == "USD"


# --------------------------------------------------------------------------
# Rus kelishiklari — so'z OXIRI o'zgaradi
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_code",
    [
        ("Грузия", "GE"),
        ("тур в Грузию", "GE"),
        ("отдых в Грузии", "GE"),
        ("Турция", "TR"),
        ("поездка в Турцию", "TR"),
        ("Анталия", "TR-AYT"),
        ("в Анталии", "TR-AYT"),
        ("Мальдивы", "MV"),
    ],
)
def test_russian_declension(text, expected_code):
    codes = [d.code for d in match_destinations(text)]
    assert expected_code in codes, f"{text!r} -> {codes}"


# --------------------------------------------------------------------------
# Noto'g'ri moslik bo'lmasin
# --------------------------------------------------------------------------
def test_short_codes_do_not_false_positive():
    """"ai" (All Inclusive) boshqa so'z ichidan topilmasin."""
    assert match_board("aeroportdan transfer") is None
    assert match_board("Dubai shahri") is None


def test_unrelated_text_matches_nothing():
    result = match_all("bugun ob-havo yaxshi")
    assert result.destinations == []
    assert result.board is None
    assert result.star is None


# --------------------------------------------------------------------------
# Kurort -> davlat bog'lanishi
# --------------------------------------------------------------------------
def test_resort_implies_country():
    """Kurort topilsa davlati ham qo'shilsin — filtr ikkalasida ishlashi uchun."""
    codes = [d.code for d in match_destinations("Kemer 5*")]
    assert "TR-KMR" in codes
    assert "TR" in codes


def test_resort_ranked_before_country():
    """Kurort aniqroq — ro'yxatda oldin tursin."""
    dests = match_destinations("Sharm-el-Sheikh")
    assert not dests[0].is_country
    assert dests[0].code == "EG-SSH"


# --------------------------------------------------------------------------
# Xulosa qilish
# --------------------------------------------------------------------------
def test_umra_implies_saudi_arabia():
    """Umra faqat Saudiyada — davlatni qayta so'ramaymiz."""
    result = match_all("Umraga 14 kunlik safar")
    assert result.category == TourCategory.UMRA
    assert [d.code for d in result.destinations] == ["SA"]
    assert "destinations" in result.inferred, "xulosa ekani belgilanmagan"


def test_explicit_destination_not_marked_inferred():
    result = match_all("Antalya all inclusive")
    assert result.destinations
    assert "destinations" not in result.inferred


# --------------------------------------------------------------------------
# To'liq so'rovlar (haqiqiy holatlar)
# --------------------------------------------------------------------------
def test_full_query_uzbek():
    r = match_all("Antalyaga 5 yulduz all inclusive 2 kishi 500 dollargacha")
    assert [d.code for d in r.destinations][:2] == ["TR-AYT", "TR"]
    assert r.board == Board.AI
    assert r.star == "5"
    assert r.currency == "USD"


def test_full_query_russian():
    r = match_all("Шарм-эль-Шейх 4 звезды все включено на 7 ночей")
    assert "EG-SSH" in [d.code for d in r.destinations]
    assert r.board == Board.AI
    assert r.star == "4"


def test_full_query_umra():
    r = match_all("Умра Мекка Медина 10 кун")
    assert r.category == TourCategory.UMRA
    codes = [d.code for d in r.destinations]
    assert "SA-MKK" in codes and "SA" in codes


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------
def test_resorts_of_turkey():
    codes = [d.code for d in resorts_of("TR")]
    assert "TR-AYT" in codes
    assert all(c.startswith("TR-") for c in codes)


def test_countries_for_umra():
    assert [c.code for c in countries_for_category(TourCategory.UMRA)] == ["SA"]


def test_get_destination_case_insensitive():
    assert get_destination("tr-ayt").code == "TR-AYT"
    assert get_destination("yoq") is None


def test_snapshot_is_complete_and_serialisable():
    import json

    snap = taxonomy_snapshot()
    assert len(snap["countries"]) == len(COUNTRIES)
    assert len(snap["boards"]) == len(Board)
    assert len(snap["categories"]) == len(TourCategory)
    turkey = next(c for c in snap["countries"] if c["code"] == "TR")
    assert len(turkey["resorts"]) >= 5
    json.dumps(snap)  # frontend'ga yuboriladi — JSON bo'lishi shart
