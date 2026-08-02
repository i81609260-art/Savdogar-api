"""Qo'ng'iroq yozuvlari — yuklash va AI tahlili."""

import logging
import os
import uuid
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.call_recording import CallRecording
from app.models.user import User, UserRole
from app.services import call_analysis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls", tags=["Call Analysis"])
settings = get_settings()

# Yozuvlar `/uploads` dan TARQATILMAYDI. Mijoz bilan bo'lgan suhbat — eng
# maxfiy ma'lumot; ilgari havolani bilgan istalgan odam uni yuklab olardi.
# Endi fayllar maxfiy papkada yotadi va faqat shu router orqali, o'z
# firmasining xodimiga beriladi.
AUDIO_URL_PREFIX = "/api/calls/audio/"


def _audio_dir() -> str:
    return os.path.join(settings.private_dir, "calls")

_ALLOWED = {
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".amr": "audio/amr",  # Android qo'ng'iroq yozuvchilari ko'p ishlatadi
}


class CallOut(BaseModel):
    """Qo'ng'iroq yozuvi va tahlili."""

    id: int
    title: Optional[str]
    phone: Optional[str]
    request_id: Optional[int]
    file_url: str
    duration_sec: Optional[int]
    status: str
    error: Optional[str]
    transcript: Optional[str]
    summary: Optional[str]
    sentiment: Optional[str]
    score: Optional[int]
    destination: Optional[str]
    topics: Optional[str]
    next_step: Optional[str]
    operator_notes: Optional[str]
    created_at: str


class ConfigOut(BaseModel):
    """Tahlil yoqilganmi — frontend ogohlantirish ko'rsatishi uchun."""

    ai_enabled: bool
    max_mb: int


def _branch_scope(current_user: User):
    """Operator faqat o'z filiali va umumiy yozuvlarni ko'radi; admin — hammasini."""
    if current_user.role == UserRole.OPERATOR and current_user.branch_id:
        return or_(
            CallRecording.branch_id == current_user.branch_id,
            CallRecording.branch_id.is_(None),
        )
    return None


def _to_out(c: CallRecording) -> CallOut:
    return CallOut(
        id=c.id,
        title=c.title,
        phone=c.phone,
        request_id=c.request_id,
        file_url=c.file_url,
        duration_sec=c.duration_sec,
        status=c.status,
        error=c.error,
        transcript=c.transcript,
        summary=c.summary,
        sentiment=c.sentiment,
        score=c.score,
        destination=c.destination,
        topics=c.topics,
        next_step=c.next_step,
        operator_notes=c.operator_notes,
        created_at=c.created_at.isoformat() if c.created_at else "",
    )


async def _apply_analysis(
    db: AsyncSession, call: CallRecording, content: bytes, mime: str
) -> None:
    """Tahlilni ishga tushirib, natijani yozuvga saqlash."""
    try:
        result = await call_analysis.analyze_audio(content, mime)
    except call_analysis.AnalysisUnavailable as exc:
        call.status = "xato"
        call.error = str(exc)[:500]
    except Exception as exc:  # noqa: BLE001 — yozuv yo'qolmasligi kerak
        logger.exception("Qo'ng'iroq tahlilida kutilmagan xato")
        call.status = "xato"
        call.error = f"Kutilmagan xato: {type(exc).__name__}"[:500]
    else:
        for field, value in result.items():
            setattr(call, field, value)
        call.status = "tayyor"
        call.error = None
    await db.commit()


@router.get("/config", response_model=ConfigOut, summary="Tahlil sozlamalari")
async def get_config(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
) -> ConfigOut:
    """AI tahlili yoqilganligini bildiradi."""
    return ConfigOut(
        ai_enabled=call_analysis.is_configured(),
        max_mb=settings.max_audio_upload_mb,
    )


