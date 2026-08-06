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
