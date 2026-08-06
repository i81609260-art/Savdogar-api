"""`/api/operators` — API darajasida turagent ajratilganligi.

Model darajasidagi ajratish `test_operator_isolation.py` da tekshirilgan.
Bu yerda undan muhimrog'i tekshiriladi: **HTTP orqali** boshqa turagentning
operatoriga yoki hisobiga yetib bo'ladimi. Model to'g'ri bo'lib, router
`company_id` filtrini unutgan bo'lsa — ma'lumot baribir sizib chiqadi.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company, CompanyStatus
from app.models.tour_operator import OperatorAccount, TourOperator
from app.models.user import User, UserRole
from app.services.auth_service import _token_claims
from app.utils import crypto
from app.utils.security import create_access_token, hash_password
from tests.conftest import TestSessionLocal

SECOND_ADMIN_EMAIL = "admin@ikkinchi.uz"
SECOND_ADMIN_PASSWORD = "parol456"


async def _make_second_agent(client: AsyncClient) -> dict:
    """Ikkinchi turagentlik va uning admini uchun sarlavhalar.

    Token `/api/auth/login` orqali emas, to'g'ridan-to'g'ri yasaladi:
    login endpointida daqiqasiga 10 ta so'rov chegarasi bor va har testda
    ikki marta kirish uni tez to'ldirib qo'yardi (testlar mahsulot xatosi
    tufayli emas, rate-limit tufayli yiqilardi). Da'volar production
    bilan bir xil — `_token_claims` o'sha funksiya.
    """
    async with TestSessionLocal() as db:
        company = Company(
            name="Ikkinchi Agentlik",
            slug="ikkinchi-agentlik",
            city="Samarqand",
            phone="998901112233",
            email="ikkinchi@test.uz",
            status=CompanyStatus.APPROVED,
            tariff="boshlangich",
        )
        db.add(company)
        await db.flush()
        user = User(
            email=SECOND_ADMIN_EMAIL,
            hashed_password=hash_password(SECOND_ADMIN_PASSWORD),
            full_name="Ikkinchi Admin",
            role=UserRole.ADMIN,
            company_id=company.id,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        token = create_access_token(_token_claims(user))

    return {"Authorization": f"Bearer {token}"}


async def _add_catalog_operator(name: str = "Coral Travel", slug: str = "coral") -> int:
    """Platforma katalogi yozuvi (`company_id IS NULL`) — hamma ko'radi."""
    async with TestSessionLocal() as db:
        operator = TourOperator(company_id=None, name=name, slug=slug)
        db.add(operator)
        await db.commit()
        return operator.id


# --------------------------------------------------------------------------
# Ko'rinish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_catalog_operator_visible_to_everyone(client: AsyncClient, auth_headers):
    await _add_catalog_operator()
    response = await client.get("/api/operators", headers=auth_headers)
    assert response.status_code == 200, response.text
    slugs = [o["slug"] for o in response.json()]
    assert "coral" in slugs
    assert next(o for o in response.json() if o["slug"] == "coral")["is_catalog"] is True


@pytest.mark.asyncio
async def test_private_operator_hidden_from_other_agent(
    client: AsyncClient, auth_headers
):
    """A ning shaxsiy operatori B ning ro'yxatida BO'LMASLIGI kerak."""
    created = await client.post(
        "/api/operators",
        headers=auth_headers,
        json={"name": "Mahalliy Operator", "website": "https://example.uz"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_catalog"] is False

    other = await _make_second_agent(client)
    response = await client.get("/api/operators", headers=other)
    assert response.status_code == 200
    assert "mahalliy-operator" not in [o["slug"] for o in response.json()]


@pytest.mark.asyncio
async def test_two_agents_may_use_same_operator_name(client: AsyncClient, auth_headers):
    """Unikal cheklov (company_id, slug) — nom to'qnashmasin."""
    first = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy"}
    )
    assert first.status_code == 201

    other = await _make_second_agent(client)
    second = await client.post(
        "/api/operators", headers=other, json={"name": "Mahalliy"}
    )
    assert second.status_code == 201, second.text


@pytest.mark.asyncio
async def test_duplicate_name_rejected_within_one_agent(
    client: AsyncClient, auth_headers
):
    await client.post("/api/operators", headers=auth_headers, json={"name": "Mahalliy"})
    again = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy"}
    )
    assert again.status_code == 409


