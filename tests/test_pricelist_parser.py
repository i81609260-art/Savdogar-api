"""Price-list tahliliga testlar.

Bu qatlam operator sayti, login-parol yoki uning roziligisiz ishlaydi —
narx oqimi allaqachon Telegram va Excel orqali keladi. Shuning uchun
tahlilning ishonchliligi to'g'ridan-to'g'ri mahsulot qiymati.

Eng nozik joy — **narx ajratgichlari**. `1.200` yevropada ming ikki yuz,
amerikada bir butun ikki. Xato o'qilsa agentga 1000 barobar noto'g'ri narx
ko'rsatiladi.
"""

import csv
import io

import pytest

from app.services.pricelist_parser import (
    _PRICE_IN_LINE,  # narx satrini tanish shabloni — regressiya sinovlari uchun
    map_columns,
    parse_pricelist,
    parse_price,
    parse_table,
    parse_text,
)


# --------------------------------------------------------------------------
# Narx
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,amount,currency",
    [
        ("$850", 850.0, "USD"),
        ("690$", 690.0, "USD"),
        ("1 250 USD", 1250.0, "USD"),
        ("540 USD", 540.0, "USD"),
        ("300 евро", 300.0, "EUR"),
        ("2 500 000 so'm", 2_500_000.0, "UZS"),
        ("5 mln", 5_000_000.0, None),
        ("800 ming", 800_000.0, None),
        (850, 850.0, None),
        (850.5, 850.5, None),
        ("", None, None),
        (None, None, None),
        ("kelishuv asosida", None, None),
    ],
)
def test_parse_price(raw, amount, currency):
    assert parse_price(raw) == (amount, currency)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.200", 1200.0),      # yevropacha minglik
        ("1,200", 1200.0),      # amerikacha minglik
        ("1,200.50", 1200.5),   # amerikacha kasr
        ("1.200,50", 1200.5),   # yevropacha kasr
        ("1 200", 1200.0),      # bo'sh joy — doim minglik
        ("12.5", 12.5),         # 3 raqam emas -> kasr
    ],
)
def test_price_separators(raw, expected):
    """Ajratgichlar mintaqaga qarab teskari ma'no beradi."""
    assert parse_price(raw)[0] == expected


def test_zero_price_is_none():
    """0 — narx emas, "kelishuv asosida" degani."""
    assert parse_price("0")[0] is None


# --------------------------------------------------------------------------
# Ustun nomlari
# --------------------------------------------------------------------------
def test_map_columns_uzbek():
    mapping = map_columns(["Mehmonxona", "Yulduz", "Ovqat", "Narx", "Kecha"])
    assert mapping == {0: "hotel_name", 1: "star", 2: "board", 3: "price_gross", 4: "nights"}


def test_map_columns_russian():
    mapping = map_columns(["Отель", "Звезд", "Питание", "Цена", "Ночей"])
    assert set(mapping.values()) == {
        "hotel_name", "star", "board", "price_gross", "nights"
    }


def test_longer_alias_wins():
    """"Netto narx" -> price_net bo'lsin, ichidagi "narx" tufayli
    price_gross bo'lib qolmasin — aks holda sof narx sotuv narxi deb
    yozilib, agentning foydasi noto'g'ri hisoblanardi."""
    mapping = map_columns(["Otel", "Narx", "Netto narx"])
    assert mapping[1] == "price_gross"
    assert mapping[2] == "price_net"


def test_unknown_columns_ignored():
    mapping = map_columns(["Otel", "Izoh", "Narx", "Menejer"])
    assert set(mapping.values()) == {"hotel_name", "price_gross"}


def test_duplicate_column_not_remapped():
    """Bir maydon ikki ustunga bog'lanmasin — birinchisi qoladi."""
    mapping = map_columns(["Narx", "Tsena"])
    assert list(mapping.values()).count("price_gross") == 1


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def _csv_bytes(rows: list[list[str]], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=delimiter).writerows(rows)
    return buffer.getvalue().encode("utf-8")


def test_parse_csv():
    content = _csv_bytes([
        ["Antalya price-list", "", "", ""],           # sarlavhadan oldingi axlat
        ["Mehmonxona", "Yulduz", "Ovqat", "Narx"],
        ["Rixos Downtown", "5*", "UAI", "$850"],
        ["Delphin Imperial", "5*", "AI", "$720"],
    ])
    result = parse_table(content, "price.csv")
    assert len(result.offers) == 2
    first = result.offers[0]
    assert first.hotel_name == "Rixos Downtown"
    assert first.star == "5"
    assert first.board == "UAI"
    assert first.price_gross == 850


def test_header_not_in_first_row():
    """Price-list'lar deyarli hech qachon birinchi qatordan boshlanmaydi."""
    content = _csv_bytes([
        ["ANUR TOUR"], [""], ["Sentabr 2026"], [""],
        ["Otel", "Narx"],
        ["Rixos", "850"],
    ])
    result = parse_table(content, "p.csv")
    assert len(result.offers) == 1


