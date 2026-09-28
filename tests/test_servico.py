"""Invariantes do anúncio de serviço: payload de classificado, dry-run sem
escrita nem Telegram, publicação só com tipo de publicação escolhido."""

import json
from pathlib import Path

import pytest

from anunciar import servico, servico_cli
from anunciar.ml_api import MLError
from anunciar.tokens import AuthError

SERVICE_CATEGORY = {
    "id": "MLB63927",
    "path_from_root": [
        {"id": "MLB1540", "name": "Serviços"},
        {"id": "MLB63953", "name": "Gráficas e Impressão"},
        {"id": "MLB63927", "name": "Outros"},
    ],
    "children_categories": [],
    "settings": {"buying_modes": ["classified"], "item_conditions": ["not_allowed"]},
}
PRODUCT_CATEGORY = {
    "id": "MLB434735",
    "path_from_root": [{"id": "MLB1798", "name": "Antiguidades e Coleções"}],
    "children_categories": [],
    "settings": {"buying_modes": ["buy_it_now"]},
}
COUNTRY = {"states": [{"id": "ST-SP", "name": "São Paulo"}]}
STATE = {"cities": [{"id": "CITY-CAMPINAS", "name": "Campinas"}]}


class FakeML:
    """MLClient falso: registra toda chamada; `authed=False` simula token vencido."""

    WRITES = frozenset({"upload_picture", "create_item", "set_description", "update_item"})

    def __init__(self, authed=True, category=SERVICE_CATEGORY, validate_error=None):
        self.calls: list[tuple] = []
        self.authed = authed
        self.category_info = category
        self.validate_error = validate_error

    def _need_auth(self, auth):
        if auth and not self.authed:
            raise AuthError("Sem refresh token salvo.")

    def get(self, path, *, auth=True):
        self.calls.append(("get", path))
        if path.startswith("/categories/"):
            return self.category_info
        if path == "/classified_locations/countries/BR":
            return COUNTRY
        if path.startswith("/classified_locations/states/"):
            return STATE
        self._need_auth(auth)
        if "/available_listing_types" in path:
            return {"available": [{"id": "silver", "name": "Prata"}]}
        raise AssertionError(f"GET inesperado: {path}")

    def me(self):
        self.calls.append(("me",))
        self._need_auth(True)
        return {"id": 1, "address": {"state": "BR-SP", "city": "Campinas"}, "tags": []}

    def post(self, path, payload):
        self.calls.append(("post", path))
        self._need_auth(True)
        assert path == "/items/validate", f"POST inesperado: {path}"
        if self.validate_error:
            raise self.validate_error
        return {}

    def upload_picture(self, path):
        self.calls.append(("upload_picture", path.name))
        return {"id": f"PIC-{path.stem}"}

    def create_item(self, payload):
        self.calls.append(("create_item", payload))
        return {"id": "MLB999", "permalink": "https://ml/MLB999", "status": "active"}

    def set_description(self, item_id, text):
        self.calls.append(("set_description", item_id, text))
        return {}

    def writes(self):
        return [c for c in self.calls if c[0] in self.WRITES]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "LOGS_DIR", tmp_path / "logs")
    photos = tmp_path / "restauracao"
    photos.mkdir()
    for name in ("b-antes-depois.jpg", "a-capa.jpg"):
        (photos / name).write_bytes(b"\xff\xd8fake")
    notified: list[tuple] = []
    monkeypatch.setattr(servico_cli, "notify_success", lambda url: notified.append(("ok", url)))
    monkeypatch.setattr(servico_cli, "notify_error", lambda msg: notified.append(("err", msg)))
    monkeypatch.setattr(servico_cli, "load_dotenv", lambda *a, **k: None)
    return {"photos": photos, "notified": notified, "tmp": tmp_path}


def _use(monkeypatch, fake):
    monkeypatch.setattr(servico_cli, "MLClient", lambda site: fake)
    return fake


def _filled_template(env, **overrides) -> Path:
    path = servico.save_service_template(env["photos"])
    entry = json.loads(path.read_text())
    entry["service"].update(
        {
            "title": "Restauração de Fotos Antigas com IA Correção de Cor",
            "description": "Restauro digital de fotos antigas. Entrega em 24-48h.",
            "price_brl": 24.9,
            "category_id": "MLB63927",
            "listing_type_id": "silver",
            "state": "São Paulo",
            "city": "Campinas",
            **overrides,
        }
    )
    path.write_text(json.dumps(entry, ensure_ascii=False))
    return path


# ------------------------------------------------------------------ payload