@router.post("", response_model=CallOut, summary="Qo'ng'iroq yozuvini yuklash")
async def upload_call(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    request_id: Optional[int] = Form(None),
    duration_sec: Optional[int] = Form(None),
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> CallOut:
    """Audio'ni saqlab, darhol AI tahlilidan o'tkazadi."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Qo'llab-quvvatlanadigan formatlar: {', '.join(sorted(_ALLOWED))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fayl bo'sh")
    max_bytes = settings.max_audio_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio {settings.max_audio_upload_mb}MB dan oshmasligi kerak",
        )

    upload_path = _audio_dir()
    os.makedirs(upload_path, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    async with aiofiles.open(os.path.join(upload_path, filename), "wb") as f:
        await f.write(content)

    call = CallRecording(
        company_id=current_user.company_id,
        # Yozuv uni yuklagan xodimning filialiga biriktiriladi.
        branch_id=current_user.branch_id,
        user_id=current_user.id,
        request_id=request_id,
        title=(title or "").strip() or None,
        phone=(phone or "").strip() or None,
        file_url=f"{AUDIO_URL_PREFIX}{filename}",
        duration_sec=duration_sec,
        status="tahlilda",
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    await _apply_analysis(db, call, content, _ALLOWED[ext])
    await db.refresh(call)
    return _to_out(call)


@router.get("", response_model=List[CallOut], summary="Qo'ng'iroqlar ro'yxati")
async def list_calls(
    request_id: Optional[int] = None,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> List[CallOut]:
    """Kompaniyaning qo'ng'iroq yozuvlari, yangisidan boshlab."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    query = select(CallRecording).where(
        CallRecording.company_id == current_user.company_id
    )
    if request_id is not None:
        query = query.where(CallRecording.request_id == request_id)
    scope = _branch_scope(current_user)
    if scope is not None:
        query = query.where(scope)

    result = await db.execute(query.order_by(CallRecording.created_at.desc()).limit(200))
    return [_to_out(c) for c in result.scalars().all()]


@router.get("/audio/{filename}", summary="Yozuvni tinglash (himoyalangan)")
async def get_call_audio(
    filename: str,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Audio faylni faqat o'sha firmaning xodimiga qaytaradi.

    Fayl nomi bazadagi yozuv orqali tekshiriladi — ya'ni diskdagi ixtiyoriy
    yo'lni so'rab bo'lmaydi (`../` kabi hiylalar ham ishlamaydi, chunki
    so'ralgan nom aynan mos yozuv topilishi shart).
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    query = select(CallRecording).where(
        CallRecording.file_url == f"{AUDIO_URL_PREFIX}{filename}",
        CallRecording.company_id == current_user.company_id,
    )
    scope = _branch_scope(current_user)
    if scope is not None:
        query = query.where(scope)

    call = (await db.execute(query)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi")

    path = os.path.join(_audio_dir(), os.path.basename(filename))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Audio fayl topilmadi")

    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(
        path,
        media_type=_ALLOWED.get(ext, "application/octet-stream"),
        headers={"Cache-Control": "private, no-store"},
    )


async def _get_owned(
    db: AsyncSession, call_id: int, current_user: User
) -> CallRecording:
    query = select(CallRecording).where(
        and_(
            CallRecording.id == call_id,
            CallRecording.company_id == current_user.company_id,
        )
    )
    scope = _branch_scope(current_user)
    if scope is not None:
        query = query.where(scope)
    call = (await db.execute(query)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi")
    return call


@router.post("/{call_id}/reanalyze", response_model=CallOut, summary="Qayta tahlil")
async def reanalyze_call(
    call_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> CallOut:
    """Saqlangan audio'ni qaytadan tahlil qilish (limit tugagan bo'lsa qo'l keladi)."""
    call = await _get_owned(db, call_id, current_user)

    path = os.path.join(_audio_dir(), os.path.basename(call.file_url))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio fayl serverda topilmadi")

    async with aiofiles.open(path, "rb") as f:
        content = await f.read()

    ext = os.path.splitext(path)[1].lower()
    call.status = "tahlilda"
    await db.commit()

    await _apply_analysis(db, call, content, _ALLOWED.get(ext, "audio/mpeg"))
    await db.refresh(call)
    return _to_out(call)


@router.delete("/{call_id}", summary="Yozuvni o'chirish")
async def delete_call(
    call_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yozuvni va audio faylni o'chirish."""
    call = await _get_owned(db, call_id, current_user)

    path = os.path.join(_audio_dir(), os.path.basename(call.file_url))
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("Audio faylni o'chirib bo'lmadi: %s", path)

    await db.delete(call)
    await db.commit()
    return {"deleted": True}
