"""Psixologik anketa: ballash va tavsiya mezonlari.

Bu qism toza funksiyalardan iborat — bazasiz va tarmoqsiz sinaladi.
"""

import pytest

from app.services.travel_profile import (
    DIMENSIONS,
    QUESTIONS,
    Board,
    TourCategory,
    explain,
    questions_payload,
    score,
    to_preference,
)


def test_har_bir_savol_kamida_uch_javob():
    for q in QUESTIONS:
        assert len(q.answers) >= 3, q.id


def test_savol_va_javob_idlari_takrorlanmaydi():
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    for q in QUESTIONS:
        assert len({a.id for a in q.answers}) == len(q.answers), q.id


def test_hamma_savol_uch_tilda():
    """Bitta til unutilsa mijoz bo'sh matn ko'radi."""
    for q in QUESTIONS:
        assert set(q.text) == {"uz", "ru", "en"}, q.id
        for a in q.answers:
            assert set(a.text) == {"uz", "ru", "en"}, f"{q.id}/{a.id}"


def test_ogirliklar_chegarada():
    for q in QUESTIONS:
        for a in q.answers:
            for dim, w in a.weights.items():
                assert dim in DIMENSIONS, f"{q.id}/{a.id}: {dim}"
                assert -1.0 <= w <= 1.0, f"{q.id}/{a.id}: {w}"
                assert w != 0, "nol ta'sir yozilmasin — javob ma'nosi yo'qoladi"


def test_har_olcham_kamida_ikki_savolda_uchraydi():
    """Bitta savolga bog'liq o'lcham tasodifiy javobdan chayqalib ketadi."""
    sanoq = {d: 0 for d in DIMENSIONS}
    for q in QUESTIONS:
        tegdi = {dim for a in q.answers for dim in a.weights}
        for d in tegdi:
            sanoq[d] += 1
    for d, n in sanoq.items():
        assert n >= 2, f"{d}: faqat {n} ta savolda"


# ── Ballash ──────────────────────────────────────────────────────────


def test_javobsiz_profil_betaraf():
    p = score({})
    assert p.answered == 0
    assert all(v == 0.5 for v in p.scores.values())


def test_notanish_kalitlar_jimgina_tashlanadi():
    """Eski ilova o'chirilgan savolni yuborsa anketa yiqilmasin."""
    p = score({"yoq_savol": "yoq_javob", "hafta_oxiri": "yoq_javob"})
    assert p.answered == 0
    assert all(v == 0.5 for v in p.scores.values())


def test_tinchlik_javoblari_sokinlikni_kotaradi():
    p = score({
        "hafta_oxiri": "uy",
        "qaytish": "dam",
        "byudjet": "ekskursiya",
        "surat": "kam",
    })
    assert p.get("sokinlik") > 0.9


def test_harakat_javoblari_sokinlikni_tushiradi():
    p = score({
        "hafta_oxiri": "yangi_joy",
        "qaytish": "taassurot",
        "charchatadi": "kutish",
        "byudjet": "mehmonxona",
    })
    assert p.get("sokinlik") < 0.2


def test_tegilmagan_olcham_betaraf_qoladi():
    """Faqat bitta o'lchamga tegadigan javob boshqalarni siljitmasin."""
    p = score({"ovqat": "tanish"})   # faqat `yangilik`
    assert p.get("yangilik") == 0.0
    assert p.get("sokinlik") == 0.5
    assert p.get("davra") == 0.5
    assert p.get("tartib") == 0.5


def test_kop_tegilgan_olcham_sungani_bosmaydi():
    """Bir o'lchamga 4 ta, boshqasiga 1 ta javob — ikkalasi ham kuchli
    qolsin. Umumiy bo'luvchi ishlatilsa kamroq tegilgani betarafga
    tortilardi."""
    p = score({
        "hafta_oxiri": "uy",       # sokinlik +, davra -
        "qaytish": "dam",          # sokinlik +
        "byudjet": "ekskursiya",   # sokinlik +
        "surat": "kam",            # sokinlik +
    })
    assert p.get("sokinlik") > 0.9
    assert p.get("davra") == 0.0   # bitta javob, lekin bir tomonlama


# ── Mezonlar ─────────────────────────────────────────────────────────


def test_tinch_odamga_plyaj_va_davolanish():
    pref = to_preference(score({
        "hafta_oxiri": "uy",
        "qaytish": "dam",
        "byudjet": "ekskursiya",
    }))
    assert TourCategory.BEACH in pref.categories
    assert TourCategory.MEDICAL in pref.categories
    assert Board.AI in pref.boards
    assert pref.min_days >= 7


def test_faol_odamga_ekskursiya():
    pref = to_preference(score({
        "hafta_oxiri": "yangi_joy",
        "qaytish": "taassurot",
        "charchatadi": "kutish",
    }))
    assert TourCategory.EXCURSION in pref.categories
    assert Board.AI not in pref.boards, "kun bo'yi tashqarida — AI ortiqcha pul"


def test_rejali_odamga_guruh_turi():
    pref = to_preference(score({
        "yangi_shahar": "xarita",
        "ovqat": "menyu",
        "charchatadi": "ozgarish",
    }))
    assert pref.booking_type == "group"
    assert "reja" in pref.reasons


def test_erkin_odamga_individual_tur():
    pref = to_preference(score({
        "yangi_shahar": "sayr",
        "ovqat": "tavsiya",
        "surat": "oylamayman",
    }))
    assert pref.booking_type == "individual"
    assert "erkinlik" in pref.reasons


def test_betaraf_profil_ham_tavsiya_beradi():
    """Bo'sh natija mijozga hech narsa ko'rsatmasdi."""
    pref = to_preference(score({}))
    assert pref.categories
    assert pref.reasons == ("betaraf",)


def test_toifalar_takrorlanmaydi_va_tartibi_saqlanadi():
    pref = to_preference(score({
        "hafta_oxiri": "uy",        # sokinlik -> BEACH, MEDICAL
        "qaytish": "dam",
        "ovqat": "tanish",          # yangilik past -> BEACH (takror)
    }))
    assert len(pref.categories) == len(set(pref.categories))
    assert pref.categories[0] == TourCategory.BEACH


@pytest.mark.parametrize("til", ["uz", "ru", "en"])
def test_savollar_tanlangan_tilda(til):
    payload = questions_payload(til)
    assert len(payload) == len(QUESTIONS)
    for q in payload:
        assert q["text"], q["id"]
        assert all(a["text"] for a in q["answers"])


def test_notanish_til_ozbekchaga_tushadi():
    assert questions_payload("fr") == questions_payload("uz")


def test_sabablar_mijoz_tilida():
    pref = to_preference(score({"hafta_oxiri": "uy", "qaytish": "dam"}))
    uz = explain(pref, "uz")
    ru = explain(pref, "ru")
    assert uz and ru
    assert uz != ru, "tarjima qilinmagan"
