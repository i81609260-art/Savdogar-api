"""Instagram (Meta) integratsiyasi — DM va izohlardan pipeline lead yigish.

Oqim:
  1. Admin oz Facebook Page tokenini ulaydi (/api/admin/instagram/connect).
     Server Page ga bogliq Instagram Business akkauntni topib, webhook'ga
     obuna boladi.
  2. Mijoz Instagram DM yozadi yoki postga izoh qoldiradi.
  3. Meta webhook'ni chaqiradi -> Tella AI javob berib, ism/telefon/yonalishni
     ketma-ket soraydi.
  4. Telefon olingach pipeline'da lead (tour_requests, source="instagram")
     yaratiladi va kompaniya xodimlariga bildirishnoma ketadi.

Xavfsizlik: har bir webhook so'rovi X-Hub-Signature-256 orqali App Secret
bilan tekshiriladi — imzosiz yoki notogri imzoli so'rov rad etiladi.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.instagram import InstagramAccount, InstagramThread
from app.models.request import TourRequest
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)
settings = get_settings()

admin_router = APIRouter(prefix="/api/admin/instagram", tags=["Instagram"])
webhook_router = APIRouter(prefix="/api/instagram", tags=["Instagram Webhooks"])


# Ikki xil Meta yoli — har birining oz hosti bor.
IG_HOST = "https://graph.instagram.com"   # Instagram login
FB_HOST = "https://graph.facebook.com"    # Facebook login


def _host(login_type: Optional[str]) -> str:
    return IG_HOST if (login_type or "instagram") == "instagram" else FB_HOST


def _graph(path: str, host: str = FB_HOST) -> str:
    return f"{host}/{settings.facebook_graph_version}/{path.lstrip('/')}"


async def _get(path: str, token: str, host: str = FB_HOST, **params) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(_graph(path, host), params={"access_token": token, **params})
        try:
            return r.json()
        except ValueError:
            return {"error": {"message": f"Graph API javobi notogri (HTTP {r.status_code})"}}


async def _post(path: str, token: str, host: str = FB_HOST, **data) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(_graph(path, host), params={"access_token": token}, json=data)
        try:
            return r.json()
        except ValueError:
            return {"error": {"message": f"Graph API javobi notogri (HTTP {r.status_code})"}}


def _graph_error(resp: dict) -> Optional[str]:
    err = resp.get("error")
    if not err:
        return None
    if isinstance(err, str):
        return resp.get("error_message") or err
    return err.get("message") or "Graph API xatosi"


# ── Instagram Business Login (OAuth) ──────────────────────────────────────────

IG_AUTH_URL = "https://www.instagram.com/oauth/authorize"
IG_TOKEN_URL = "https://api.instagram.com/oauth/access_token"

# Konsoldagi 1-qadamda qoshilgan ruxsatlar bilan bir xil.
IG_SCOPES = (
    "instagram_business_basic,"
    "instagram_business_manage_messages,"
    "instagram_business_manage_comments"
)


def _make_state(company_id: int) -> str:
    """OAuth state — imzolangan, 15 daqiqa yashaydigan token.

    Qaytish nuqtasida Authorization sarlavhasi bolmaydi (bu brauzer
    yonaltirishi), shuning uchun qaysi kompaniya ulanayotganini AYNAN shu
    imzolangan state aytadi. Imzosiz bolsa istalgan odam ozining Instagram
    akkauntini begona kompaniyaga biriktirib qoyishi mumkin edi.
    """
    payload = {
        "cid": company_id,
        "typ": "ig_oauth",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _read_state(state: str) -> Optional[int]:
    try:
        data = jwt.decode(state, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if data.get("typ") != "ig_oauth":
        return None
    cid = data.get("cid")
    return int(cid) if cid else None


def _front_redirect(status: str, message: str = "") -> RedirectResponse:
    """Admin panelning Integratsiyalar sahifasiga natija bilan qaytaramiz."""
    base = settings.frontend_url.rstrip("/") + "/admin/integrations"
    params = {"instagram": status}
    if message:
        params["msg"] = message[:200]
    return RedirectResponse(url=f"{base}?{urlencode(params)}", status_code=303)


# ── Admin endpointlari ────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    """Access token.

    Instagram login yolida — Instagram User access token.
    Facebook login yolida — Facebook Page access token.
    Qaysi ekani avtomatik aniqlanadi.
    """

    page_access_token: str


async def _resolve_instagram_login(token: str) -> Optional[dict]:
    """graph.instagram.com/me — Instagram login yoli."""
    me = await _get("me", token, host=IG_HOST, fields="user_id,username")
    if _graph_error(me):
        return None
    ig_user_id = me.get("user_id") or me.get("id")
    if not ig_user_id:
        return None
    return {
        "login_type": "instagram",
        "ig_user_id": str(ig_user_id),
        "ig_username": me.get("username"),
        "page_id": None,
        "page_name": None,
    }


async def _resolve_facebook_login(token: str) -> tuple[Optional[dict], Optional[str]]:
    """graph.facebook.com — Page token orqali bogliq IG akkauntni topadi."""
    me = await _get("me", token, host=FB_HOST, fields="id,name")
    if (err := _graph_error(me)):
        return None, err
    page_id = me.get("id")
    if not page_id:
        return None, "Page aniqlanmadi"

    linked = await _get(page_id, token, host=FB_HOST,
                        fields="instagram_business_account{id,username}")
    if (err := _graph_error(linked)):
        return None, err
    iba = linked.get("instagram_business_account") or {}
    if not iba.get("id"):
        return None, ("Bu Facebook Page ga Instagram Business akkaunt ulanmagan. "
                      "Instagram akkauntni Professional (Business) ga otkazib, Page ga bogʻlang.")
    return {
        "login_type": "facebook",
        "ig_user_id": str(iba["id"]),
        "ig_username": iba.get("username"),
        "page_id": page_id,
        "page_name": me.get("name"),
    }, None


@admin_router.get("/status", summary="Instagram ulanish holati")
async def instagram_status(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    acc = (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.company_id == current_user.company_id
        )
    )).scalar_one_or_none()

    # Sozlama tayyorligini ham qaytaramiz — admin nima yetishmayotganini korsin.
    configured = bool(settings.webhook_secrets and settings.instagram_verify_token)
    # "Instagram bilan kirish" tugmasi faqat OAuth sozlangan bolsa korinadi.
    oauth_ready = bool(settings.instagram_app_id and settings.instagram_app_secret)
    if not acc:
        return {
            "connected": False,
            "server_configured": configured,
            "oauth_available": oauth_ready,
        }

    days_left = None
    if acc.token_expires_at:
        delta = acc.token_expires_at - datetime.now(timezone.utc)
        days_left = max(0, delta.days)

    leads = (await db.execute(
        select(func.count(TourRequest.id)).where(
            TourRequest.company_id == current_user.company_id,
            TourRequest.source == "instagram",
        )
    )).scalar() or 0

    return {
        "connected": True,
        "server_configured": configured,
        "oauth_available": oauth_ready,
        "login_type": acc.login_type,
        "ig_username": acc.ig_username,
        "page_name": acc.page_name,
        "webhook_subscribed": acc.webhook_subscribed,
        "is_active": acc.is_active,
        "leads_count": leads,
        "token_days_left": days_left,
        "profile_url": f"https://instagram.com/{acc.ig_username}" if acc.ig_username else None,
    }


@admin_router.get("/login-url", summary="Instagram bilan kirish havolasi")
async def instagram_login_url(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
) -> dict:
    """Admin shu havolaga otadi, Instagram'da ruxsat beradi va qaytadi."""
    if not (settings.instagram_app_id and settings.instagram_app_secret):
        raise HTTPException(
            status_code=503,
            detail="Server tomonda INSTAGRAM_APP_ID va INSTAGRAM_APP_SECRET sozlanmagan.",
        )
    params = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": settings.instagram_oauth_redirect,
        "response_type": "code",
        "scope": IG_SCOPES,
        "state": _make_state(current_user.company_id),
    }
    return {
        "url": f"{IG_AUTH_URL}?{urlencode(params)}",
        "redirect_uri": settings.instagram_oauth_redirect,
    }


