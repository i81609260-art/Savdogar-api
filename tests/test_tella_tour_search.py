"""Tella tur qidiruv so'rovini ajratishga testlar.

Bu qatlam LLM'siz ishlaydi — qoidalar va regex. Shuning uchun testlar
qoidalarning chekka holatlarini bosadi: son bilan birikkan qo'shimchalar,
"1 bola" ni "1 kishi" deb o'qib yubormaslik, sana ajratgichlari.
"""

import pytest

from app.services.tella_tour_search import (
    SEARCH_INTENT,
    SEARCH_TRAINING,
    extract_query,
    missing_slots,
    next_question,
    parse_budget,
    parse_date_from,
    parse_month,
    parse_nights,
    parse_pax,
    summarize,
)
from app.services.tour_taxonomy import Board, TourCategory


# --------------------------------------------------------------------------
# Kecha
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("7 kecha", 7), ("10 kunlik", 10), ("3 kun", 3),
        ("на 7 ночей", 7), ("5 ночи", 5), ("7 nights", 7),
        ("kecha yo'q", None), ("100 kecha", None),  # mantiqsiz uzunlik
    ],
)
def test_parse_nights(text, expected):
    assert parse_nights(text) == expected


# --------------------------------------------------------------------------
# Mehmonlar
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,adults,children",
    [
        ("2 kishi", 2, None),
        ("2 katta", 2, None),
        ("2 katta 1 bola", 2, 1),
        ("2 взрослых 1 ребенок", 2, 1),
        ("3 adults 2 kids", 3, 2),
        ("hech kim", None, None),
    ],
)
def test_parse_pax(text, adults, children):
    assert parse_pax(text) == (adults, children)


def test_children_not_counted_as_adults():
    """"1 bola" dagi "1" kattalar soniga tushib ketmasin."""
    adults, children = parse_pax("1 bola")
    assert children == 1
    assert adults is None


def test_children_before_adults_in_text():
    adults, children = parse_pax("1 bola 2 katta")
    assert (adults, children) == (2, 1)


# --------------------------------------------------------------------------
# Byudjet
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,low,high",
    [
        ("500 dollargacha", None, 500),
        ("500 gacha", None, 500),
        ("до 800", None, 800),
        ("от 300", 300, None),
        ("300 dan 800 gacha", 300, 800),
        ("byudjet 5 mln so'm", None, 5_000_000),
        ("800 ming som", None, 800_000),
        ("$500", None, 500),
        ("narx muhim emas", None, None),
    ],
)
def test_parse_budget(text, low, high):
    assert parse_budget(text) == (low, high)


def test_budget_multiplier_applies():
    """"5 mln" -> 5 000 000, "5" emas."""
    assert parse_budget("5 mln so'm")[1] == 5_000_000


# --------------------------------------------------------------------------
# Sana
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("01.09.2026", "2026-09-01"),
        ("2026-09-01", "2026-09-01"),
        ("01/09/2026", "2026-09-01"),
        ("15 sentabr", "09-15"),
        ("sana yo'q", None),
    ],
)
def test_parse_date_from(text, expected):
    assert parse_date_from(text) == expected


def test_date_survives_punctuation():
    """Normalizatsiya nuqtalarni bo'shliqqa aylantiradi — sana XOM matndan
    o'qilishi kerak, aks holda "01.09.2026" yo'qolardi."""
    assert parse_date_from("01.09.2026 Gudauri changi") == "2026-09-01"


@pytest.mark.parametrize(
    "text,expected",
    [("sentabrda", 9), ("в сентябре", 9), ("dekabr", 12), ("oy yo'q", None)],
)
def test_parse_month(text, expected):
    assert parse_month(text) == expected


# --------------------------------------------------------------------------
# To'liq so'rovlar
# --------------------------------------------------------------------------
def test_full_uzbek_query():
    q = extract_query(
        "Antalyaga 5 yulduz all inclusive 7 kecha 2 katta 1 bola 500 dollargacha"
    )
    assert [d.code for d in q.destinations][:2] == ["TR-AYT", "TR"]
    assert q.star == "5"
    assert q.board == Board.AI
    assert q.nights == 7
    assert (q.adults, q.children) == (2, 1)
    assert q.budget_max == 500
    assert q.currency == "USD"
    assert q.pax == 3


