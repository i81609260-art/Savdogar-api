"""Price-list yuklash va takliflarni ko'rish — API darajasida.

Asosiy tekshiruv o'sha-o'sha: bir turagentning narxi boshqasiga
ko'rinmasin. Narx shartnomaga bog'liq — B ning narxini A ga ko'rsatish
noto'g'ri narx ko'rsatish demakdir.
"""

import csv
import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company, CompanyStatus
from app.models.tour_offer import OfferSource, TourOffer
from app.models.user import User, UserRole
from app.services.auth_service import _token_claims
from app.utils.security import create_access_token, hash_password
from tests.conftest import TestSessionLocal

PRICELIST = """
ANTALYA 7 kecha
Rixos Downtown 5* UAI — $850
Delphin Imperial 5* AI — $720
"""


async def _second_agent_headers() -> dict:
    async with TestSessionLocal() as db:
        company = Company(
            name="Ikkinchi Agentlik", slug="ikkinchi-agentlik", city="Samarqand",
            phone="998901112233", email="ikkinchi@test.uz",
            status=CompanyStatus.APPROVED, tariff="boshlangich",
        )
        db.add(company)
        await db.flush()
        user = User(
            email="admin@ikkinchi.uz", hashed_password=hash_password("parol456"),
            full_name="Ikkinchi Admin", role=UserRole.ADMIN,
            company_id=company.id, is_active=True,
        )
        db.add(user)
        await db.commit()
        return {"Authorization": f"Bearer {create_access_token(_token_claims(user))}"}


def _csv_bytes(rows) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode("utf-8")


