"""Book Menu como fonte dos dados do livro: busca, mapeamento e template pré-preenchido."""

import json

import pytest

from anunciar import book_menu, runlog

BAKUMAN = {
    "id": "bakuman-1",
    "title": "Bakuman n° 1",
    "originalTitle": "バクマン。 1",
    "category": "manga",
    "origin": "br",
    "language": "pt-BR",
    "publisher": "JBC",
    "publishedYear": 2011,
    "pages": 212,
    "format": "(13,5 x 20,5 cm) Preto e branco/Lombada quadrada",
    "isbn": "9788577875603",
    "summary": "Mashiro e Takagi querem ser mangakás.",
    "credits": [{"role": "Arte", "names": ["Takeshi Obata"]}],
    "stories": [{"title": "Cap. 1", "credits": [{"role": "Roteiro", "names": ["Tsugumi Ohba"]}]}],
}


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeBookMenuSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        path = url.split("http://book-menu.test", 1)[1]
        status, body = self.routes.get(path, (404, {"error": "not found"}))
        return FakeResponse(status, body)


def make_client(routes):
    session = FakeBookMenuSession(routes)
    return book_menu.BookMenuClient("http://book-menu.test/", session), session


def test_search_asks_for_owned_items_only_by_default():
    client, session = make_client({"/api/v1/items": (200, {"items": [BAKUMAN]})})
    assert client.search("bakuman 1") == [BAKUMAN]
    _url, params, timeout = session.calls[0]
    assert params == {"search": "bakuman 1", "digital": "false", "ownership": "owned"}
    assert timeout == book_menu.TIMEOUT_S


def test_get_reports_missing_items_and_server_errors():
    client, _ = make_client({"/api/v1/items/boom": (500, {"error": "x"})})
    with pytest.raises(book_menu.BookMenuError, match="nope"):
        client.get("nope")
    with pytest.raises(book_menu.BookMenuError, match="500"):
        client.get("boom")


def test_empty_url_is_a_clear_error():
    with pytest.raises(book_menu.BookMenuError, match="BOOK_MENU_URL"):
        book_menu.BookMenuClient("")


def test_identification_uses_only_what_book_menu_knows():
    data = book_menu.identification_from_item(BAKUMAN)
    assert data["product_type"] == "Mangá"
    assert data["publisher"] == "JBC"
    assert data["isbn_ean"] == "9788577875603"
    assert data["dimensions"] == "13,5 x 20,5 cm"
    assert data["author_or_cast"] == "Takeshi Obata, Tsugumi Ohba"
    assert data["language"] == "Português"
    assert data["country_of_origin"] == "Brasil"
    # embalagem: formato + margem; espessura e peso não são inventados
    assert data["package"] == {
        "height_cm": 22.5,
        "width_cm": 15.5,
        "length_cm": None,
        "weight_g": None,
    }
    assert "suggested_price_brl" not in data


def test_template_keeps_blank_fields_and_records_the_source(tmp_path, monkeypatch):
    monkeypatch.setattr(runlog, "LOGS_DIR", tmp_path / "logs")
    photos = tmp_path / "fotos"
    photos.mkdir()
    (photos / "1.jpg").write_bytes(b"x")
    prefill = book_menu.identification_from_item({**BAKUMAN, "weightGrams": 250})
    path = runlog.save_template(photos, prefill, {"book_menu_id": "bakuman-1"})
    entry = json.loads(path.read_text())
    ident = entry["identification"]
    assert ident["full_name"] == "Bakuman n° 1"
    assert ident["suggested_price_brl"] is None
    assert ident["condition_notes"] is None
    assert ident["package"]["weight_g"] == 250
    assert entry["source"] == {"book_menu_id": "bakuman-1"}
    assert runlog.TEMPLATE_IDENTIFICATION["full_name"] is None  # o modelo global não muda
