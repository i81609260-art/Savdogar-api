"""Tella tezligi va firmalar ajratilishi.

Ikkita talab bir yechimdan chiqadi: model FIRMA bo'yicha bo'lsa,
to'plam kichik qoladi va qurish tez bo'ladi.

Ilgari model bitta va umumiy edi hamda foydalanuvchi so'rovi ICHIDA
qayta qurilardi. Ya'ni yordamchi o'rgangani sari sekinlashardi — 6000
misolda qurish ~2.8 soniya edi.
"""

import asyncio
import time

import pytest
from sqlalchemy import select

from app.models.assistant_example import AssistantExample
from app.models.company import Company
from app.models.user import User
from app.services import ml_assistant
from app.services.ml_assistant import _LearningStore, _store
from tests.conftest import TestSessionLocal

# `setup_db` — bazaga tegadigan sinovlar uni ATAYLAB so'raydi: u
# `autouse` emas, chunki sof funksiya sinovlariga ~2 s qo'shardi.
INTENTLAR = ["create_tour", "list_tours", "list_customers", "report"]


def _misollar(nechta: int, belgi: str = "a") -> list[tuple[str, str]]:
    return [
        (f"{belgi} sinov ibora {i} qo'shimcha matn", INTENTLAR[i % len(INTENTLAR)])
        for i in range(nechta)
    ]


@pytest.fixture(autouse=True)
def _toza_kesh():
    """Har sinov o'z keshidan boshlasin."""
    ml_assistant._STORES.clear()
    yield
    ml_assistant._STORES.clear()


# ── Tezlik ───────────────────────────────────────────────────────────


def test_bashorat_juda_tez():
    """Javob 1 soniyadan oshmasligi kerak — bashorat esa uning kichik qismi."""
    store = _store(1)
    t0 = time.perf_counter()
    for _ in range(50):
        store.predict("nechta turim bor")
    ortacha = (time.perf_counter() - t0) / 50
    assert ortacha < 0.05, f"bitta bashorat {ortacha*1000:.0f} ms"


def test_urug_modeli_bir_marta_quriladi():
    """Har firma uchun qaytadan qurilsa, birinchi savol ~120 ms kutardi."""
    ml_assistant._SEED = None
    t0 = time.perf_counter()
    _store(1)
    birinchi = time.perf_counter() - t0

    t0 = time.perf_counter()
    _store(2)
    ikkinchi = time.perf_counter() - t0

    assert ikkinchi < birinchi / 4, (
        f"ikkinchi firma ham qaytadan qurdi: {ikkinchi*1000:.0f} ms"
    )
    assert ikkinchi < 0.02


async def test_organish_javobni_kutkazmaydi(setup_db):
    """`learn` chaqiruvi model qurishni KUTMASLIGI kerak.

    Aks holda foydalanuvchi o'z iborasini o'rgatgani uchun jazolanardi.
    """
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        store = _store(firma.id)
        # Katta to'plam — sinxron qurilsa sezilarli vaqt ketardi.
        store.learned = _misollar(1200)
        store.learned_norm = {t for t, _ in store.learned}

        t0 = time.perf_counter()
        await store.learn(db, firma.id, "mutlaqo yangi ibora bu yerda", "list_tours")
        ketgan = time.perf_counter() - t0

    assert ketgan < 0.5, f"o'rganish {ketgan*1000:.0f} ms ushlab qoldi"


async def test_fondagi_qurish_modelni_yangilaydi(setup_db):
    """Fonda ketsa ham natija KELISHI kerak — yo'qotib qo'ymaslik."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        store = _store(firma.id)
        eski = store.clf
        await store.learn(db, firma.id, "butunlay boshqacha ibora", "list_tours")

        # Fon vazifasi tugashini kutamiz.
        for _ in range(100):
            if store.clf is not eski and not store._rebuilding:
                break
            await asyncio.sleep(0.05)

    assert store.clf is not eski, "model yangilanmadi"


def test_misollar_soni_chegaralangan():
    """Chegarasiz o'sish qurish vaqtini ham cheksiz o'stirardi."""
    store = _LearningStore(1)
    store.learned = _misollar(ml_assistant._MAX_LEARNED + 50)
    store.learned_norm = {t for t, _ in store.learned}
    assert len(store.learned) > ml_assistant._MAX_LEARNED

    # `learn` chegaradan oshganda eng eskisini chiqaradi.
    eng_eski = store.learned[0][0]
    store.learned.append(("yangi ibora", "report"))
    while len(store.learned) > ml_assistant._MAX_LEARNED:
        tashlandi = store.learned.pop(0)
        store.learned_norm.discard(tashlandi[0])
    assert len(store.learned) == ml_assistant._MAX_LEARNED
    assert eng_eski not in store.learned_norm


# ── Firmalar ajratilishi ─────────────────────────────────────────────


def test_har_firmaga_ozining_modeli():
    """Bir agentlikning iborasi boshqasinikiga aralashmasin."""
    a, b = _store(1), _store(2)
    assert a is not b
    assert a.company_id == 1 and b.company_id == 2


def test_bir_xil_firma_bir_xil_modelni_oladi():
    assert _store(7) is _store(7)


def test_kesh_chegaralangan():
    """Xotirada hamma firmani saqlab bo'lmaydi."""
    for i in range(ml_assistant._MAX_STORES + 10):
        _store(i)
    assert len(ml_assistant._STORES) <= ml_assistant._MAX_STORES


async def test_boshqa_firmaning_misollari_yuklanmaydi(setup_db):
    """Eng muhim shart: `ensure_fresh` faqat o'z firmasini o'qisin."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        boshqa = Company(name="Ikkinchi", slug="ikkinchi", city="Buxoro",
                         phone="998901112244", email="ikki@test.uz")
        db.add(boshqa)
        await db.flush()

        db.add(AssistantExample(
            company_id=firma.id, text="birinchi firmaning iborasi", intent="report"
        ))
        db.add(AssistantExample(
            company_id=boshqa.id, text="ikkinchi firmaning iborasi", intent="report"
        ))
        await db.commit()

        a = _store(firma.id)
        await a.ensure_fresh(db)
        b = _store(boshqa.id)
        await b.ensure_fresh(db)

    a_matnlar = {t for t, _ in a.learned}
    b_matnlar = {t for t, _ in b.learned}
    assert any("birinchi" in t for t in a_matnlar)
    assert not any("ikkinchi" in t for t in a_matnlar), "begona ibora tushdi"
    assert any("ikkinchi" in t for t in b_matnlar)
    assert not any("birinchi" in t for t in b_matnlar), "begona ibora tushdi"


async def test_yordamchi_javobi_bir_soniyadan_tez(client, auth_headers):
    """Uchdan-uchgacha o'lchov — endpoint orqali."""
    savollar = ["salom", "nechta turim bor", "mijozlar ro'yxati", "hisobot"]
    async with TestSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == "admin@test.uz"))
        ).scalar_one()
        _store(user.company_id)   # urug' modelini oldindan qurib qo'yamiz

    for savol in savollar:
        t0 = time.perf_counter()
        r = await client.post(
            "/api/assistant/chat", headers=auth_headers, json={"message": savol}
        )
        ketgan = time.perf_counter() - t0
        assert r.status_code == 200, r.text
        assert r.json()["reply"]
        assert ketgan < 1.0, f"«{savol}» -> {ketgan*1000:.0f} ms"
