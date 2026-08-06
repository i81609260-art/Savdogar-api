"""Rasm ko'rinishidagi price-list.

Bu qism qolgan hammasidan farq qiladi: tashqi xizmatga so'rov yuboradi.
Shuning uchun testlar ikki narsani bosadi:

1. **Sozlanmagan bo'lsa ilova ishlashda davom etsin.** Rasm — ixtiyoriy
   imkoniyat; kalit yo'qligi boshqa hech narsani buzmasligi kerak.
2. **Xato istisno bo'lib chiqmasin.** Chaqiruvchi (yuklash endpointi,
   Telegram bot) qolgan formatlar bilan bir xil `PricelistResult` olsin —
   ikki xil xato ishlovi yozilmasin.

Tarmoqqa chiqilmaydi: HTTP qatlami almashtiriladi.
"""

import pytest

from app.services import pricelist_image
from app.services.pricelist_image import (
    ImageOcrUnavailable,
    is_configured,
    parse_image,
)
from app.services.pricelist_parser import IMAGE_EXT, parse_pricelist_async

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100

OCR_TEXT = """ANTALYA 7 kecha
Rixos Downtown 5* UAI — $850
Delphin Imperial 5* AI — $720"""


# --------------------------------------------------------------------------
# Sozlanmagan holat
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_key_returns_clear_message(monkeypatch):
    """Kalit yo'q — tushunarli xabar, istisno emas."""
    monkeypatch.setattr(
        pricelist_image, "get_settings", lambda: _Settings(key="")
    )
    result = await parse_image(PNG, "image/png")
    assert result.offers == []
    assert "GEMINI_API_KEY" in result.warnings[0]


def test_is_configured_reflects_key(monkeypatch):
    monkeypatch.setattr(pricelist_image, "get_settings", lambda: _Settings(key=""))
    assert is_configured() is False
    monkeypatch.setattr(pricelist_image, "get_settings", lambda: _Settings(key="k"))
    assert is_configured() is True


# --------------------------------------------------------------------------
# Muvaffaqiyatli o'qish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_image_text_goes_through_normal_parser(monkeypatch):
    """Rasmdan chiqqan matn odatdagi tahlilchidan o'tsin.

    Tahlil qoidalari (yo'nalish, ovqat, yulduz, narx) ikkiga bo'linmasligi
    kerak — aks holda rasm va matn boshqacha natija berardi.
    """
    _patch_ocr(monkeypatch, OCR_TEXT)
    result = await parse_image(PNG, "image/png")

    assert len(result.offers) == 2
    first = result.offers[0]
    assert first.hotel_name == "Rixos Downtown"
    assert first.price_gross == 850
    assert first.board == "UAI"
    assert first.star == "5"
    assert first.nights == 7          # sarlavha satridan tarqadi
    assert first.city == "Antalya"


@pytest.mark.asyncio
async def test_empty_ocr_result_reported(monkeypatch):
    _patch_ocr(monkeypatch, "   ")
    result = await parse_image(PNG, "image/png")
    assert result.offers == []
    assert "topilmadi" in result.warnings[0]


@pytest.mark.asyncio
async def test_text_without_prices_reported(monkeypatch):
    """Rasm o'qildi, lekin narx yo'q — buni aytish kerak."""
    _patch_ocr(monkeypatch, "Bizning agentlik eng yaxshisi!")
    result = await parse_image(PNG, "image/png")
    assert result.offers == []
    assert any("narx topilmadi" in w for w in result.warnings)


# --------------------------------------------------------------------------
# Cheklovlar
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsupported_mime_rejected(monkeypatch):
    monkeypatch.setattr(pricelist_image, "get_settings", lambda: _Settings(key="k"))
    result = await parse_image(PNG, "image/tiff")
    assert result.offers == []
    assert "format" in result.warnings[0].lower()


@pytest.mark.asyncio
async def test_oversized_image_rejected(monkeypatch):
    monkeypatch.setattr(pricelist_image, "get_settings", lambda: _Settings(key="k"))
    huge = b"0" * (pricelist_image.MAX_IMAGE_BYTES + 1)
    result = await parse_image(huge, "image/png")
    assert "katta" in result.warnings[0]


@pytest.mark.asyncio
async def test_mime_with_charset_accepted(monkeypatch):
    """Telegram "image/jpeg; charset=..." yuborishi mumkin."""
    _patch_ocr(monkeypatch, OCR_TEXT)
    result = await parse_image(PNG, "image/jpeg; charset=binary")
    assert len(result.offers) == 2


# --------------------------------------------------------------------------
# Xizmat xatolari — hech biri istisno bo'lib chiqmasin
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_service_error_becomes_warning(monkeypatch):
    async def boom(content, mime):
        raise ImageOcrUnavailable("Xizmat javob bermadi (500)")

    monkeypatch.setattr(pricelist_image, "image_to_text", boom)
    result = await parse_image(PNG, "image/png")
    assert result.offers == []
    assert "javob bermadi" in result.warnings[0]


@pytest.mark.asyncio
async def test_rate_limit_message(monkeypatch):
    async def limited(content, mime):
        raise ImageOcrUnavailable("Kunlik limit tugadi, ertaga qayta urining")

    monkeypatch.setattr(pricelist_image, "image_to_text", limited)
    result = await parse_image(PNG, "image/png")
    assert "limit" in result.warnings[0]


# --------------------------------------------------------------------------
# Umumiy kirish nuqtasi
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_async_parser_routes_images(monkeypatch):
    _patch_ocr(monkeypatch, OCR_TEXT)
    result = await parse_pricelist_async(PNG, filename="afisha.jpg")
    assert len(result.offers) == 2


@pytest.mark.asyncio
async def test_async_parser_routes_by_content_type(monkeypatch):
    _patch_ocr(monkeypatch, OCR_TEXT)
    result = await parse_pricelist_async(PNG, content_type="image/png")
    assert len(result.offers) == 2


@pytest.mark.asyncio
async def test_async_parser_still_handles_text():
    """Rasm bo'lmagan formatlar avvalgidek ishlasin."""
    result = await parse_pricelist_async("Rixos 5* AI — $850")
    assert len(result.offers) == 1


@pytest.mark.asyncio
async def test_async_parser_still_handles_csv():
    csv_bytes = b"Otel,Narx\nRixos,850\n"
    result = await parse_pricelist_async(csv_bytes, filename="price.csv")
    assert len(result.offers) == 1


def test_image_extensions_cover_common_formats():
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        assert ext in IMAGE_EXT


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------
class _Settings:
    def __init__(self, key: str):
        self.gemini_api_key = key
        self.gemini_model = "gemini-2.0-flash"


def _patch_ocr(monkeypatch, text: str) -> None:
    """Tashqi xizmat o'rniga tayyor matn qaytaradi."""

    async def fake(content, mime):
        return text

    monkeypatch.setattr(pricelist_image, "image_to_text", fake)