def test_semicolon_delimiter():
    """Ruscha Excel CSV'ni `;` bilan yozadi."""
    content = _csv_bytes([["Otel", "Narx"], ["Rixos", "850"]], delimiter=";")
    result = parse_table(content, "p.csv")
    assert len(result.offers) == 1


def test_rows_without_price_are_reported():
    """Jim yutilgan qator — yo'qolgan narx. Agentga aytilishi kerak."""
    content = _csv_bytes([
        ["Otel", "Narx"],
        ["Rixos", "850"],
        ["Delphin", ""],
        ["Sherwood", "kelishuv"],
    ])
    result = parse_table(content, "p.csv")
    assert len(result.offers) == 1
    assert result.skipped == 2
    assert result.warnings


def test_missing_header_reported():
    content = _csv_bytes([["a", "b"], ["c", "d"]])
    result = parse_table(content, "p.csv")
    assert result.offers == []
    assert "Sarlavha" in result.warnings[0]


def test_net_and_gross_both_read():
    content = _csv_bytes([
        ["Otel", "Netto", "Narx"],
        ["Rixos", "800", "850"],
    ])
    offer = parse_table(content, "p.csv").offers[0]
    assert offer.price_net == 800
    assert offer.price_gross == 850


# --------------------------------------------------------------------------
# Matn (Telegram)
# --------------------------------------------------------------------------
TELEGRAM_POST = """
🔥 ANTALYA 7 kecha чартер
Rixos Downtown 5* UAI — $850
Delphin Imperial 5* AI — $720
Lara Family Club 4* HB — 540 USD

ШАРМ-ЭЛЬ-ШЕЙХ 10 ночей
Rixos Premium Seagate 5* UAI — 1 250 USD
"""


def test_parse_telegram_post():
    result = parse_text(TELEGRAM_POST)
    assert len(result.offers) == 4
    names = [o.hotel_name for o in result.offers]
    assert "Rixos Downtown" in names
    assert "Lara Family Club" in names


def test_context_propagates_to_following_lines():
    """Sarlavha satridagi yo'nalish va kecha keyingi narxlarga tarqalsin."""
    offers = parse_text(TELEGRAM_POST).offers
    antalya = [o for o in offers if o.city == "Antalya"]
    sharm = [o for o in offers if o.city == "Sharm ash-Shayx"]
    assert len(antalya) == 3
    assert len(sharm) == 1
    assert all(o.nights == 7 for o in antalya)
    assert sharm[0].nights == 10


def test_hotel_name_stripped_of_markers():
    """Nomdan yulduz, ovqat kodi va ajratgich olib tashlansin."""
    offer = parse_text("Rixos Downtown 5* UAI — $850").offers[0]
    assert offer.hotel_name == "Rixos Downtown"
    assert offer.star == "5"
    assert offer.board == "UAI"


def test_lines_without_price_are_not_offers():
    result = parse_text("ANTALYA 7 kecha\nchartyer reys\nRixos 5* AI — $850")
    assert len(result.offers) == 1


def test_empty_text():
    result = parse_text("")
    assert result.offers == []


# --------------------------------------------------------------------------
# Format aniqlash
# --------------------------------------------------------------------------
def test_dispatch_by_filename():
    content = _csv_bytes([["Otel", "Narx"], ["Rixos", "850"]])
    assert len(parse_pricelist(content, "price.csv").offers) == 1


def test_dispatch_plain_string():
    assert len(parse_pricelist("Rixos 5* AI — $850").offers) == 1


def test_image_reports_unsupported():
    result = parse_pricelist(b"\x89PNG\r\n", "afisha.png")
    assert result.offers == []
    assert "Rasm" in result.warnings[0]


def test_corrupt_file_does_not_raise():
    """Buzuq fayl butun tahlilni yiqitmasin."""
    result = parse_pricelist(b"\x00\x01buzuq", "price.xlsx")
    assert result.offers == []
    assert result.warnings


# --------------------------------------------------------------------------
# Xlsx
# --------------------------------------------------------------------------
def test_parse_xlsx():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ANUR TOUR — sentabr"])
    sheet.append(["Mehmonxona", "Yulduz", "Ovqat", "Narx", "Kecha"])
    sheet.append(["Rixos Downtown", "5*", "UAI", 850, 7])
    sheet.append(["Delphin Imperial", "5*", "AI", 720, 7])

    buffer = io.BytesIO()
    workbook.save(buffer)
    result = parse_table(buffer.getvalue(), "price.xlsx")

    assert len(result.offers) == 2
    assert result.offers[0].price_gross == 850
    assert result.offers[0].nights == 7


