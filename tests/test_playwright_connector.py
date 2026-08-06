"""Retsept bilan ishlaydigan brauzer konnektori.

Testlar **soxta sahifa** obyekti bilan ishlaydi — Playwright o'rnatilishi
shart emas. Bu ataylab: konnektor `page` ni bir necha metod orqaligina
ishlatadi, shuning uchun uni almashtirish mumkin. Xuddi shu sabab bilan
bir xil konnektor serverda ham, turagentning mashinasida ham ishlaydi.
"""

import pytest

from app.services.operator_connector import (
    ConnectorContext,
    ConnectorStatus,
    run_connector,
)
from app.services.playwright_connector import (
    PlaywrightConnector,
    SearchRecipe,
    build_connector,
)
from app.services.tella_tour_search import extract_query


# --------------------------------------------------------------------------
# Soxta sahifa
# --------------------------------------------------------------------------
class FakeElement:
    def __init__(self, text: str = "", children: dict | None = None):
        self.text = text
        self.children = children or {}
        self.filled: list[str] = []
        self.clicked = 0
        self.selected: list[str] = []

    async def fill(self, value):
        self.filled.append(value)

    async def click(self):
        self.clicked += 1

    async def press(self, key):
        self.clicked += 1

    async def select_option(self, value):
        self.selected.append(value)

    async def inner_text(self):
        return self.text

    async def query_selector(self, selector):
        return self.children.get(selector)


class FakePage:
    """Konnektor ishlatadigan metodlargina."""

    def __init__(self, elements=None, html="", rows=None):
        self.elements = elements or {}
        self.html = html
        self.rows = rows or []
        self.visited: list[str] = []
        self.waited: list[str] = []

    async def goto(self, url):
        self.visited.append(url)

    async def content(self):
        return self.html

    async def query_selector(self, selector):
        return self.elements.get(selector)

    async def query_selector_all(self, selector):
        return self.rows if selector == ".row" else []

    async def wait_for_selector(self, selector, timeout=None):
        self.waited.append(selector)


def _ctx(page=None, **kw) -> ConnectorContext:
    return ConnectorContext(
        query=kw.pop("query", extract_query("Antalyaga 5 yulduz UAI 7 kecha")),
        page=page,
        **kw,
    )


def _login_page(html="dashboard") -> FakePage:
    return FakePage(
        elements={
            "input[type=password]": FakeElement(),
            "input[type=email]": FakeElement(),
            "button[type=submit]": FakeElement(),
        },
        html=html,
    )


FULL_RECIPE = SearchRecipe(
    search_url="https://op.uz/search",
    fields={"destination": "#city", "nights": "#nights", "board": "#board"},
    field_values={"board": {"UAI": "7"}},
    submit="#go",
    row=".row",
    row_fields={
        "hotel_name": ".name", "price_gross": ".price",
        "star": ".star", "board": ".board",
    },
    wait_for=".row",
)


# --------------------------------------------------------------------------
# Retsept
# --------------------------------------------------------------------------
def test_recipe_from_json():
    recipe = SearchRecipe.from_json(
        '{"row": ".card", "row_fields": {"hotel_name": ".n"}, "submit": "#go"}'
    )
    assert recipe.row == ".card"
    assert recipe.submit == "#go"
    assert recipe.is_usable


def test_recipe_from_dict():
    recipe = SearchRecipe.from_json({"row": ".card", "row_fields": {"hotel_name": ".n"}})
    assert recipe.is_usable


def test_broken_json_gives_empty_recipe():
    """Buzuq retsept ilovani yiqitmasin."""
    recipe = SearchRecipe.from_json("{buzuq json")
    assert not recipe.is_usable


def test_unknown_keys_ignored():
    """Retseptda notanish kalit bo'lsa ham yiqilmasin."""
    recipe = SearchRecipe.from_json(
        '{"row": ".c", "row_fields": {"hotel_name": ".n"}, "allaqanday": 1}'
    )
    assert recipe.is_usable


def test_recipe_without_row_is_unusable():
    """Natija qatorisiz hech narsa o'qib bo'lmaydi."""
    assert not SearchRecipe.from_json('{"submit": "#go"}').is_usable


def test_recipe_without_hotel_name_is_unusable():
    assert not SearchRecipe.from_json(
        '{"row": ".c", "row_fields": {"price_gross": ".p"}}'
    ).is_usable


def test_empty_config_is_unusable():
    assert not SearchRecipe.from_json(None).is_usable


# --------------------------------------------------------------------------
# Login — retseptsiz, umumiy qoidalar bilan
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_fills_and_submits():
    page = _login_page()
    connector = PlaywrightConnector()
    status = await connector.login(
        _ctx(page, login="a@b.uz", password="parol", login_url="https://op.uz/login")
    )
    assert status is ConnectorStatus.OK
    assert page.elements["input[type=email]"].filled == ["a@b.uz"]
    assert page.elements["input[type=password]"].filled == ["parol"]
    assert page.elements["button[type=submit]"].clicked == 1


@pytest.mark.asyncio
async def test_login_detects_wrong_password():
    page = _login_page(html="<div>Invalid credentials</div>")
    status = await PlaywrightConnector().login(
        _ctx(page, login="a@b.uz", password="x", login_url="https://op.uz/login")
    )
    assert status is ConnectorStatus.AUTH_FAILED


@pytest.mark.asyncio
async def test_captcha_wins_over_auth_error():
    """Captcha sahifasida "error" so'zi ham bo'lishi mumkin.

    AUTH_FAILED deb belgilansa agent parolini beso'naqay qayta terardi,
    aslida esa captcha bosish kerak edi.
    """
    page = _login_page(html="<div>Error. Please confirm you are not a robot. reCAPTCHA</div>")
    status = await PlaywrightConnector().login(
        _ctx(page, login="a@b.uz", password="x", login_url="https://op.uz/login")
    )
    assert status is ConnectorStatus.CAPTCHA


