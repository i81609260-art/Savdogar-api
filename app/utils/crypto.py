"""Maxfiy qiymatlarni (operator login/parol, sessiya cookie) shifrlash.

Turagentlar tur operatorlarning B2B kabinetiga o'z login-parolini kiritadi.
Bu — **begona tizimdagi** hisob ma'lumoti, ya'ni bazadan o'g'irlansa zarar
faqat Savdogar bilan cheklanmaydi. Shuning uchun ular bazaga hech qachon
ochiq ko'rinishda yozilmaydi.

Kalit
-----
`CREDENTIALS_KEY` environment o'zgaruvchisi. Qo'yilmagan bo'lsa `SECRET_KEY`
dan hosil qilinadi — ishga tushish uchun yetarli, lekin:

  ⚠️ SECRET_KEY almashtirilsa saqlangan parollar O'QILMAY QOLADI.
     Production'da alohida CREDENTIALS_KEY qo'ying.

Kalit yaratish:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _fernet() -> Fernet:
    """Shifrlash kalitini tayyorlaydi (bir marta hisoblanadi)."""
    settings = get_settings()
    raw = (settings.credentials_key or "").strip()

    if raw:
        try:
            return Fernet(raw.encode())
        except (ValueError, TypeError):
            # Foydalanuvchi Fernet formatida bo'lmagan matn qo'ygan —
            # undan barqaror kalit hosil qilamiz.
            digest = hashlib.sha256(raw.encode()).digest()
            return Fernet(base64.urlsafe_b64encode(digest))

    log.warning(
        "CREDENTIALS_KEY o'rnatilmagan — kalit SECRET_KEY dan hosil qilinmoqda. "
        "SECRET_KEY almashtirilsa saqlangan operator parollari o'qilmay qoladi. "
        "Railway -> Variables -> CREDENTIALS_KEY qo'ying."
    )
    digest = hashlib.sha256(
        b"savdogar-credentials:" + settings.secret_key.encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str | None) -> str | None:
    """Matnni shifrlaydi. Bo'sh qiymat shundayligicha qaytadi."""
    if not plaintext:
        return plaintext
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Shifrni ochadi.

    Kalit almashgan yoki yozuv buzilgan bo'lsa `None` qaytaradi — ilova
    yiqilmasin, chaqiruvchi "qayta login qiling" deb ko'rsatsin.
    """
    if not ciphertext:
        return ciphertext
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        log.warning("Shifrni ochib bo'lmadi — kalit almashgan bo'lishi mumkin.")
        return None


def mask(value: str | None, keep: int = 2) -> str:
    """Ko'rsatish uchun niqoblaydi: `is••••@mail.uz` kabi.

    Hech qachon to'liq parolni qaytarmaydi — panelda ham, logda ham.
    """
    if not value:
        return ""
    if len(value) <= keep:
        return "•" * len(value)
    return value[:keep] + "•" * min(len(value) - keep, 8)
