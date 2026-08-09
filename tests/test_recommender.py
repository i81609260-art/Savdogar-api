"""Tur tavsiyalovchi: saralash, ruxsat va o'rganish.

Eng muhim shart — RUXSAT BERMAGAN agentlikning turi tavsiyaga
tushmasligi. Qolgani tartib masalasi, bu esa maxfiylik masalasi.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.services import recommender
from app.services.travel_profile import score, to_preference
from tests.conftest import TestSessionLocal


def _tur(**kw) -> Tour:
    """Bazaga yozilmaydigan tur — `rank` toza funksiya."""
    asos = dict(
        id=1,
        company_id=1,
        title="Antalya dam olish",
        description="Dengiz bo'yida plyaj dam olishi",
        city="Antalya",
        country="Turkiya",
        departure_city="Toshkent",
        price=12_000_000,
        price_uzs=12_000_000,
        currency="UZS",
        duration_days=7,
        available_slots=10,
        booking_type="group",
        image_url=None,
        start_date=None,
    )
    asos.update(kw)
    return Tour(**asos)


_TINCH = {"hafta_oxiri": "uy", "qaytish": "dam", "byudjet": "ekskursiya"}
_FAOL = {"hafta_oxiri": "yangi_joy", "qaytish": "taassurot",
         "charchatadi": "kutish"}


# ── Saralash ─────────────────────────────────────────────────────────


def test_profilga_mos_toifa_yuqorida():
    pref = to_preference(score(_TINCH))
    plyaj = _tur(id=1, title="Antalya plyaj dam olish",
                 description="Dengiz bo'yida")
    changi = _tur(id=2, title="Changi kurorti",
                  description="Tog'da changi uchish", city="Almaty",
                  country="Qozogiston")
    natija = recommender.rank([changi, plyaj], pref)
    assert natija[0].tour.id == 1
    assert any(m.startswith("toifa:") for m in natija[0].matched)


def test_joy_qolmagan_tur_pastga_tushadi():
    """Bo'sh joyi yo'q turni yuqorida ko'rsatish mijozni aldash."""
    pref = to_preference(score(_TINCH))
    bor = _tur(id=1, available_slots=8)
    yoq = _tur(id=2, available_slots=0)
    natija = recommender.rank([yoq, bor], pref)
    assert natija[0].tour.id == 1


def test_oz_shahridan_jonaydigan_tur_yuqorida():
    pref = to_preference(score(_TINCH))
    toshkent = _tur(id=1, departure_city="Toshkent")
    samarqand = _tur(id=2, departure_city="Samarqand")
    natija = recommender.rank(
        [samarqand, toshkent], pref, departure_city="Toshkent"
    )
    assert natija[0].tour.id == 1
    assert "shahringizdan" in natija[0].matched


def test_matndagi_yonalish_hisobga_olinadi():
    pref = to_preference(score(_TINCH))
    turkiya = _tur(id=1, city="Antalya", country="Turkiya")
    misr = _tur(id=2, city="Sharm ash-Shayx", country="Misr")
    natija = recommender.rank(
        [misr, turkiya], pref,
        recommender.extract_query("Antalyaga bormoqchiman"),
    )
    assert natija[0].tour.id == 1


def test_byudjetdan_oshgan_tur_pastroqda():
    pref = to_preference(score(_TINCH))
    arzon = _tur(id=1, price=8_000_000, price_uzs=8_000_000)
    qimmat = _tur(id=2, price=40_000_000, price_uzs=40_000_000)
    q = recommender.extract_query("10 mln so'mgacha")
    natija = recommender.rank([qimmat, arzon], pref, q)
    assert natija[0].tour.id == 1
    assert "byudjet" in natija[0].matched


def test_bosh_royxat_yiqilmaydi():
    assert recommender.rank([], to_preference(score({}))) == []


def test_hech_qanday_shart_mos_kelmasa_ham_royxat_qaytadi():
    """Bo'sh ro'yxat ko'rsatishdan ko'ra eng yaqinini ko'rsatgan ma'qul."""
    pref = to_preference(score(_FAOL))
    t = _tur(title="Umra ziyorati", description="Makka va Madina",
             city="Makka", country="Saudiya Arabistoni")
    natija = recommender.rank([t], pref)
    assert len(natija) == 1


# ── O'rganish ────────────────────────────────────────────────────────


def test_organgan_markaz_ballni_kotaradi():
    """Tarixda shu profil plyajni bron qilgan bo'lsa u yuqoriga chiqadi."""
    profile = score(_TINCH)
    pref = to_preference(profile)
    t = _tur(title="Antalya plyaj", description="Dengiz")

    tarixsiz = recommender.rank([t], pref, profile=profile)[0].score
    markaz = {
        "plyaj": {
            "sokinlik": profile.get("sokinlik"),
            "yangilik": profile.get("yangilik"),
            "davra": profile.get("davra"),
            "tartib": profile.get("tartib"),
        }
    }
    tarixli = recommender.rank(
        [t], pref, profile=profile, learned=markaz
    )[0]
    assert tarixli.score > tarixsiz
    assert "tarix" in tarixli.matched


