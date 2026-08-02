"""Yuklanadigan rasmlarni tekshirish — bitta manba.

Ilgari bu mantiq `upload.py`, `tours.py` va `company_public.py` da uch marta
takrorlangan va uchtasi bir-biridan farq qilardi (biri magic-byte tekshirsa,
boshqasi faqat content-type'ga ishonardi). Endi hammasi shu yerdan foydalanadi.
"""

import os
import uuid
from typing import Optional

import aiofiles
from fastapi import HTTPException, UploadFile

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Kengaytma va content-type'ga ishonib bo'lmaydi — ikkalasini ham mijoz
# yuboradi. Fayl boshidagi imzo (magic bytes) esa yolg'on bo'lolmaydi.
_MAGIC = (
    lambda c: c[:3] == b"\xff\xd8\xff",  # JPEG
    lambda c: c[:8] == b"\x89PNG\r\n\x1a\n",  # PNG
    lambda c: c[:6] in (b"GIF87a", b"GIF89a"),  # GIF
    lambda c: c[:4] == b"RIFF" and c[8:12] == b"WEBP",  # WebP
)


def ensure_within_limit(file: UploadFile, max_bytes: int) -> None:
    """Faylni O'QIMASDAN oldin hajmini tekshiradi.

    Muhim: avval `await file.read()` qilib, keyin uzunlikni tekshirish 500 MB
    lik so'rovda serverning butun xotirasini yeb qo'yardi. Starlette
    `UploadFile.size` ni Content-Length dan oldindan biladi.
    """
    size = getattr(file, "size", None)
    if size is not None and size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Fayl hajmi {max_bytes // 1024 // 1024}MB dan oshmasligi kerak",
        )


def validate_image(content: bytes, filename: Optional[str], max_bytes: int) -> str:
    """Rasmni tekshirib, xavfsiz kengaytmani qaytaradi."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Faqat rasm fayllari qabul qilinadi: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Fayl hajmi {max_bytes // 1024 // 1024}MB dan oshmasligi kerak",
        )
    if not any(check(content) for check in _MAGIC):
        raise HTTPException(status_code=400, detail="Yaroqsiz rasm formati")
    return ext


async def save_image(
    file: UploadFile, directory: str, max_bytes: int, prefix: str = ""
) -> str:
    """Rasmni tekshirib saqlaydi va `/uploads/...` ko'rinishidagi URL qaytaradi."""
    ensure_within_limit(file, max_bytes)
    content = await file.read()
    ext = validate_image(content, file.filename, max_bytes)

    os.makedirs(directory, exist_ok=True)
    name = f"{prefix}{uuid.uuid4()}{ext}"
    async with aiofiles.open(os.path.join(directory, name), "wb") as f:
        await f.write(content)
    return f"/uploads/{name}"
