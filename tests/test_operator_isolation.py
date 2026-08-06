"""Turagentlar orasidagi ajratilganlik (tenant isolation) testlari.

Eng muhim talab: bir turagentning tur operator ulanishi va topgan narxlari
boshqasiga hech qanday yo'l bilan ko'rinmasin. Operator kabineti login-paroli
va shartnoma narxi — savdo siri; aralashib ketsa bu shunchaki xato emas,
biznesga zarar.

Shuning uchun bu yerda testlar "ishlaydimi" ni emas, "**ajratilganmi**" ni
tekshiradi.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, CompanyStatus
from app.models.tour_offer import OfferSource, OperatorSearch, TourOffer
from app.models.tour_operator import (
    AccountStatus,
    OperatorAccount,
    OperatorEngine,
    TourOperator,
)
from app.utils import crypto


# --------------------------------------------------------------------------
# Yordamchi
# --------------------------------------------------------------------------
async def _make_company(db: AsyncSession, name: str, slug: str) -> Company:
    company = Company(
        name=name,
        slug=slug,
        city="Toshkent",
        phone="998900000000",
        email=f"{slug}@test.uz",
        status=CompanyStatus.APPROVED,
        tariff="boshlangich",
    )
    db.add(company)
    await db.flush()
    return company


async def _make_operator(db: AsyncSession, slug: str, company_id=None) -> TourOperator:
    operator = TourOperator(
        company_id=company_id,
        name=slug.replace("-", " ").title(),
        slug=slug,
        engine=OperatorEngine.CUSTOM,
    )
    db.add(operator)
    await db.flush()
    return operator


# --------------------------------------------------------------------------
# company_id majburiyligi — ajratishning poydevori
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_account_requires_company(db_session: AsyncSession):
    """Firmasiz hisob yaratib bo'lmasin — aks holda u "hammaniki" bo'lardi."""
    operator = await _make_operator(db_session, "coral")
    db_session.add(OperatorAccount(company_id=None, operator_id=operator.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_offer_requires_company(db_session: AsyncSession):
    """Taklif ham firmasiz bo'lmaydi — narx firmaga bog'liq."""
    db_session.add(TourOffer(company_id=None, hotel_name="Rixos"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_search_requires_company(db_session: AsyncSession):
    db_session.add(OperatorSearch(company_id=None, destination="Antalya"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Ikki turagent — bir operator
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_two_agents_same_operator_no_clash(db_session: AsyncSession):
    """Ikki turagent AYNAN bir operatorga o'z hisobi bilan ulanishi kerak.

    Bu real holat: Coral bilan o'nlab agentlik ishlaydi, har birining o'z
    login-paroli bor. Unikal cheklov ularni to'qnashtirmasligi shart.
    """
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    b = await _make_company(db_session, "Agentlik B", "agent-b")
    coral = await _make_operator(db_session, "coral")

    db_session.add(
        OperatorAccount(
            company_id=a.id,
            operator_id=coral.id,
            login_enc=crypto.encrypt("agent-a@mail.uz"),
            password_enc=crypto.encrypt("A-paroli"),
        )
    )
    db_session.add(
        OperatorAccount(
            company_id=b.id,
            operator_id=coral.id,
            login_enc=crypto.encrypt("agent-b@mail.uz"),
            password_enc=crypto.encrypt("B-paroli"),
        )
    )
    await db_session.flush()  # to'qnashuv bo'lmasligi kerak

    rows = (await db_session.execute(select(OperatorAccount))).scalars().all()
    assert len(rows) == 2
    await db_session.rollback()


@pytest.mark.asyncio
async def test_same_agent_cannot_duplicate_operator(db_session: AsyncSession):
    """Bitta turagentda bitta operatorga ikkita hisob bo'lmasin."""
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    coral = await _make_operator(db_session, "coral")

    db_session.add(OperatorAccount(company_id=a.id, operator_id=coral.id))
    await db_session.flush()
    db_session.add(OperatorAccount(company_id=a.id, operator_id=coral.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# --------------------------------------------------------------------------
# So'rov firma bo'yicha filtrlanishi
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_sees_only_own_accounts(db_session: AsyncSession):
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    b = await _make_company(db_session, "Agentlik B", "agent-b")
    coral = await _make_operator(db_session, "coral")
    anex = await _make_operator(db_session, "anex")

    db_session.add_all([
        OperatorAccount(company_id=a.id, operator_id=coral.id),
        OperatorAccount(company_id=a.id, operator_id=anex.id),
        OperatorAccount(company_id=b.id, operator_id=coral.id),
    ])
    await db_session.flush()

    a_rows = (
        await db_session.execute(
            select(OperatorAccount).where(OperatorAccount.company_id == a.id)
        )
    ).scalars().all()
    b_rows = (
        await db_session.execute(
            select(OperatorAccount).where(OperatorAccount.company_id == b.id)
        )
    ).scalars().all()

    assert len(a_rows) == 2
    assert len(b_rows) == 1
    assert all(r.company_id == a.id for r in a_rows)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_agent_sees_only_own_offers(db_session: AsyncSession):
    """Narxlar ham aralashmasin — B ning narxi A ga ko'rinmasin."""
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    b = await _make_company(db_session, "Agentlik B", "agent-b")

    db_session.add_all([
        TourOffer(
            company_id=a.id, hotel_name="Rixos Premium",
            price_gross=520.0, price_net=470.0, source=OfferSource.RPA,
        ),
        TourOffer(
            company_id=b.id, hotel_name="Rixos Premium",
            price_gross=505.0, price_net=440.0, source=OfferSource.RPA,
        ),
    ])
    await db_session.flush()

    a_offers = (
        await db_session.execute(
            select(TourOffer).where(TourOffer.company_id == a.id)
        )
    ).scalars().all()

    assert len(a_offers) == 1
    assert a_offers[0].price_gross == 520.0, "B ning narxi A ga sizib chiqdi"
    await db_session.rollback()


# --------------------------------------------------------------------------
# Katalog va shaxsiy operator
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_catalog_vs_private_operator(db_session: AsyncSession):
    """`company_id IS NULL` — umumiy katalog; to'ldirilgan — shaxsiy."""
    a = await _make_company(db_session, "Agentlik A", "agent-a")

    catalog = await _make_operator(db_session, "coral")           # umumiy
    private = await _make_operator(db_session, "mahalliy-operator", company_id=a.id)

    assert catalog.is_catalog is True
    assert private.is_catalog is False

    # A ko'radigan ro'yxat: katalog + o'ziniki
    visible = (
        await db_session.execute(
            select(TourOperator).where(
                (TourOperator.company_id.is_(None))
                | (TourOperator.company_id == a.id)
            )
        )
    ).scalars().all()
    assert {o.slug for o in visible} == {"coral", "mahalliy-operator"}
    await db_session.rollback()


@pytest.mark.asyncio
async def test_private_operator_hidden_from_other_agent(db_session: AsyncSession):
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    b = await _make_company(db_session, "Agentlik B", "agent-b")
    await _make_operator(db_session, "mahalliy-operator", company_id=a.id)

    visible_to_b = (
        await db_session.execute(
            select(TourOperator).where(
                (TourOperator.company_id.is_(None))
                | (TourOperator.company_id == b.id)
            )
        )
    ).scalars().all()
    assert visible_to_b == [], "A ning shaxsiy operatori B ga ko'rindi"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_two_agents_can_use_same_private_slug(db_session: AsyncSession):
    """Unikal cheklov (company_id, slug) bo'yicha — bir xil nom to'qnashmasin."""
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    b = await _make_company(db_session, "Agentlik B", "agent-b")
    await _make_operator(db_session, "mahalliy", company_id=a.id)
    await _make_operator(db_session, "mahalliy", company_id=b.id)
    await db_session.flush()  # to'qnashmasligi kerak
    await db_session.rollback()


# --------------------------------------------------------------------------
# Parol shifrlash
# --------------------------------------------------------------------------
def test_credentials_roundtrip():
    secret = "MeningKuchliParolim!2026"
    enc = crypto.encrypt(secret)
    assert enc != secret, "shifrlanmagan"
    assert secret not in enc
    assert crypto.decrypt(enc) == secret


def test_credentials_ciphertext_differs_each_time():
    """Fernet tasodifiy IV ishlatadi — bir xil parol har safar boshqa shifr."""
    a, b = crypto.encrypt("bir xil parol"), crypto.encrypt("bir xil parol")
    assert a != b
    assert crypto.decrypt(a) == crypto.decrypt(b) == "bir xil parol"


def test_decrypt_garbage_returns_none():
    """Kalit almashsa ilova yiqilmasin, `None` qaytsin."""
    assert crypto.decrypt("buzuq-shifr-matni") is None


def test_encrypt_empty_passthrough():
    assert crypto.encrypt("") == ""
    assert crypto.encrypt(None) is None
    assert crypto.decrypt(None) is None


def test_mask_never_reveals_full_value():
    masked = crypto.mask("SuperMaxfiyParol123")
    assert "SuperMaxfiyParol123" not in masked
    assert masked.startswith("Su")
    assert "•" in masked


@pytest.mark.asyncio
async def test_password_not_stored_in_plaintext(db_session: AsyncSession):
    """Bazadagi xom qiymatda parol ochiq ko'rinmasin."""
    a = await _make_company(db_session, "Agentlik A", "agent-a")
    coral = await _make_operator(db_session, "coral")
    account = OperatorAccount(
        company_id=a.id,
        operator_id=coral.id,
        login_enc=crypto.encrypt("agent@mail.uz"),
        password_enc=crypto.encrypt("OchiqParol123"),
        status=AccountStatus.NEW,
    )
    db_session.add(account)
    await db_session.flush()

    assert "OchiqParol123" not in (account.password_enc or "")
    assert "agent@mail.uz" not in (account.login_enc or "")
    assert crypto.decrypt(account.password_enc) == "OchiqParol123"
    await db_session.rollback()


# --------------------------------------------------------------------------
# Yordamchi xossalar
# --------------------------------------------------------------------------
def test_agent_margin():
    offer = TourOffer(company_id=1, hotel_name="X", price_gross=520.0, price_net=470.0)
    assert offer.agent_margin == 50.0


def test_agent_margin_none_when_incomplete():
    assert TourOffer(company_id=1, hotel_name="X", price_gross=520.0).agent_margin is None


def test_account_usable_flags():
    ok = OperatorAccount(company_id=1, operator_id=1, status=AccountStatus.OK)
    blocked = OperatorAccount(
        company_id=1, operator_id=1, status=AccountStatus.BLOCKED
    )
    assert ok.is_usable is True
    assert blocked.is_usable is False