# --------------------------------------------------------------------------
# Hisoblarga kirish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cannot_add_account_to_foreign_operator(
    client: AsyncClient, auth_headers
):
    """B, A ning shaxsiy operatoriga hisob qo'sha olmasin."""
    created = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy Operator"}
    )
    operator_id = created.json()["id"]

    other = await _make_second_agent(client)
    response = await client.put(
        f"/api/operators/{operator_id}/account",
        headers=other,
        json={"login": "buzgunchi@mail.uz", "password": "parol"},
    )
    assert response.status_code == 404, "begona operator ko'rinib qoldi"


@pytest.mark.asyncio
async def test_accounts_do_not_leak_between_agents(client: AsyncClient, auth_headers):
    """Ikkalasi ham katalogdagi bir operatorga ulanadi — aralashmasin."""
    operator_id = await _add_catalog_operator()

    a = await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent-a@mail.uz", "password": "A-paroli"},
    )
    assert a.status_code == 200, a.text

    other = await _make_second_agent(client)
    b = await client.put(
        f"/api/operators/{operator_id}/account",
        headers=other,
        json={"login": "agent-b@mail.uz", "password": "B-paroli"},
    )
    assert b.status_code == 200, b.text

    # Har biri FAQAT o'z hisobini ko'rsin.
    a_list = (await client.get("/api/operators", headers=auth_headers)).json()
    b_list = (await client.get("/api/operators", headers=other)).json()
    a_account = next(o for o in a_list if o["id"] == operator_id)["account"]
    b_account = next(o for o in b_list if o["id"] == operator_id)["account"]

    assert a_account["login_masked"].startswith("ag")
    assert a_account["id"] != b_account["id"], "bir xil hisob ko'rsatilyapti"

    async with TestSessionLocal() as db:
        rows = (await db.execute(select(OperatorAccount))).scalars().all()
        assert len(rows) == 2
        logins = {crypto.decrypt(r.login_enc) for r in rows}
        assert logins == {"agent-a@mail.uz", "agent-b@mail.uz"}


# --------------------------------------------------------------------------
# Parol oshkor bo'lmasligi
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_password_never_returned_by_api(client: AsyncClient, auth_headers):
    operator_id = await _add_catalog_operator()
    response = await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "JudaMaxfiyParol"},
    )
    assert response.status_code == 200
    assert "JudaMaxfiyParol" not in response.text
    assert response.json()["has_password"] is True

    listing = await client.get("/api/operators", headers=auth_headers)
    assert "JudaMaxfiyParol" not in listing.text
    assert "agent@mail.uz" not in listing.text, "login to'liq ko'rinib qoldi"


@pytest.mark.asyncio
async def test_password_stored_encrypted(client: AsyncClient, auth_headers):
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "JudaMaxfiyParol"},
    )
    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        assert "JudaMaxfiyParol" not in (account.password_enc or "")
        assert crypto.decrypt(account.password_enc) == "JudaMaxfiyParol"


# --------------------------------------------------------------------------
# O'chirish — maxfiy ma'lumot ketadi, yozuv qoladi
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clear_account_removes_secrets_but_keeps_row(
    client: AsyncClient, auth_headers
):
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "parol"},
    )

    response = await client.delete(
        f"/api/operators/{operator_id}/account", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["has_password"] is False

    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        assert account.password_enc is None
        assert account.login_enc is None
        assert account.id is not None, "yozuv o'chib ketmasin (audit)"


@pytest.mark.asyncio
async def test_cannot_clear_foreign_account(client: AsyncClient, auth_headers):
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent-a@mail.uz", "password": "parol"},
    )

    other = await _make_second_agent(client)
    response = await client.delete(
        f"/api/operators/{operator_id}/account", headers=other
    )
    assert response.status_code == 404, "begona hisob o'chirildi!"

    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        assert account.password_enc is not None, "A ning paroli o'chib ketdi"