@webhook_router.get("/oauth/callback", summary="Instagram OAuth qaytish", include_in_schema=False)
async def instagram_oauth_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Instagram ruxsatdan keyin shu yerga qaytaradi (brauzer yonaltirishi)."""
    q = request.query_params
    if q.get("error"):
        return _front_redirect("error", q.get("error_description") or q["error"])

    code = q.get("code")
    company_id = _read_state(q.get("state") or "")
    if not code or not company_id:
        return _front_redirect("error", "Sorov yaroqsiz yoki muddati otgan. Qaytadan urinib koring.")

    # 1) code -> qisqa muddatli token
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(IG_TOKEN_URL, data={
            "client_id": settings.instagram_app_id,
            "client_secret": settings.instagram_app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": settings.instagram_oauth_redirect,
            "code": code,
        })
        try:
            short = r.json()
        except ValueError:
            short = {"error": f"HTTP {r.status_code}"}
    if (err := _graph_error(short)) or not short.get("access_token"):
        logger.warning("Instagram token almashuvi muvaffaqiyatsiz: %s", short)
        return _front_redirect("error", err or "Token olinmadi")

    ig_user_id = str(short.get("user_id") or "")

    # 2) qisqa -> uzoq muddatli (~60 kun)
    long = await _get("access_token", short["access_token"], host=IG_HOST,
                      grant_type="ig_exchange_token",
                      client_secret=settings.instagram_app_secret)
    token = long.get("access_token") or short["access_token"]
    expires_in = int(long.get("expires_in") or 0)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) if expires_in else None

    # 3) profil maʼlumoti
    me = await _get("me", token, host=IG_HOST, fields="user_id,username")
    ig_user_id = str(me.get("user_id") or me.get("id") or ig_user_id)
    username = me.get("username")
    if not ig_user_id:
        return _front_redirect("error", "Instagram akkaunt aniqlanmadi")

    # 4) boshqa kompaniya band qilmaganini tekshiramiz
    taken = (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.ig_user_id == ig_user_id,
            InstagramAccount.company_id != company_id,
        )
    )).scalar_one_or_none()
    if taken:
        return _front_redirect("error", "Bu Instagram akkaunt boshqa kompaniyaga ulangan")

    # 5) webhook obunasi
    sub = await _post(f"{ig_user_id}/subscribed_apps", token, host=IG_HOST,
                      subscribed_fields="messages,comments")
    subscribed = bool(sub.get("success"))
    if not subscribed:
        logger.warning("Instagram webhook obunasi ulgurmadi: %s", sub)

    # 6) saqlaymiz
    acc = (await db.execute(
        select(InstagramAccount).where(InstagramAccount.company_id == company_id)
    )).scalar_one_or_none()
    if acc:
        await db.delete(acc)
        await db.flush()
    db.add(InstagramAccount(
        company_id=company_id,
        login_type="instagram",
        ig_user_id=ig_user_id,
        ig_username=username,
        page_id=None,
        page_name=None,
        page_access_token=token,
        token_expires_at=expires_at,
        webhook_subscribed=subscribed,
    ))
    await db.commit()

    return _front_redirect("ok", username or "")


@admin_router.post("/connect", summary="Instagram akkauntni qolda ulash (zaxira)")
async def connect_instagram(
    payload: ConnectRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not settings.webhook_secrets:
        raise HTTPException(
            status_code=503,
            detail="Server tomonda INSTAGRAM_APP_SECRET (yoki FACEBOOK_APP_SECRET) "
                   "sozlanmagan. Administratorga murojaat qiling.",
        )

    token = (payload.page_access_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Access token majburiy")

    # 1) Qaysi yol ekanini avtomatik aniqlaymiz: avval Instagram login,
    #    keyin Facebook login. Admin token turini bilishi shart emas.
    info = await _resolve_instagram_login(token)
    if not info:
        info, err = await _resolve_facebook_login(token)
        if not info:
            raise HTTPException(
                status_code=400,
                detail=f"Token tanilmadi. Instagram User access token yoki Facebook Page "
                       f"access token kiriting. ({err or 'nomaʼlum xato'})",
            )

    ig_user_id = info["ig_user_id"]
    host = _host(info["login_type"])

    # 2) Boshqa kompaniya shu akkauntni ishlatmayotganini tekshiramiz.
    taken = (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.ig_user_id == ig_user_id,
            InstagramAccount.company_id != current_user.company_id,
        )
    )).scalar_one_or_none()
    if taken:
        raise HTTPException(
            status_code=400,
            detail="Bu Instagram akkaunt boshqa kompaniyaga ulangan.",
        )

    # 3) Webhook'ga obuna. Instagram yolida IG akkauntning ozi, Facebook
    #    yolida Page obuna qilinadi.
    target = ig_user_id if info["login_type"] == "instagram" else info["page_id"]
    sub = await _post(
        f"{target}/subscribed_apps",
        token,
        host=host,
        subscribed_fields="messages,comments",
    )
    subscribed = bool(sub.get("success"))
    if not subscribed:
        logger.warning("Instagram webhook obunasi ulgurmadi (%s): %s", info["login_type"], sub)

    # 4) Saqlaymiz (upsert).
    acc = (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.company_id == current_user.company_id
        )
    )).scalar_one_or_none()
    if acc:
        await db.delete(acc)
        await db.flush()

    acc = InstagramAccount(
        company_id=current_user.company_id,
        login_type=info["login_type"],
        ig_user_id=ig_user_id,
        ig_username=info["ig_username"],
        page_id=info["page_id"],
        page_name=info["page_name"],
        page_access_token=token,
        webhook_subscribed=subscribed,
    )
    db.add(acc)
    await db.commit()

    return {
        "connected": True,
        "login_type": info["login_type"],
        "ig_username": acc.ig_username,
        "page_name": info["page_name"],
        "webhook_subscribed": subscribed,
    }


@admin_router.delete("/disconnect", summary="Instagram akkauntni uzish")
async def disconnect_instagram(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    acc = (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.company_id == current_user.company_id
        )
    )).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Instagram akkaunt ulanmagan")

    # Webhook obunasini bekor qilishga urinamiz — muvaffaqiyatsiz bolsa ham uzamiz.
    target = acc.ig_user_id if acc.login_type == "instagram" else acc.page_id
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.delete(
                _graph(f"{target}/subscribed_apps", _host(acc.login_type)),
                params={"access_token": acc.page_access_token},
            )
    except Exception:
        logger.info("Instagram webhook obunasini bekor qilib bolmadi (eʼtiborsiz qoldirildi)")

    await db.delete(acc)
    await db.commit()
    return {"disconnected": True}


# ── Webhook ───────────────────────────────────────────────────────────────────

@webhook_router.get("/webhook", summary="Meta webhook tasdigi", include_in_schema=False)
async def verify_webhook(request: Request) -> Response:
    """Meta webhook'ni royxatdan otkazishda bir marta chaqiradi."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    expected = settings.instagram_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token or "", expected):
        return Response(content=challenge, media_type="text/plain")
    return Response(content="forbidden", status_code=403, media_type="text/plain")