def test_payload_is_classified_without_condition_or_shipping():
    data = {
        "title": "  Restauração   de fotos ",
        "category_id": "MLB63927",
        "price_brl": 60,
        "listing_type_id": "silver",
        "seller_contact": {"contact": "Diego", "phone": None, "email": ""},
    }
    payload = servico.build_service_payload(data, city_id="C1", pictures=[])
    assert payload["buying_mode"] == "classified"
    assert "condition" not in payload
    assert "shipping" not in payload
    assert payload["location"] == {"city": {"id": "C1"}}
    assert payload["price"] == 59.9
    assert payload["title"] == "Restauração de fotos"
    assert payload["seller_contact"] == {"contact": "Diego"}


def test_services_always_send_title_even_for_user_products_sellers():
    # ML real (2026-09-28): classificado com family_name -> "family name is invalid"
    # + "body does not contain [title]", mesmo com a conta em User Products.
    data = {"title": "X", "category_id": "MLB1", "price_brl": 10}
    payload = servico.build_service_payload(data, city_id=None, pictures=[])
    assert payload["title"] == "X" and "family_name" not in payload
    assert "location" not in payload and "seller_contact" not in payload


def test_title_over_60_is_an_error_not_a_silent_cut():
    data = {
        "title": "Restauração de Fotos Antigas com IA — Correção de Cor e Desbotamento",
        "description": "x",
        "price_brl": 24.9,
        "category_id": "MLB63927",
    }
    errors = servico.validate_service(data, [Path("a.jpg")])
    assert any("limite do ML é 60" in e for e in errors)


def test_validate_lists_every_missing_field():
    errors = servico.validate_service(dict(servico.SERVICE_TEMPLATE), [])
    assert len(errors) == 5


def test_too_many_pictures():
    data = {"title": "t", "description": "d", "price_brl": 1, "category_id": "MLB1"}
    errors = servico.validate_service(data, [Path(f"{i}.jpg") for i in range(13)])
    assert errors == ["13 fotos; máximo 12"]


def test_category_outside_services_is_rejected():
    with pytest.raises(servico.ServiceError, match="não está dentro de Serviços"):
        servico.check_service_category(FakeML(category=PRODUCT_CATEGORY), "MLB434735")


def test_non_leaf_or_non_classified_category_is_rejected():
    parent = {**SERVICE_CATEGORY, "children_categories": [{"id": "MLBX"}]}
    with pytest.raises(servico.ServiceError, match="não é folha"):
        servico.check_service_category(FakeML(category=parent), "MLB63953")
    sale = {**SERVICE_CATEGORY, "settings": {"buying_modes": ["buy_it_now"]}}
    with pytest.raises(servico.ServiceError, match="não aceita classificado"):
        servico.check_service_category(FakeML(category=sale), "MLB63927")


def test_city_resolution_ignores_accents_and_reports_unknowns():
    ml = FakeML()
    assert servico.resolve_city(ml, "sao paulo", "CAMPINAS")["id"] == "CITY-CAMPINAS"
    with pytest.raises(servico.ServiceError, match="Estado"):
        servico.resolve_city(ml, "Narnia", "X")
    with pytest.raises(servico.ServiceError, match="Cidade"):
        servico.resolve_city(ml, "São Paulo", "Atlantida")


def test_city_from_profile_maps_uf_to_state_name():
    assert servico.city_from_profile(FakeML()) == ("São Paulo", "Campinas")


# ---------------------------------------------------------------- templates


def test_templates_never_overwrite_each_other(env):
    first = servico.save_service_template(env["photos"])
    second = servico.save_service_template(env["photos"])
    assert first != second and first.exists() and second.exists()
    entry = json.loads(first.read_text())
    assert entry["kind"] == "servico"
    assert [Path(p).name for p in entry["images"]] == ["a-capa.jpg", "b-antes-depois.jpg"]


def test_cli_template_generation(env, capsys):
    assert servico_cli.main([str(env["photos"])]) == 0
    assert "Template de serviço salvo" in capsys.readouterr().out


def test_product_template_is_refused(env, monkeypatch):
    product = env["tmp"] / "produto.json"
    product.write_text(json.dumps({"folder": "x", "images": [], "identification": {}}))
    _use(monkeypatch, FakeML())
    with pytest.raises(SystemExit, match="não é um template de serviço"):
        servico_cli.main(["--dry-run", "--replay", str(product)])


def test_invalid_template_stops_before_any_ml_call(env, monkeypatch):
    fake = _use(monkeypatch, FakeML())
    path = _filled_template(env, title="x" * 61)
    with pytest.raises(SystemExit, match="Template inválido"):
        servico_cli.main(["--dry-run", "--replay", str(path)])
    assert fake.calls == []