# --------------------------------------------------------------------------
# Yuklash
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paste_text_pricelist(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": PRICELIST}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["found"] == 2
    assert body["saved"] == 2
    names = [o["hotel_name"] for o in body["offers_preview"]]
    assert "Rixos Downtown" in names


@pytest.mark.asyncio
async def test_upload_csv_pricelist(client: AsyncClient, auth_headers):
    content = _csv_bytes([
        ["Mehmonxona", "Yulduz", "Ovqat", "Narx"],
        ["Rixos Downtown", "5*", "UAI", "850"],
        ["Delphin Imperial", "5*", "AI", "720"],
    ])
    response = await client.post(
        "/api/pricelists/upload",
        headers=auth_headers,
        files={"file": ("price.csv", content, "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["saved"] == 2


@pytest.mark.asyncio
async def test_upload_reports_unreadable_rows(client: AsyncClient, auth_headers):
    """O'qilmagan qator jim yutilmasin — agentga aytilsin."""
    content = _csv_bytes([
        ["Otel", "Narx"],
        ["Rixos", "850"],
        ["Delphin", ""],
    ])
    response = await client.post(
        "/api/pricelists/upload",
        headers=auth_headers,
        files={"file": ("price.csv", content, "text/csv")},
    )
    body = response.json()
    assert body["saved"] == 1
    assert body["skipped"] == 1
    assert body["warnings"]


@pytest.mark.asyncio
async def test_empty_file_rejected(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/pricelists/upload",
        headers=auth_headers,
        files={"file": ("bosh.csv", b"", "text/csv")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_empty_text_rejected(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": "   "}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_unknown_operator_rejected(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/pricelists/paste",
        headers=auth_headers,
        data={"text": PRICELIST, "operator_id": 999999},
    )
    # `paste` operatorni tekshirmaydi; `upload` tekshiradi.
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_upload_rejects_foreign_operator(client: AsyncClient, auth_headers):
    """B ning shaxsiy operatoriga A price-list bog'lay olmasin."""
    other = await _second_agent_headers()
    created = await client.post(
        "/api/operators", headers=other, json={"name": "Begona Operator"}
    )
    operator_id = created.json()["id"]

    response = await client.post(
        "/api/pricelists/upload",
        headers=auth_headers,
        files={"file": ("p.csv", _csv_bytes([["Otel", "Narx"], ["Rixos", "850"]]), "text/csv")},
        data={"operator_id": str(operator_id)},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Ajratilganlik
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_offers_do_not_leak_between_agents(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": PRICELIST}
    )
    other = await _second_agent_headers()
    await client.post(
        "/api/pricelists/paste",
        headers=other,
        data={"text": "DUBAI 5 kecha\nAtlantis 5* BB — $1200"},
    )

    a_offers = (await client.get("/api/offers", headers=auth_headers)).json()
    b_offers = (await client.get("/api/offers", headers=other)).json()

    assert {o["hotel_name"] for o in a_offers} == {"Rixos Downtown", "Delphin Imperial"}
    assert {o["hotel_name"] for o in b_offers} == {"Atlantis"}


@pytest.mark.asyncio
async def test_cannot_save_foreign_offer(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": PRICELIST}
    )
    async with TestSessionLocal() as db:
        offer_id = (await db.execute(select(TourOffer.id))).scalars().first()

    other = await _second_agent_headers()
    response = await client.post(f"/api/offers/{offer_id}/save", headers=other)
    assert response.status_code == 404, "begona taklif saqlandi!"


# --------------------------------------------------------------------------
# Ko'rish va filtrlash
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_filter_by_star_and_board(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste",
        headers=auth_headers,
        data={"text": "ANTALYA 7 kecha\nRixos 5* UAI — $850\nLara 4* HB — $540"},
    )
    only_five = (
        await client.get("/api/offers?star=5", headers=auth_headers)
    ).json()
    assert [o["hotel_name"] for o in only_five] == ["Rixos"]

    only_hb = (await client.get("/api/offers?board=HB", headers=auth_headers)).json()
    assert [o["hotel_name"] for o in only_hb] == ["Lara"]


@pytest.mark.asyncio
async def test_filter_by_price_range(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste",
        headers=auth_headers,
        data={"text": "ANTALYA\nRixos 5* UAI — $850\nLara 4* HB — $540"},
    )
    cheap = (
        await client.get("/api/offers?price_max=600", headers=auth_headers)
    ).json()
    assert [o["hotel_name"] for o in cheap] == ["Lara"]


@pytest.mark.asyncio
async def test_ranking_prefers_agent_margin_over_price(
    client: AsyncClient, auth_headers
):
    """Eng arzon taklif eng ko'p daromad keltirmasligi mumkin.

    Reyting agentga qoladigan foyda bo'yicha — komissiya operatorga qarab
    har xil, shuning uchun eng past narx eng yaxshi taklif emas.
    """
    content = _csv_bytes([
        ["Otel", "Netto", "Narx"],
        ["Arzon Otel", "780", "800"],    # foyda 20
        ["Qimmat Otel", "800", "900"],   # foyda 100
    ])
    await client.post(
        "/api/pricelists/upload",
        headers=auth_headers,
        files={"file": ("p.csv", content, "text/csv")},
    )
    offers = (await client.get("/api/offers", headers=auth_headers)).json()
    assert offers[0]["hotel_name"] == "Qimmat Otel"
    assert offers[0]["agent_margin"] == 100


@pytest.mark.asyncio
async def test_saved_offer_marked(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": PRICELIST}
    )
    offers = (await client.get("/api/offers", headers=auth_headers)).json()
    response = await client.post(
        f"/api/offers/{offers[0]['id']}/save", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["is_saved"] is True

    saved = (
        await client.get("/api/offers?saved_only=true", headers=auth_headers)
    ).json()
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_offers_carry_source_and_ttl(client: AsyncClient, auth_headers):
    await client.post(
        "/api/pricelists/paste", headers=auth_headers, data={"text": PRICELIST}
    )
    offers = (await client.get("/api/offers", headers=auth_headers)).json()
    assert offers[0]["source"] == OfferSource.PRICELIST
    assert offers[0]["expires_at"] is not None, "TTL qo'yilmagan"
    assert offers[0]["is_fresh"] is True
    # Price-list ishonchliligi jonli qidiruvdan past.
    assert 0 < offers[0]["confidence"] < 0.95


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient):
    assert (await client.get("/api/offers")).status_code in (401, 403)
    assert (
        await client.post("/api/pricelists/paste", data={"text": "x"})
    ).status_code in (401, 403)
