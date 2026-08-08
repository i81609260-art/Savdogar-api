"""Tur operatorlar va turagentning ulardagi hisoblari.

Bu routerdagi HAR BIR so'rov `current_user.company_id` bo'yicha filtrlanadi.
Sabab qat'iy: operator kabinetidagi login-parol va shartnoma narxi — savdo
siri. Bir turagentniki boshqasiga ko'rinsa bu shunchaki xato emas, zarar.

Ko'rinish qoidasi
-----------------
Turagent ko'radi:
  * `company_id IS NULL` — platforma katalogi (Coral, Anex, ...);
  * `company_id = o'ziniki` — o'zi qo'shgan operatorlar.
Boshqa turagentning shaxsiy operatori hech qanday yo'l bilan ko'rinmaydi.

Parollar
--------
Bazaga faqat shifrlangan holda yoziladi va API javobida **hech qachon**
ochiq qaytmaydi — faqat niqoblangan ko'rinish (`is••••@mail.uz`).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.tour_operator import (
    AccountStatus,
    OperatorAccount,
    OperatorEngine,
    TourOperator,
)
from app.models.user import User, UserRole
from app.services.browser_runner import BrowserUnavailable, run_in_browser
from app.services.operator_connector import (
    ConnectorContext,
    ConnectorStatus,
    registry,
)
from app.services.playwright_connector import SearchRecipe, build_connector
from app.services.tella_tour_search import TourSearchQuery
from app.services.tour_taxonomy import taxonomy_snapshot
from app.utils import crypto
from app.utils.slug import slugify

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/operators", tags=["Tur operatorlar"])

# Ko'rish — admin va operator; o'zgartirish — faqat admin (maxfiy ma'lumot).
_READ = role_required(UserRole.ADMIN, UserRole.OPERATOR)
_WRITE = role_required(UserRole.ADMIN)
# Konnektor retseptiga superadmin ham kirishi kerak: katalog operatorlarini
# faqat u sozlaydi. `_WRITE` ni ishlatsak superadmin rol tekshiruvidayoq
# 403 olardi va katalog retseptini HECH KIM tahrirlay olmasdi.
_RECIPE_WRITE = role_required(UserRole.ADMIN, UserRole.SUPERADMIN)


# --------------------------------------------------------------------------
# Sxemalar
# --------------------------------------------------------------------------
class OperatorIn(BaseModel):
    """Turagent o'z shaxsiy operatorini qo'shadi."""

    name: str = Field(min_length=2, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    login_url: Optional[str] = Field(default=None, max_length=500)
    engine: str = OperatorEngine.CUSTOM


class AccountIn(BaseModel):
    """Operator kabinetidagi hisob."""

    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class AccountOut(BaseModel):
    """Hisob holati. Parol HECH QACHON bu yerda qaytmaydi."""

    id: int
    login_masked: Optional[str] = None
    has_password: bool = False
    has_session: bool = False
    status: str
    is_enabled: bool
    last_ok_at: Optional[datetime] = None
    last_error: Optional[str] = None


class ConnectorIn(BaseModel):
    """Konnektor retsepti — qaysi maydonga nima yozish, natijani qayerdan
    o'qish. Kod emas, ma'lumot."""

    config: dict


class OperatorOut(BaseModel):
    id: int
    name: str
    slug: str
    website: Optional[str] = None
    login_url: Optional[str] = None
    engine: str
    is_catalog: bool
    # Bu dvigatel uchun konnektor bormi — UI "avtomatik qidiruv mumkin"
    # belgisini shunga qarab ko'rsatadi.
    connector_available: bool = False
    # Retsept to'ldirilganmi va uni shu foydalanuvchi tahrirlay oladimi.
    has_recipe: bool = False
    can_edit_recipe: bool = False
    connector_config: Optional[dict] = None
    account: Optional[AccountOut] = None


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------
def _visible_operators_stmt(company_id: int):
    """Shu turagent ko'ra oladigan operatorlar.

    Katalog (`company_id IS NULL`) + o'ziniki. Boshqa turagentniki EMAS.
    """
    return select(TourOperator).where(
        TourOperator.is_active.is_(True),
        or_(
            TourOperator.company_id.is_(None),
            TourOperator.company_id == company_id,
        ),
    )


async def _get_visible_operator(
    db: AsyncSession, company_id: int, operator_id: int
) -> TourOperator:
    """Operatorni oladi, ko'rinish huquqini tekshiradi.

    Topilmasa ham, begona bo'lsa ham bir xil 404 — mavjudligini oshkor
    qilmaslik uchun (boshqa turagentda qanday operator borligini bilib
    olish ham ortiqcha ma'lumot).
    """
    result = await db.execute(
        _visible_operators_stmt(company_id).where(TourOperator.id == operator_id)
    )
    operator = result.scalar_one_or_none()
    if operator is None:
        raise HTTPException(status_code=404, detail="Operator topilmadi")
    return operator


async def _get_account(
    db: AsyncSession, company_id: int, operator_id: int
) -> Optional[OperatorAccount]:
    """Shu turagentning shu operatordagi hisobi."""
    result = await db.execute(
        select(OperatorAccount).where(
            OperatorAccount.company_id == company_id,
            OperatorAccount.operator_id == operator_id,
        )
    )
    return result.scalar_one_or_none()


def _account_out(account: Optional[OperatorAccount]) -> Optional[AccountOut]:
    if account is None:
        return None
    return AccountOut(
        id=account.id,
        login_masked=crypto.mask(crypto.decrypt(account.login_enc)),
        has_password=bool(account.password_enc),
        has_session=account.has_session,
        status=account.status,
        is_enabled=bool(account.is_enabled),
        last_ok_at=account.last_ok_at,
        last_error=account.last_error,
    )



def _load_session(account: OperatorAccount) -> Optional[dict]:
    """Saqlangan brauzer seansini ochadi.

    Buzuq yoki eski seans butun kirishni yiqitmasligi kerak — bunday holda
    shunchaki seanssiz, oddiy login yo'li bilan davom etamiz.
    """
    if not account.session_enc:
        return None
    try:
        return json.loads(crypto.decrypt(account.session_enc) or "")
    except Exception:  # noqa: BLE001
        log.info("Saqlangan seans o'qilmadi (account=%s) — qaytadan kiramiz", account.id)
        return None

def _can_edit_recipe(operator: TourOperator, user: User) -> bool:
    """Retseptni kim tahrirlay oladi.

    Katalog operatorining retsepti BARCHA turagentga ta'sir qiladi —
    bittasi buzsa hammasining qidiruvi to'xtardi. Shuning uchun uni faqat
    superadmin tahrirlaydi. O'z shaxsiy operatorini esa firma admini
    o'zi sozlaydi.
    """
    if user.role == UserRole.SUPERADMIN:
        return True
    return (not operator.is_catalog) and user.role == UserRole.ADMIN


def _parse_config(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _operator_out(
    operator: TourOperator, account: Optional[OperatorAccount], user: User
) -> OperatorOut:
    config = _parse_config(operator.connector_config)
    editable = _can_edit_recipe(operator, user)
    return OperatorOut(
        id=operator.id,
        name=operator.name,
        slug=operator.slug,
        website=operator.website,
        login_url=operator.login_url,
        engine=operator.engine,
        is_catalog=operator.is_catalog,
        connector_available=registry.supports(operator.engine),
        has_recipe=SearchRecipe.from_json(config).is_usable,
        can_edit_recipe=editable,
        # Retsept maxfiy emas, lekin uni faqat tahrirlay oladiganga
        # yuboramiz — ortiqcha ma'lumot ortiqcha yuk.
        connector_config=config if editable else None,
        account=_account_out(account),
    )


# --------------------------------------------------------------------------
# Ma'lumotnoma
# --------------------------------------------------------------------------
@router.get("/taxonomy", summary="Kategoriyalar ma'lumotnomasi")
async def get_taxonomy(current_user: User = Depends(_READ)) -> dict:
    """Davlat, kurort, toifa, ovqat, yulduz ro'yxati (UI bir marta yuklaydi)."""
    return taxonomy_snapshot()


# --------------------------------------------------------------------------
# Operatorlar
# --------------------------------------------------------------------------
@router.get("", summary="Operatorlar ro'yxati")
async def list_operators(
    current_user: User = Depends(_READ),
    db: AsyncSession = Depends(get_db),
) -> list[OperatorOut]:
    """Katalog + shu turagentning shaxsiy operatorlari, hisob holati bilan."""
    cid = current_user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    operators = (await db.execute(_visible_operators_stmt(cid))).scalars().all()

    accounts = (
        await db.execute(
            select(OperatorAccount).where(OperatorAccount.company_id == cid)
        )
    ).scalars().all()
    by_operator = {a.operator_id: a for a in accounts}

    return [_operator_out(o, by_operator.get(o.id), current_user) for o in operators]


@router.post("", status_code=201, summary="Shaxsiy operator qo'shish")
async def create_operator(
    payload: OperatorIn,
    current_user: User = Depends(_WRITE),
    db: AsyncSession = Depends(get_db),
) -> OperatorOut:
    """Katalogda yo'q operatorni qo'shadi — faqat shu turagentga ko'rinadi."""
    cid = current_user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    slug = slugify(payload.name)
    # Unikal cheklov (company_id, slug) — bir turagent ichida takrorlanmasin.
    # Boshqa turagentda yoki katalogda bir xil slug bo'lishi mumkin va normal.
    existing = (
        await db.execute(
            select(TourOperator).where(
                TourOperator.company_id == cid, TourOperator.slug == slug
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Bunday operator allaqachon bor")

    operator = TourOperator(
        company_id=cid,
        name=payload.name.strip(),
        slug=slug,
        website=payload.website,
        login_url=payload.login_url,
        engine=payload.engine,
        created_by=current_user.id,
    )
    db.add(operator)
    await db.flush()
    return _operator_out(operator, None, current_user)


# --------------------------------------------------------------------------
# Konnektor retsepti
# --------------------------------------------------------------------------
@router.put("/{operator_id}/connector", summary="Konnektor retseptini saqlash")
async def save_connector(
    operator_id: int,
    payload: ConnectorIn,
    current_user: User = Depends(_RECIPE_WRITE),
    db: AsyncSession = Depends(get_db),
) -> OperatorOut:
    """Qidiruv retseptini saqlaydi.

    Katalog operatorini faqat superadmin tahrirlaydi — uning retsepti
    barcha turagentga ta'sir qiladi va bittasi buzsa hammasining qidiruvi
    to'xtardi.
    """
    cid = current_user.company_id

    if current_user.role == UserRole.SUPERADMIN:
        # Superadmin firmaga biriktirilmagan — ko'rinish filtri o'rniga
        # to'g'ridan-to'g'ri olamiz.
        operator = (
            await db.execute(
                select(TourOperator).where(TourOperator.id == operator_id)
            )
        ).scalar_one_or_none()
        if operator is None:
            raise HTTPException(status_code=404, detail="Operator topilmadi")
    else:
        if not cid:
            raise HTTPException(
                status_code=400, detail="Kompaniyaga biriktirilmagansiz"
            )
        operator = await _get_visible_operator(db, cid, operator_id)

    if not _can_edit_recipe(operator, current_user):
        raise HTTPException(
            status_code=403,
            detail="Katalogdagi operator retseptini faqat superadmin o'zgartiradi",
        )

    # Yaroqsiz retsept saqlanmasin: agent uni to'g'ri deb o'ylab, qidiruv
    # jimgina ishlamay turardi.
    recipe = SearchRecipe.from_json(payload.config)
    if payload.config and not recipe.is_usable:
        raise HTTPException(
            status_code=400,
            detail=(
                "Retsept to'liq emas: natija qatori (`row`) va undagi "
                "mehmonxona nomi (`row_fields.hotel_name`) ko'rsatilishi shart"
            ),
        )

    operator.connector_config = json.dumps(payload.config) if payload.config else None
    await db.flush()

    account = await _get_account(db, cid, operator_id) if cid else None
    return _operator_out(operator, account, current_user)


# --------------------------------------------------------------------------
# Hisoblar (login/parol)
# --------------------------------------------------------------------------
@router.put("/{operator_id}/account", summary="Hisob qo'shish yoki yangilash")
async def upsert_account(
    operator_id: int,
    payload: AccountIn,
    current_user: User = Depends(_WRITE),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Operator kabinetidagi login-parolni saqlaydi (shifrlangan holda)."""
    cid = current_user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    await _get_visible_operator(db, cid, operator_id)

    account = await _get_account(db, cid, operator_id)
    if account is None:
        account = OperatorAccount(
            company_id=cid, operator_id=operator_id, created_by=current_user.id
        )
        db.add(account)

    account.login_enc = crypto.encrypt(payload.login.strip())
    account.password_enc = crypto.encrypt(payload.password)
    # Parol almashdi — eski sessiya endi ishonchsiz.
    account.session_enc = None
    account.session_expires_at = None
    account.status = AccountStatus.NEW
    account.last_error = None
    account.is_enabled = True

    await db.flush()
    return _account_out(account)


@router.patch("/{operator_id}/account", summary="Hisobni yoqish/o'chirish")
async def toggle_account(
    operator_id: int,
    is_enabled: bool,
    current_user: User = Depends(_WRITE),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Hisobni qidiruvdan vaqtincha chiqaradi yoki qaytaradi."""
    cid = current_user.company_id
    account = await _get_account(db, cid, operator_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Hisob topilmadi")

    account.is_enabled = is_enabled
    if not is_enabled:
        account.status = AccountStatus.DISABLED
    elif account.status == AccountStatus.DISABLED:
        account.status = AccountStatus.NEW
    await db.flush()
    return _account_out(account)


@router.delete("/{operator_id}/account", summary="Hisob ma'lumotlarini o'chirish")
async def clear_account(
    operator_id: int,
    current_user: User = Depends(_WRITE),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Login, parol va sessiyani o'chiradi.

    Yozuvning O'ZI qoladi — qachon kim qo'shgani (audit) va tarixdagi
    qidiruvlarning bog'lanishi saqlanishi kerak. Ya'ni maxfiy ma'lumot
    yo'qoladi, tarix yo'qolmaydi.
    """
    cid = current_user.company_id
    account = await _get_account(db, cid, operator_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Hisob topilmadi")

    account.login_enc = None
    account.password_enc = None
    account.session_enc = None
    account.session_expires_at = None
    account.is_enabled = False
    account.status = AccountStatus.DISABLED
    account.last_error = None
    await db.flush()
    return _account_out(account)


# --------------------------------------------------------------------------
# Kabinetga kirishni tekshirish
# --------------------------------------------------------------------------
# Bu endpoint yetishmayotgan bo'g'in edi. `PlaywrightConnector` login
# mantiqini biladi, `browser_runner` brauzer ochadi — lekin ularni HECH KIM
# birlashtirmasdi. Turagent kabinet manzili va login-parolni kiritardi,
# ular shifrlanib saqlanardi va shu bilan tamom: hech qayerga kirilmasdi,
# hisob holati abadiy "yangi" (sinalmagan) bo'lib qolardi.
#
# Retsept SHART EMAS. Kirish uchun faqat kabinet manzili va login-parol
# kerak; retsept keyinroq, avtomatik QIDIRUV uchun kerak bo'ladi.
_STATUS_BY_CONNECTOR: dict[ConnectorStatus, AccountStatus] = {
    ConnectorStatus.OK: AccountStatus.OK,
    ConnectorStatus.AUTH_FAILED: AccountStatus.AUTH_FAILED,
    ConnectorStatus.CAPTCHA: AccountStatus.CAPTCHA,
}

_MESSAGE_BY_STATUS: dict[AccountStatus, str] = {
    AccountStatus.OK: "Kabinetga muvaffaqiyatli kirildi.",
    AccountStatus.AUTH_FAILED: (
        "Login yoki parol qabul qilinmadi. Kabinetga brauzerdan kirib "
        "tekshiring va qayta kiriting."
    ),
    AccountStatus.CAPTCHA: (
        "Operator sayti captcha so'rayapti — serverdagi brauzer uni "
        "o'tolmaydi. Kabinetga o'zingiz kirib captchani bosing, keyin "
        "qaytadan urinib ko'ring."
    ),
    AccountStatus.BLOCKED: (
        "Kabinet ochilmadi yoki javob bermadi. Manzil to'g'riligini "
        "tekshiring."
    ),
}


class LoginTestOut(BaseModel):
    ok: bool
    status: AccountStatus
    message: str
    account: Optional[AccountOut] = None


@router.post("/{operator_id}/login-test", summary="Kabinetga kirishni tekshirish")
async def test_login(
    operator_id: int,
    current_user: User = Depends(_WRITE),
    db: AsyncSession = Depends(get_db),
) -> LoginTestOut:
    """Saqlangan login-parol bilan operator kabinetiga haqiqatan kiradi."""
    cid = current_user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    operator = await _get_visible_operator(db, cid, operator_id)
    account = await _get_account(db, cid, operator_id)
    if account is None or not account.password_enc:
        raise HTTPException(
            status_code=400,
            detail="Avval kabinet login va parolini kiriting",
        )

    login_url = operator.login_url or operator.website
    if not login_url:
        raise HTTPException(
            status_code=400,
            detail="Operatorda B2B kabinet manzili ko'rsatilmagan",
        )

    connector = build_connector(operator.connector_config)
    ctx = ConnectorContext(
        query=TourSearchQuery(),          # login uchun so'rov kerak emas
        login=crypto.decrypt(account.login_enc),
        password=crypto.decrypt(account.password_enc),
        login_url=login_url,
        storage_state=_load_session(account),
    )

    async def _do(page: Any) -> ConnectorStatus:
        ctx.page = page
        return await connector.login(ctx)

    try:
        outcome = await run_in_browser(_do, storage_state=ctx.storage_state)
        conn_status: ConnectorStatus = outcome.value
    except BrowserUnavailable as exc:
        # Bu sozlash muammosi, turagentning parolida emas — hisob holatini
        # "parol xato" deb belgilab qo'yish noto'g'ri bo'lardi.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("Kabinetga kirish uzildi (operator=%s): %s", operator_id, exc)
        account.status = AccountStatus.BLOCKED
        account.last_error = str(exc)[:500]
        await db.flush()
        return LoginTestOut(
            ok=False,
            status=AccountStatus.BLOCKED,
            message=_MESSAGE_BY_STATUS[AccountStatus.BLOCKED],
            account=_account_out(account),
        )

    status = _STATUS_BY_CONNECTOR.get(conn_status, AccountStatus.BLOCKED)
    account.status = status

    if status is AccountStatus.OK:
        account.last_ok_at = datetime.now(timezone.utc)
        account.last_error = None
        # Seansni saqlaymiz — keyingi safar login formasi ochilmaydi va
        # operator sayti takror kirishlarni ko'rmaydi.
        account.session_enc = crypto.encrypt(json.dumps(outcome.storage_state))
    else:
        account.last_error = _MESSAGE_BY_STATUS.get(status)

    await db.flush()
    return LoginTestOut(
        ok=status is AccountStatus.OK,
        status=status,
        message=_MESSAGE_BY_STATUS.get(status, "Noma'lum natija."),
        account=_account_out(account),
    )