# ------------------------------------------------------------------ dry-run


def test_dry_run_validates_without_writes_or_telegram(env, monkeypatch, capsys):
    fake = _use(monkeypatch, FakeML())
    assert servico_cli.main(["--dry-run", "--replay", str(_filled_template(env))]) == 0
    out = capsys.readouterr().out
    assert fake.writes() == []
    assert ("post", "/items/validate") in fake.calls
    assert env["notified"] == []
    assert '"buying_mode": "classified"' in out and "CITY-CAMPINAS" in out
    assert "/items/validate: OK" in out


def test_dry_run_without_tokens_still_checks_public_data(env, monkeypatch, capsys):
    fake = _use(monkeypatch, FakeML(authed=False))
    assert servico_cli.main(["--dry-run", "--replay", str(_filled_template(env))]) == 0
    out = capsys.readouterr().out
    assert fake.writes() == [] and env["notified"] == []
    assert ("post", "/items/validate") not in fake.calls
    assert "Sem autenticação no ML" in out
    assert "Serviços > Gráficas e Impressão > Outros" in out
    assert "CITY-CAMPINAS" in out


def test_dry_run_reports_validate_causes(env, monkeypatch, capsys):
    err = MLError("POST /items/validate: HTTP 400", 400, {"cause": [{"message": "bad x"}]})
    _use(monkeypatch, FakeML(validate_error=err))
    assert servico_cli.main(["--dry-run", "--replay", str(_filled_template(env))]) == 0
    assert "/items/validate: bad x" in capsys.readouterr().out
    assert env["notified"] == []


def test_dry_run_explains_paid_listing_type(env, monkeypatch, capsys):
    err = MLError("POST /items/validate: HTTP 402", 402, {"status": "payment_required"})
    _use(monkeypatch, FakeML(validate_error=err))
    assert servico_cli.main(["--dry-run", "--replay", str(_filled_template(env))]) == 0
    assert "nasce payment_required" in capsys.readouterr().out


def test_dry_run_without_listing_type_lists_options_and_skips_validate(env, monkeypatch, capsys):
    fake = _use(monkeypatch, FakeML())
    path = _filled_template(env, listing_type_id=None)
    assert servico_cli.main(["--dry-run", "--replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "listing_type_id não escolhido. Disponíveis: silver (Prata)" in out
    assert "/items/validate pulado" in out
    assert ("post", "/items/validate") not in fake.calls


def test_dry_run_with_wrong_category_warns_instead_of_failing(env, monkeypatch, capsys):
    _use(monkeypatch, FakeML(category=PRODUCT_CATEGORY))
    assert servico_cli.main(["--dry-run", "--replay", str(_filled_template(env))]) == 0
    out = capsys.readouterr().out
    assert "não está dentro de Serviços" in out and "(não conferida)" in out


def test_dry_run_uses_account_city_when_template_has_none(env, monkeypatch, capsys):
    _use(monkeypatch, FakeML())
    path = _filled_template(env, city=None, state=None)
    assert servico_cli.main(["--dry-run", "--replay", str(path)]) == 0
    assert "via endereço da conta ML" in capsys.readouterr().out


# ------------------------------------------------------------------ publish


def test_publish_refuses_without_listing_type(env, monkeypatch):
    fake = _use(monkeypatch, FakeML())
    path = _filled_template(env, listing_type_id=None)
    assert servico_cli.main(["--replay", str(path)]) == 1
    assert fake.writes() == []
    assert env["notified"][0][0] == "err"


def test_publish_refuses_without_tokens(env, monkeypatch):
    fake = _use(monkeypatch, FakeML(authed=False))
    assert servico_cli.main(["--replay", str(_filled_template(env))]) == 1
    assert fake.writes() == []


def test_publish_creates_active_item_with_description(env, monkeypatch, capsys):
    fake = _use(monkeypatch, FakeML())
    assert servico_cli.main(["--replay", str(_filled_template(env))]) == 0
    kinds = [c[0] for c in fake.writes()]
    assert kinds == ["upload_picture", "upload_picture", "create_item", "set_description"]
    payload = next(c[1] for c in fake.calls if c[0] == "create_item")
    assert payload["pictures"] == [{"id": "PIC-a-capa"}, {"id": "PIC-b-antes-depois"}]
    assert payload["buying_mode"] == "classified" and "condition" not in payload
    assert env["notified"] == [("ok", "https://ml/MLB999")]
    assert "MLB999" in capsys.readouterr().out