def test_uzoq_profil_bonus_olmaydi():
    profile = score(_TINCH)
    pref = to_preference(profile)
    t = _tur(title="Antalya plyaj", description="Dengiz")
    # Butunlay teskari markaz.
    markaz = {"plyaj": {"sokinlik": 0.0, "yangilik": 1.0,
                        "davra": 1.0, "tartib": 0.0}}
    natija = recommender.rank([t], pref, profile=profile, learned=markaz)[0]
    assert "tarix" not in natija.matched


# ── Endpointlar ──────────────────────────────────────────────────────


async def test_savollar_uch_tilda(client: AsyncClient):
    for til in ("uz", "ru", "en"):
        r = await client.get(f"/api/recommender/questions?lang={til}")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 5
        assert body["questions"][0]["answers"]
        assert body["dimensions"]


async def test_ruxsat_bermagan_agentlik_tavsiyaga_tushmaydi(
    client: AsyncClient,
):
    """Eng muhim shart: firma o'zi ruxsat bermaguncha ko'rinmaydi."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = False
        firma.status = CompanyStatus.APPROVED
        db.add(Tour(
            company_id=firma.id,
            title="Antalya plyaj dam olish",
            description="Dengiz bo'yida 7 kecha",
            city="Antalya", country="Turkiya",
            price=12_000_000, duration_days=7, available_slots=10,
        ))
        await db.commit()

    r = await client.post("/api/recommender", json={"answers": _TINCH})
    assert r.status_code == 200
    assert r.json()["items"] == []

    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = True
        await db.commit()

    r = await client.post("/api/recommender", json={"answers": _TINCH})
    assert len(r.json()["items"]) == 1


async def test_javobsiz_ham_tavsiya_beradi(client: AsyncClient):
    """Anketani to'ldirmagan odam ham natija ko'rsin."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = True
        firma.status = CompanyStatus.APPROVED
        db.add(Tour(
            company_id=firma.id, title="Dubay sayohati",
            description="Shahar turi", city="Dubay", country="BAA",
            price=9_000_000, duration_days=5, available_slots=6,
        ))
        await db.commit()

    r = await client.post("/api/recommender", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["items"]
    assert body["profile"]["answered"] == 0
    assert body["reasons"]


async def test_suhbat_javob_qaytaradi(client: AsyncClient):
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = True
        firma.status = CompanyStatus.APPROVED
        db.add(Tour(
            company_id=firma.id, title="Antalya plyaj",
            description="Dengiz bo'yida", city="Antalya", country="Turkiya",
            price=12_000_000, duration_days=7, available_slots=10,
        ))
        await db.commit()

    r = await client.post(
        "/api/recommender/chat",
        json={"message": "avgustda 2 kishi 15 mln gacha Turkiyaga",
              "answers": _TINCH},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert "<" not in body["reply"], "javobda HTML bo'lmasin"


async def test_hodisa_yoziladi(client: AsyncClient):
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = True
        tur = Tour(
            company_id=firma.id, title="Antalya plyaj",
            description="Dengiz", city="Antalya", country="Turkiya",
            price=12_000_000, duration_days=7, available_slots=10,
        )
        db.add(tur)
        await db.commit()
        tid = tur.id

    r = await client.post(
        "/api/recommender/event",
        json={"tour_id": tid, "outcome": "booked", "answers": _TINCH},
    )
    assert r.json()["ok"] is True


async def test_notogri_holat_qabul_qilinmaydi(client: AsyncClient):
    r = await client.post(
        "/api/recommender/event",
        json={"tour_id": 1, "outcome": "o'ylab ko'raman"},
    )
    assert r.json()["ok"] is False


# ── Ruxsatni agentlikning o'zi boshqaradi ────────────────────────────


async def test_agentlik_ozi_ruxsat_beradi(client: AsyncClient, auth_headers):
    """Qaror agentlikniki: o'z turlarini kimga ko'rsatishni firma hal qiladi."""
    r = await client.get("/api/admin/company/recommender", headers=auth_headers)
    assert r.status_code == 200

    r = await client.patch(
        "/api/admin/company/recommender",
        headers=auth_headers,
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True

    r = await client.get("/api/admin/company/recommender", headers=auth_headers)
    assert r.json()["enabled"] is True

    r = await client.patch(
        "/api/admin/company/recommender",
        headers=auth_headers,
        json={"enabled": False},
    )
    assert r.json()["enabled"] is False


async def test_kirmagan_odam_ruxsatni_ozgartira_olmaydi(client: AsyncClient):
    r = await client.patch(
        "/api/admin/company/recommender", json={"enabled": True}
    )
    assert r.status_code in (401, 403)


async def test_bosh_anketa_hodisa_yozmaydi(client: AsyncClient):
    """Hamma o'lchami betaraf profil hech nima o'rgatmaydi."""
    from sqlalchemy import func

    from app.models.recommendation_event import RecommendationEvent

    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        firma.recommender_enabled = True
        db.add(Tour(
            company_id=firma.id, title="Antalya plyaj",
            description="Dengiz", city="Antalya", country="Turkiya",
            price=12_000_000, duration_days=7, available_slots=10,
        ))
        await db.commit()

    await client.post("/api/recommender", json={})
    async with TestSessionLocal() as db:
        soni = (
            await db.execute(select(func.count(RecommendationEvent.id)))
        ).scalar()
    assert soni == 0

    await client.post("/api/recommender", json={"answers": _TINCH})
    async with TestSessionLocal() as db:
        soni = (
            await db.execute(select(func.count(RecommendationEvent.id)))
        ).scalar()
    assert soni > 0