def _valid_signature(body: bytes, header: Optional[str]) -> bool:
    """X-Hub-Signature-256 ni tekshiradi.

    Instagram login yolida imzo Instagram App Secret bilan, Facebook login
    yolida Facebook App Secret bilan hisoblanadi. Qaysi yol ishlatilayotganini
    webhook'ning ozidan bilib bolmaydi, shuning uchun sozlangan barcha
    secret'lar sinaladi — bittasi mos kelsa yetarli.
    """
    if not header:
        return False
    for secret in settings.webhook_secrets:
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, header):
            return True
    return False


@webhook_router.post("/webhook", summary="Instagram webhook", include_in_schema=False)
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    raw = await request.body()
    if not _valid_signature(raw, request.headers.get("X-Hub-Signature-256")):
        # Imzo notogri — soʻrov Meta dan kelmagan.
        raise HTTPException(status_code=403, detail="Imzo notogri")

    try:
        payload = json.loads(raw)
    except ValueError:
        return {"ok": False}

    for entry in payload.get("entry", []):
        # DM lar
        for event in entry.get("messaging", []) or []:
            try:
                await _handle_dm(db, entry, event)
            except Exception:
                # Bitta xabar xatosi butun webhook'ni yiqitmasin — Meta qayta yuboradi.
                logger.exception("Instagram DM ishlashda xato")
                await db.rollback()
        # Izohlar
        for change in entry.get("changes", []) or []:
            if change.get("field") != "comments":
                continue
            try:
                await _handle_comment(db, entry, change.get("value") or {})
            except Exception:
                logger.exception("Instagram izohini ishlashda xato")
                await db.rollback()

    return {"ok": True}