# --------------------------------------------------------------------------
# Sessiya
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_updating_password_invalidates_session(
    client: AsyncClient, auth_headers
):
    """Parol almashsa saqlangan cookie ishonchsiz — tozalanishi kerak."""
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "eski"},
    )
    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        account.session_enc = crypto.encrypt('{"cookies": []}')
        await db.commit()

    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "yangi"},
    )
    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        assert account.session_enc is None


# --------------------------------------------------------------------------
# Ruxsat
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Vaqtincha to'xtatish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_toggle_account_off_and_on(client: AsyncClient, auth_headers):
    """Agent hisobni qidiruvdan vaqtincha chiqara olsin — parolni
    o'chirmasdan."""
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent@mail.uz", "password": "parol"},
    )

    off = await client.patch(
        f"/api/operators/{operator_id}/account?is_enabled=false",
        headers=auth_headers,
    )
    assert off.status_code == 200, off.text
    assert off.json()["is_enabled"] is False
    assert off.json()["has_password"] is True, "parol o'chib ketmasin"

    on = await client.patch(
        f"/api/operators/{operator_id}/account?is_enabled=true",
        headers=auth_headers,
    )
    assert on.json()["is_enabled"] is True
    assert on.json()["status"] != "ochirilgan"


@pytest.mark.asyncio
async def test_cannot_toggle_foreign_account(client: AsyncClient, auth_headers):
    operator_id = await _add_catalog_operator()
    await client.put(
        f"/api/operators/{operator_id}/account",
        headers=auth_headers,
        json={"login": "agent-a@mail.uz", "password": "parol"},
    )

    other = await _make_second_agent(client)
    response = await client.patch(
        f"/api/operators/{operator_id}/account?is_enabled=false", headers=other
    )
    assert response.status_code == 404, "begona hisob o'chirildi!"

    async with TestSessionLocal() as db:
        account = (await db.execute(select(OperatorAccount))).scalar_one()
        assert account.is_enabled is True, "A ning hisobi to'xtatildi"


@pytest.mark.asyncio
async def test_toggle_without_account_is_404(client: AsyncClient, auth_headers):
    operator_id = await _add_catalog_operator()
    response = await client.patch(
        f"/api/operators/{operator_id}/account?is_enabled=false", headers=auth_headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Konnektor retsepti
# --------------------------------------------------------------------------
VALID_RECIPE = {
    "search_url": "https://op.uz/search",
    "fields": {"destination": "#city"},
    "row": ".hotel-card",
    "row_fields": {"hotel_name": ".name", "price_gross": ".price"},
}


@pytest.mark.asyncio
async def test_agent_can_edit_own_operator_recipe(client: AsyncClient, auth_headers):
    created = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy"}
    )
    operator_id = created.json()["id"]

    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": VALID_RECIPE},
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_recipe"] is True
    assert response.json()["connector_config"]["row"] == ".hotel-card"


@pytest.mark.asyncio
async def test_agent_cannot_edit_catalog_recipe(client: AsyncClient, auth_headers):
    """Katalog retsepti BARCHA turagentga ta'sir qiladi.

    Bitta agent uni buzsa hammasining qidiruvi to'xtardi — shuning uchun
    faqat superadmin tahrirlaydi.
    """
    operator_id = await _add_catalog_operator()
    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": VALID_RECIPE},
    )
    assert response.status_code == 403

    async with TestSessionLocal() as db:
        operator = (
            await db.execute(
                select(TourOperator).where(TourOperator.id == operator_id)
            )
        ).scalar_one()
        assert operator.connector_config is None, "katalog retsepti o'zgardi!"