# --------------------------------------------------------------------------
# Valyuta so'z bilan yozilgan holat
# --------------------------------------------------------------------------
# Bu yerdagi ro'yxat ilgari `tour_taxonomy.CURRENCY_ALIASES` dan QO'LDA
# nusxalangan edi va vaqt o'tib undan ajralib ketgan: taksonomiyada "dollar",
# "сўм", "долл", "rubl", "euro" bor edi, tahlilchidagi nusxada yo'q. Natijada
# narxi shunday yozilgan satr "narxsiz" deb hisoblanib, sarlavha o'rnida qabul
# qilinar va JIMGINA tashlab yuborilardi — foydalanuvchi taklif yo'qolganini
# bilmasdi. Endi regex bitta manbadan yasaladi.
@pytest.mark.parametrize(
    "yozuv",
    [
        "890 dollar",      # lotincha — o'zbek operatorlari eng ko'p shunday yozadi
        "1200 долл",       # qisqartma
        "450 евро",
        "750 euro",
        "900 rubl",
        "300 сўм",         # kirill "o'" bilan
        "12 000 000 so'm",
        "12 000 000 soʻm",   # tutuq belgisi (U+02BB)
        "12 000 000 so’m",   # tipografik apostrof (U+2019)
    ],
)
def test_narx_valyuta_sozi_bilan_tanaladi(yozuv):
    assert _PRICE_IN_LINE.search(yozuv), f"tanilmadi: {yozuv}"


@pytest.mark.parametrize(
    "yozuv", ["500 summa", "Antalya 7 kecha", "Aloqa: +998 90 123 45 67"]
)
def test_valyutaga_oxshamagan_matn_narx_deb_olinmaydi(yozuv):
    r"""`(?!\w)` qo'riqchisi: "summa" ichidagi "sum" valyuta emas."""
    assert not _PRICE_IN_LINE.search(yozuv)


def test_sozli_valyutali_satr_taklifga_aylanadi():
    """Butun zanjir: shunday satr endi taklif bo'lib chiqishi kerak."""
    matn = (
        "ANTALYA 7 kecha\n"
        "Rixos Downtown 5* UAI — $850\n"
        "Sunrise Diamond 4* AI — 890 dollar\n"
    )
    result = parse_text(matn)
    nomlar = [o.hotel_name for o in result.offers]
    assert "Sunrise Diamond" in nomlar, f"topilgan: {nomlar}"

    sunrise = next(o for o in result.offers if o.hotel_name == "Sunrise Diamond")
    assert sunrise.price_gross == 890
    assert sunrise.currency == "USD"
    # Sarlavhadagi yo'nalish va kecha bu satrga ham tarqalsin.
    assert sunrise.nights == 7


# --------------------------------------------------------------------------
# Brauzerdan olingan jadval (kengaytma yo'li)
# --------------------------------------------------------------------------
#
# `innerText` jadval kataklarini TAB bilan ajratadi. Ilgari tab
# "mingliklar ajratgichi" deb qabul qilinardi va qo'shni ustundagi son
# narxga yopishib ketardi.

KABINET = (
    "Rixos Downtown Antalya\t5*\tAI\t7\t890 USD\n"
    "Delphin Imperial\t5*\tUAI\t7\t1120 USD\n"
    "Lara Family Club\t4*\tAI\t10\t760 USD\n"
)


def test_tab_narxga_yopishmaydi():
    """Eng qimmat xato: 890 USD o'rniga 7890 USD.

    Agent shu narx bilan mijozga taklif bersa, to'qqiz barobar oshirib
    aytgan bo'lardi.
    """
    natija = parse_text(KABINET)
    assert [o.price_gross for o in natija.offers] == [890.0, 1120.0, 760.0]


def test_ustunli_satrda_nom_faqat_birinchi_katak():
    natija = parse_text(KABINET)
    nomlar = [o.hotel_name for o in natija.offers]
    assert nomlar == [
        "Rixos Downtown Antalya",
        "Delphin Imperial",
        "Lara Family Club",
    ]
    assert all("\t" not in nom for nom in nomlar)


def test_ustunli_satrdan_kecha_soni_olinadi():
    """Kecha soni alohida katakda — u narxga qo'shilib ketmasin."""
    natija = parse_text(KABINET)
    assert [o.nights for o in natija.offers] == [7, 7, 10]


def test_yakka_katakda_ham_tab_ajratadi():
    """Jadval yo'lida `parse_price` bitta katak oladi, lekin himoya qolsin."""
    assert parse_price("7\t890 USD") == (890.0, "USD")
    assert parse_price("10\t760 USD") == (760.0, "USD")


def test_bosh_joy_hamon_minglik_ajratgichi():
    """Tabni chiqarish o'zbekcha yozuvni buzmasligi kerak."""
    assert parse_price("12 500 000 so'm") == (12_500_000.0, "UZS")
    assert parse_price("1 200 EUR") == (1_200.0, "EUR")