# ── Tella AI lead yigish oqimi ────────────────────────────────────────────────

_ASK_NAME = (
    "Assalomu alaykum! Men Tella AI — {company} yordamchisiman.\n"
    "Sizga tur tanlashda yordam beramiz. Iltimos, ism-familiyangizni yozing."
)
_ASK_PHONE = "Rahmat, {name}! Endi telefon raqamingizni yozing (masalan: +998901234567)."
_BAD_PHONE = "Telefon raqamini tushunmadim. Masalan: +998901234567"
_ASK_DEST = "Qaysi yonalish qiziqtiradi? (masalan: Dubay, Turkiya, Umra)"
_DONE = (
    "Rahmat! Sorovingiz qabul qilindi ✅\n"
    "Operatorimiz yaqin orada siz bilan bogʻlanadi."
)
_ALREADY = "Sorovingiz allaqachon qabul qilingan. Operatorimiz tez orada bogʻlanadi."


async def _account_for_entry(db: AsyncSession, entry: dict) -> Optional[InstagramAccount]:
    """Webhook entry sidan kompaniyaning ulangan akkauntini topadi."""
    ig_user_id = str(entry.get("id") or "")
    if not ig_user_id:
        return None
    return (await db.execute(
        select(InstagramAccount).where(
            InstagramAccount.ig_user_id == ig_user_id,
            InstagramAccount.is_active.is_(True),
        )
    )).scalar_one_or_none()