@pytest.mark.asyncio
async def test_saved_session_skips_login():
    """Sessiya bo'lsa login formasi umuman ochilmasin — tezroq va
    operator saytiga kam yuklama."""
    page = _login_page()
    status = await PlaywrightConnector().login(
        _ctx(page, storage_state={"cookies": []})
    )
    assert status is ConnectorStatus.OK
    assert page.visited == [], "sessiya bo'lsa ham login sahifasi ochildi"


@pytest.mark.asyncio
async def test_login_without_credentials_fails():
    status = await PlaywrightConnector().login(_ctx(_login_page()))
    assert status is ConnectorStatus.AUTH_FAILED


@pytest.mark.asyncio
async def test_no_password_field_means_already_logged_in():
    page = FakePage(elements={}, html="dashboard")
    status = await PlaywrightConnector().login(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert status is ConnectorStatus.OK


# --------------------------------------------------------------------------
# Qidiruv
# --------------------------------------------------------------------------
def _result_page(rows_data):
    rows = [
        FakeElement(children={
            ".name": FakeElement(name), ".price": FakeElement(price),
            ".star": FakeElement(star), ".board": FakeElement(board),
        })
        for name, price, star, board in rows_data
    ]
    page = FakePage(
        elements={
            "input[type=password]": FakeElement(),
            "input[type=email]": FakeElement(),
            "button[type=submit]": FakeElement(),
            "#city": FakeElement(), "#nights": FakeElement(),
            "#board": FakeElement(), "#go": FakeElement(),
        },
        html="dashboard",
        rows=rows,
    )
    return page


@pytest.mark.asyncio
async def test_search_reads_rows():
    page = _result_page([
        ("Rixos Downtown", "$850", "5*", "UAI"),
        ("Delphin Imperial", "$720", "5*", "AI"),
    ])
    result = await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert result.status is ConnectorStatus.OK
    assert [o.hotel_name for o in result.offers] == ["Rixos Downtown", "Delphin Imperial"]
    assert result.offers[0].price_gross == 850
    assert result.offers[0].star == "5"
    assert result.offers[0].board == "UAI"


@pytest.mark.asyncio
async def test_search_fills_form_from_query():
    page = _result_page([("Rixos", "$850", "5*", "UAI")])
    await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert page.elements["#city"].filled == ["Antalya"]
    assert page.elements["#nights"].filled == ["7"]
    assert page.elements["#go"].clicked == 1


@pytest.mark.asyncio
async def test_field_values_map_to_site_codes():
    """Har saytda o'z kodlari bor: "UAI" -> "7"."""
    page = _result_page([("Rixos", "$850", "5*", "UAI")])
    await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert page.elements["#board"].filled == ["7"]


@pytest.mark.asyncio
async def test_rows_without_price_skipped():
    page = _result_page([
        ("Rixos", "$850", "5*", "UAI"),
        ("Kelishuv asosida", "", "5*", "AI"),
    ])
    result = await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert [o.hotel_name for o in result.offers] == ["Rixos"]


@pytest.mark.asyncio
async def test_no_rows_gives_no_results_not_error():
    page = _result_page([])
    result = await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert result.status is ConnectorStatus.NO_RESULTS
    assert result.offers == []


@pytest.mark.asyncio
async def test_search_without_recipe_is_unsupported():
    result = await PlaywrightConnector().search(_ctx(_login_page()))
    assert result.status is ConnectorStatus.UNSUPPORTED
    assert "retsept" in result.error.lower()


@pytest.mark.asyncio
async def test_search_without_page_fails_cleanly():
    result = await PlaywrightConnector(FULL_RECIPE).search(_ctx(None))
    assert result.status is ConnectorStatus.ERROR


@pytest.mark.asyncio
async def test_auth_failure_stops_search():
    page = _result_page([("Rixos", "$850", "5*", "UAI")])
    page.html = "Invalid password"
    result = await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="x", login_url="https://op.uz/login")
    )
    assert result.status is ConnectorStatus.AUTH_FAILED
    assert result.offers == []


# --------------------------------------------------------------------------
# Xatolarga chidamlilik
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connector_exception_does_not_escape():
    """Bitta operator sinsa qolgan 17 tasi ishlashda davom etishi kerak."""

    class Exploding(PlaywrightConnector):
        async def search(self, ctx):
            raise RuntimeError("sayt yiqildi")

    from app.services.operator_connector import registry

    registry.register(Exploding(FULL_RECIPE))
    try:
        result = await run_connector("custom", _ctx(_login_page()))
        assert result.status is ConnectorStatus.ERROR
        assert "sayt yiqildi" in result.error
    finally:
        registry.register(PlaywrightConnector())


@pytest.mark.asyncio
async def test_missing_form_field_does_not_break_search():
    """Retseptda ko'rsatilgan maydon saytda yo'q bo'lsa ham davom etsin."""
    page = _result_page([("Rixos", "$850", "5*", "UAI")])
    del page.elements["#nights"]
    result = await PlaywrightConnector(FULL_RECIPE).search(
        _ctx(page, login="a@b.uz", password="p", login_url="https://op.uz/login")
    )
    assert result.status is ConnectorStatus.OK


# --------------------------------------------------------------------------
# build_connector
# --------------------------------------------------------------------------
def test_build_connector_from_config():
    connector = build_connector('{"row": ".c", "row_fields": {"hotel_name": ".n"}}')
    assert connector.recipe.is_usable


def test_build_connector_from_empty():
    assert not build_connector(None).recipe.is_usable