@pytest.mark.asyncio
async def test_catalog_recipe_not_editable_flag(client: AsyncClient, auth_headers):
    """UI tugmani ko'rsatmasligi uchun bayroq to'g'ri kelsin."""
    await _add_catalog_operator()
    await client.post("/api/operators", headers=auth_headers, json={"name": "Mahalliy"})

    listing = (await client.get("/api/operators", headers=auth_headers)).json()
    catalog = next(o for o in listing if o["is_catalog"])
    private = next(o for o in listing if not o["is_catalog"])

    assert catalog["can_edit_recipe"] is False
    assert private["can_edit_recipe"] is True


@pytest.mark.asyncio
async def test_incomplete_recipe_rejected(client: AsyncClient, auth_headers):
    """Yaroqsiz retsept saqlanmasin — agent uni to'g'ri deb o'ylab,
    qidiruv jimgina ishlamay turardi."""
    created = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy"}
    )
    operator_id = created.json()["id"]

    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": {"search_url": "https://op.uz", "fields": {}}},
    )
    assert response.status_code == 400
    assert "row" in response.json()["detail"]


@pytest.mark.asyncio
async def test_empty_config_clears_recipe(client: AsyncClient, auth_headers):
    created = await client.post(
        "/api/operators", headers=auth_headers, json={"name": "Mahalliy"}
    )
    operator_id = created.json()["id"]
    await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": VALID_RECIPE},
    )

    cleared = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": {}},
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_recipe"] is False


@pytest.mark.asyncio
async def test_cannot_edit_recipe_of_foreign_operator(
    client: AsyncClient, auth_headers
):
    other = await _make_second_agent(client)
    created = await client.post(
        "/api/operators", headers=other, json={"name": "Begona"}
    )
    operator_id = created.json()["id"]

    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=auth_headers,
        json={"config": VALID_RECIPE},
    )
    assert response.status_code == 404


async def _superadmin_headers() -> dict:
    """Superadmin sarlavhalari. U firmaga biriktirilmagan."""
    async with TestSessionLocal() as db:
        user = (
            await db.execute(
                select(User).where(User.role == UserRole.SUPERADMIN)
            )
        ).scalar_one()
        return {
            "Authorization": f"Bearer {create_access_token(_token_claims(user))}"
        }


@pytest.mark.asyncio
async def test_superadmin_can_edit_catalog_recipe(client: AsyncClient):
    """Katalog retseptini superadmin tahrirlay olishi SHART.

    Aks holda katalogdagi operatorlar uchun avtomatik qidiruvni hech kim
    sozlay olmaydi — agent ham (403), superadmin ham (rol tekshiruvida).
    """
    operator_id = await _add_catalog_operator()
    headers = await _superadmin_headers()

    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=headers,
        json={"config": VALID_RECIPE},
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_recipe"] is True

    async with TestSessionLocal() as db:
        operator = (
            await db.execute(
                select(TourOperator).where(TourOperator.id == operator_id)
            )
        ).scalar_one()
        assert operator.connector_config is not None


@pytest.mark.asyncio
async def test_superadmin_rejects_incomplete_recipe(client: AsyncClient):
    """Tekshiruv superadmin uchun ham ishlasin."""
    operator_id = await _add_catalog_operator()
    headers = await _superadmin_headers()
    response = await client.put(
        f"/api/operators/{operator_id}/connector",
        headers=headers,
        json={"config": {"submit": "#go"}},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_recipe_not_leaked_to_non_editor(client: AsyncClient, auth_headers):
    """Katalog retsepti tahrirlay olmaydiganga yuborilmasin."""
    await _add_catalog_operator()
    listing = (await client.get("/api/operators", headers=auth_headers)).json()
    catalog = next(o for o in listing if o["is_catalog"])
    assert catalog["connector_config"] is None


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient):
    assert (await client.get("/api/operators")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_taxonomy_endpoint(client: AsyncClient, auth_headers):
    response = await client.get("/api/operators/taxonomy", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["countries"][0]["code"] == "SA", "Saudiya birinchi bo'lishi kerak"
    assert any(c["code"] == "umra" for c in data["categories"])