async def _reply(acc: InstagramAccount, recipient_id: str, text: str) -> None:
    resp = await _post(
        f"{acc.ig_user_id}/messages",
        acc.page_access_token,
        host=_host(acc.login_type),
        recipient={"id": recipient_id},
        message={"text": text},
    )
    if (err := _graph_error(resp)):
        logger.warning("Instagram javobini yuborib bolmadi: %s", err)


async def _company_name(db: AsyncSession, company_id: int) -> str:
    from app.models.company import Company

    c = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    return c.name if c else "firmamiz"


async def _notify_staff(db: AsyncSession, company_id: int, title: str, message: str) -> None:
    from app.services.notification_service import NotificationService

    try:
        await NotificationService(db, None).notify_company_staff(
            company_id, title, message, "lead", "/admin/requests"
        )
    except Exception:
        logger.exception("Instagram lead bildirishnomasi yuborilmadi")


async def _create_lead(
    db: AsyncSession,
    company_id: int,
    name: str,
    phone: str,
    sender_id: str,
    username: Optional[str],
    note: str,
) -> TourRequest:
    """Pipeline'da lead yaratadi (source="instagram")."""
    handle = username or sender_id
    lead = TourRequest(
        company_id=company_id,
        lead_name=name,
        lead_phone=phone,
        # tour_requests.lead_email NOT NULL — Instagram email bermaydi,
        # shuning uchun akkaunt nomidan barqaror plemba yasaymiz.
        lead_email=f"{handle}@instagram.local",
        status="Yangi",
        source="instagram",
        notes=note,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _handle_dm(db: AsyncSession, entry: dict, event: dict) -> None:
    acc = await _account_for_entry(db, entry)
    if not acc:
        return

    sender_id = str((event.get("sender") or {}).get("id") or "")
    # Oz akkauntimiz yuborgan (echo) xabarlarni eʼtiborsiz qoldiramiz.
    if not sender_id or sender_id == acc.ig_user_id:
        return
    message = event.get("message") or {}
    if message.get("is_echo"):
        return
    text = (message.get("text") or "").strip()
    if not text:
        return

    thread = (await db.execute(
        select(InstagramThread).where(
            InstagramThread.company_id == acc.company_id,
            InstagramThread.ig_sender_id == sender_id,
        )
    )).scalar_one_or_none()

    if not thread:
        thread = InstagramThread(
            company_id=acc.company_id,
            ig_sender_id=sender_id,
            stage="name",
        )
        db.add(thread)
        await db.flush()
        await db.commit()
        await _reply(acc, sender_id, _ASK_NAME.format(company=await _company_name(db, acc.company_id)))
        return

    if thread.stage == "name":
        thread.lead_name = text[:255]
        thread.stage = "phone"
        await db.commit()
        await _reply(acc, sender_id, _ASK_PHONE.format(name=thread.lead_name))
        return

    if thread.stage == "phone":
        # ml_assistant dagi tekshirilgan parserni qayta ishlatamiz.
        from app.services.ml_assistant import parse_phone

        phone = parse_phone(text)
        if not phone:
            await _reply(acc, sender_id, _BAD_PHONE)
            return
        thread.lead_phone = phone
        lead = await _create_lead(
            db,
            acc.company_id,
            thread.lead_name or "Instagram mijoz",
            phone,
            sender_id,
            thread.ig_username,
            note="Instagram DM orqali keldi (Tella AI yigdi).",
        )
        thread.request_id = lead.id
        thread.stage = "destination"
        await _notify_staff(
            db,
            acc.company_id,
            "Yangi lead (Instagram)",
            f"{lead.lead_name} — {phone}",
        )
        await db.commit()
        await _reply(acc, sender_id, _ASK_DEST)
        return

    if thread.stage == "destination":
        if thread.request_id:
            lead = (await db.execute(
                select(TourRequest).where(TourRequest.id == thread.request_id)
            )).scalar_one_or_none()
            if lead:
                lead.destination = text[:100]
        thread.stage = "done"
        await db.commit()
        await _reply(acc, sender_id, _DONE)
        return

    # stage == "done"
    await _reply(acc, sender_id, _ALREADY)


async def _handle_comment(db: AsyncSession, entry: dict, value: dict) -> None:
    """Post izohidan ham lead yaratamiz (telefon yoq — operator bogʻlanadi)."""
    acc = await _account_for_entry(db, entry)
    if not acc:
        return

    frm = value.get("from") or {}
    sender_id = str(frm.get("id") or "")
    username = frm.get("username")
    text = (value.get("text") or "").strip()
    if not sender_id or sender_id == acc.ig_user_id:
        return

    # Ayni foydalanuvchi uchun allaqachon suhbat/lead bolsa, takrorlamaymiz.
    thread = (await db.execute(
        select(InstagramThread).where(
            InstagramThread.company_id == acc.company_id,
            InstagramThread.ig_sender_id == sender_id,
        )
    )).scalar_one_or_none()
    if thread:
        return

    lead = await _create_lead(
        db,
        acc.company_id,
        username or "Instagram mijoz",
        "",  # izohda telefon bolmaydi — operator DM orqali soraydi
        sender_id,
        username,
        note=f"Instagram izohi: {text[:400]}",
    )
    # Izoh lead'i uchun ham thread ochamiz — keyin DM yozsa takror lead bolmasin.
    db.add(InstagramThread(
        company_id=acc.company_id,
        ig_sender_id=sender_id,
        ig_username=username,
        request_id=lead.id,
        stage="done",
        lead_name=username,
    ))
    await _notify_staff(
        db,
        acc.company_id,
        "Yangi lead (Instagram izoh)",
        f"@{username or sender_id}: {text[:80]}",
    )
    await db.commit()