def test_full_russian_query():
    q = extract_query("Шарм-эль-Шейх 4 звезды все включено на 7 ночей 2 взрослых до 800")
    assert "EG-SSH" in [d.code for d in q.destinations]
    assert q.star == "4"
    assert q.board == Board.AI
    assert q.nights == 7
    assert q.adults == 2
    assert q.budget_max == 800


def test_umra_query_infers_country():
    q = extract_query("Umraga 14 kun 2 kishi")
    assert q.category == TourCategory.UMRA
    assert q.country_codes == ["SA"]
    assert "destinations" in q.inferred


def test_currency_defaults_to_usd_when_budget_given():
    q = extract_query("Dubayga 500 gacha")
    assert q.currency == "USD"
    assert "currency" in q.inferred, "taxmin ekani belgilanmagan"


def test_currency_not_invented_without_budget():
    q = extract_query("Dubayga 3 kecha")
    assert q.currency is None
    assert "currency" not in q.inferred


def test_pax_defaults_to_two():
    """Ko'rsatilmasa 2 kishi — eng keng tarqalgan holat."""
    assert extract_query("Antalya 7 kecha").pax == 2


# --------------------------------------------------------------------------
# Yetishmayotgan shartlar / dialog
# --------------------------------------------------------------------------
def test_missing_destination_is_asked():
    q = extract_query("7 kecha 2 kishi 500 dollargacha")
    assert missing_slots(q) == ["destinations"]
    assert "yo'nalish" in next_question(q).lower()


def test_complete_query_has_no_question():
    q = extract_query("Antalyaga 7 kecha")
    assert missing_slots(q) == []
    assert next_question(q) is None


def test_appending_answer_preserves_earlier_slots():
    """Agent yetishmagan shartni aytganda avvalgilari yo'qolmasin."""
    first = extract_query("7 kecha 2 kishi 500 dollargacha qidir")
    assert missing_slots(first) == ["destinations"]

    combined = extract_query(f"{first.raw_text} Antalya 5 yulduz")
    assert missing_slots(combined) == []
    assert combined.nights == 7          # birinchi xabardan
    assert combined.adults == 2          # birinchi xabardan
    assert combined.budget_max == 500    # birinchi xabardan
    assert combined.star == "5"          # ikkinchi xabardan
    assert "TR-AYT" in [d.code for d in combined.destinations]


# --------------------------------------------------------------------------
# Bayon
# --------------------------------------------------------------------------
def test_summary_is_human_readable():
    q = extract_query("Antalyaga 5 yulduz all inclusive 7 kecha 2 katta 500 dollargacha")
    text = summarize(q)
    assert "Antalya" in text
    assert "5*" in text
    assert "All Inclusive" in text
    assert "7 kecha" in text


def test_summary_of_empty_query():
    assert summarize(extract_query("")) == "shartlar ko'rsatilmagan"


def test_to_dict_is_json_serialisable():
    import json

    json.dumps(extract_query("Antalya 7 kecha 500 gacha").to_dict())


# --------------------------------------------------------------------------
# Tella intentiga ulanish
# --------------------------------------------------------------------------
def test_search_training_examples_are_labelled():
    assert SEARCH_TRAINING
    assert all(label == SEARCH_INTENT for _, label in SEARCH_TRAINING)


def test_tella_recognises_search_intent():
    from app.services.ml_assistant import _store

    for text in (
        "Antalyaga 5 yulduz all inclusive qidir",
        "eng arzon turni topib ber",
        "narxlarni solishtir operatorlardan",
    ):
        intent, _ = _store().predict(text)
        assert intent == SEARCH_INTENT, f"{text!r} -> {intent}"


def test_existing_intents_still_work():
    """Yangi intent eskilarini buzmasin — bu eng katta xavf edi."""
    from app.services.ml_assistant import _store

    for text, expected in (
        ("yangi tur qosh", "create_tour"),
        ("nechta tur bor", "count_tours"),
        ("hisobot ber", "report"),
        ("mijoz qosh", "create_customer"),
        ("narxini ozgartir", "update_price"),
    ):
        intent, _ = _store().predict(text)
        assert intent == expected, f"{text!r} -> {intent}"
