"""Valyuta kurslari va so'mga o'girish.

Bu qatlam TASHQI xizmatga (Markaziy bank) bog'langan, shuning uchun eng
muhim savol: xizmat ishlamay qolsa nima bo'ladi? Javob qat'iy — tur
saqlash amali to'xtamasligi kerak.
"""

import app.services.currency as cur
from app.services.currency import _parse, rate_for, refresh_rates, to_uzs


def _keshni_tozala():
    cur._cache.clear()
    cur._fetched_at = 0.0


# --------------------------------------------------------------------------
# MB javobini o'qish
# --------------------------------------------------------------------------
def test_oddiy_kurs_oqiladi():
    r = _parse([{"Ccy": "USD", "Rate": "11915.64", "Nominal": "1"}])
    assert r["USD"] == 11915.64


def test_nominal_hisobga_olinadi():
    """Ba'zi valyutalar 100 birlik uchun kotirovka qilinadi.

    Hisobga olmasak qiymat 100 barobar xato bo'lardi — masalan yapon
    iyenasidagi tur million so'm o'rniga yuz million so'm bo'lib ko'rinardi.
    """
    r = _parse([{"Ccy": "JPY", "Rate": "8100.0", "Nominal": "100"}])
    assert r["JPY"] == 81.0


def test_uzs_doim_bir():
    assert _parse([])["UZS"] == 1.0


def test_buzuq_yozuv_otkazib_yuboriladi():
    """Bitta buzuq qator butun ro'yxatni yo'q qilmasligi kerak."""
    r = _parse([
        {"Ccy": "USD", "Rate": "11915.64", "Nominal": "1"},
        {"Ccy": "XXX", "Rate": "axlat", "Nominal": "1"},
        {"Ccy": "YYY"},
        {"Rate": "100"},
    ])
    assert r["USD"] == 11915.64
    assert "XXX" not in r and "YYY" not in r


def test_nol_kurs_qabul_qilinmaydi():
    """Nolga bo'lish yoki narxni nolga aylantirish oldini oladi."""
    r = _parse([{"Ccy": "ZZZ", "Rate": "0", "Nominal": "1"}])
    assert "ZZZ" not in r


# --------------------------------------------------------------------------
# So'mga o'girish
# --------------------------------------------------------------------------
def test_soumga_ogirish():
    _keshni_tozala()
    cur._cache.update({"UZS": 1.0, "EUR": 13749.46})
    assert to_uzs(10_001, "EUR") == round(10_001 * 13749.46, 2)


def test_som_ozgarishsiz_qoladi():
    _keshni_tozala()
    cur._cache.update({"UZS": 1.0})
    assert to_uzs(12_000_000, "UZS") == 12_000_000


def test_asosiy_xato_qayta_ishlab_chiqariladi():
    """Aynan shu holat saralashni buzgan edi.

    12 mln so'm va 10 001 EUR — xom raqamda birinchisi katta, so'mga
    o'girilganda esa ikkinchisi ~11 barobar qimmat.
    """
    _keshni_tozala()
    cur._cache.update({"UZS": 1.0, "EUR": 13749.46})

    som = to_uzs(12_000_000, "UZS")
    yevro = to_uzs(10_001, "EUR")

    assert 12_000_000 > 10_001, "xom raqamda so'mli tur kattaroq"
    assert yevro > som, "so'mga o'girilganda yevroli tur qimmatroq"


def test_nomalum_valyuta_yiqilmaydi():
    """Noma'lum kod bilan ham tur saqlanishi kerak."""
    _keshni_tozala()
    assert to_uzs(100, "XYZ") == 100.0


def test_bosh_narx_none_qaytaradi():
    assert to_uzs(None, "USD") is None


def test_valyutasiz_som_deb_olinadi():
    _keshni_tozala()
    assert to_uzs(500, None) == 500.0


# --------------------------------------------------------------------------
# Ishonchlilik — eng muhimi
# --------------------------------------------------------------------------
async def test_mb_ishlamasa_zaxira_ishlatiladi(monkeypatch):
    """Tarmoq uzilganda ham qiymat qaytishi SHART.

    Aks holda MB xizmatining uzilishi tur saqlashni to'xtatib qo'yardi.
    """
    _keshni_tozala()

    class _Yiqiladi:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("tarmoq yo'q")

    monkeypatch.setattr(cur.httpx, "AsyncClient", lambda **k: _Yiqiladi())

    rates = await refresh_rates(force=True)
    assert rates["USD"] > 0, "zaxira qiymat qaytishi kerak"
    assert to_uzs(100, "USD") > 0


async def test_eski_kesh_zaxiradan_ustun(monkeypatch):
    """Uzilishda eskirgan kesh ham zaxira konstantadan yaxshiroq.

    Kurs kuniga bir marta o'zgaradi, uzilish esa vaqtinchalik.
    """
    _keshni_tozala()
    cur._cache.update({"UZS": 1.0, "USD": 99_999.0})

    class _Yiqiladi:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("tarmoq yo'q")

    monkeypatch.setattr(cur.httpx, "AsyncClient", lambda **k: _Yiqiladi())

    rates = await refresh_rates(force=True)
    assert rates["USD"] == 99_999.0, "eski kesh saqlanishi kerak"


def test_rate_for_tarmoqqa_chiqmaydi():
    """`to_uzs` tur saqlash yo'lida chaqiriladi — u sekin bo'lmasligi kerak."""
    _keshni_tozala()
    cur._cache.update({"UZS": 1.0, "USD": 12_000.0})
    assert rate_for("usd") == 12_000.0, "katta-kichik harf farq qilmasin"
    assert rate_for(None) == 1.0


# --------------------------------------------------------------------------
# Kunlik yangilash halqasi
# --------------------------------------------------------------------------
async def test_kunlik_halqa_darrov_bir_marta_ishlaydi(monkeypatch):
    """Halqa birinchi aylanishni KUTMASDAN bajaradi.

    Aks holda server qayta ishga tushgach kurs 24 soat davomida
    yangilanmay turardi.
    """
    import asyncio

    chaqirildi = {"refresh": 0, "recompute": 0}

    async def _refresh(force=False):
        chaqirildi["refresh"] += 1
        return {"UZS": 1.0}

    async def _recompute():
        chaqirildi["recompute"] += 1

    monkeypatch.setattr(cur, "refresh_rates", _refresh)

    task = asyncio.create_task(cur.daily_refresh_loop(_recompute))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert chaqirildi["refresh"] == 1
    assert chaqirildi["recompute"] == 1


async def test_xato_halqani_toxtatmaydi(monkeypatch):
    """Bir kunlik uzilish keyingi kunlarni ham to'xtatib qo'ymasligi kerak."""
    import asyncio

    urinishlar = {"n": 0}

    async def _refresh(force=False):
        urinishlar["n"] += 1
        raise RuntimeError("MB javob bermadi")

    async def _recompute():
        pass

    monkeypatch.setattr(cur, "refresh_rates", _refresh)
    # Kutishni qisqartiramiz, aks holda test 24 soat kutardi.
    monkeypatch.setattr(cur, "_DAILY_SLEEP_SECONDS", 0)

    task = asyncio.create_task(cur.daily_refresh_loop(_recompute))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert urinishlar["n"] > 1, "xatodan keyin ham qayta urinishi kerak"
