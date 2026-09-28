"""Anúncio de SERVIÇO no Mercado Livre (classificado em Serviços, MLB1540).

Diferenças para o fluxo de produto (cli.py / listing.py):

- categorias de Serviços só aceitam `buying_mode: classified`;
- `condition` não é permitida (item_conditions = not_allowed) — não é enviada;
- não há Mercado Envios nem frete grátis — `shipping` não é enviado;
- `location` (cidade do classificado) é obrigatória;
- tipo de publicação é de classificado (pode ter custo) e precisa ser
  escolhido explicitamente — vem de /users/{id}/available_listing_types;
- título até 60 caracteres: acima disso é ERRO, nunca corte silencioso;
- descrição é o texto livre do template, sem frases de produto físico;
- sempre `title` (User Products/`family_name` não vale para classificado).
"""

import json
import re
import time
import unicodedata
from pathlib import Path

from .config import LOGS_DIR
from .images import list_images
from .ml_api import MLClient
from .pricing import normalize_ending

SERVICES_ROOT = "MLB1540"
TITLE_LIMIT = 60
MAX_PICTURES = 12

SERVICE_TEMPLATE = {
    "title": None,
    "description": None,
    "price_brl": None,
    "category_id": None,
    "listing_type_id": None,
    "city": None,
    "state": None,
    "seller_contact": {
        "contact": None,
        "area_code": None,
        "phone": None,
        "email": None,
        "other_info": None,
    },
    "notes": None,
}


class ServiceError(Exception):
    pass


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-") or "servico"


def unique_path(prefix: str, name: str) -> Path:
    """Arquivo novo em LOGS_DIR que nunca sobrescreve outro (mesmo segundo)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = f"{prefix}-{_slug(name)}-{stamp}"
    path = LOGS_DIR / f"{base}.json"
    n = 2
    while path.exists():
        path = LOGS_DIR / f"{base}-{n}.json"
        n += 1
    return path


def _write(path: Path, entry: dict) -> Path:
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_service_template(folder: Path) -> Path:
    images = list_images(folder)
    entry = {
        "kind": "servico",
        "folder": str(folder),
        "images": [str(p) for p in images],
        "service": json.loads(json.dumps(SERVICE_TEMPLATE)),
    }
    return _write(unique_path("servico-template", folder.name), entry)


def save_service_log(entry: dict, mode: str) -> Path:
    name = Path(entry.get("folder") or "servico").name
    return _write(unique_path(f"servico-{mode}", name), {**entry, "mode": mode})


def validate_service(data: dict, images: list) -> list[str]:
    """Erros que impedem até o dry-run (lista vazia = ok)."""
    errors = []
    title = " ".join((data.get("title") or "").split())
    if not title:
        errors.append("title vazio")
    elif len(title) > TITLE_LIMIT:
        errors.append(
            f"title tem {len(title)} caracteres; o limite do ML é {TITLE_LIMIT} "
            "(encurte à mão — não há corte automático)"
        )
    if not (data.get("description") or "").strip():
        errors.append("description vazia")
    price = data.get("price_brl")
    if not isinstance(price, (int, float)) or price <= 0:
        errors.append("price_brl precisa ser um número > 0")
    if not re.fullmatch(r"MLB\d+", str(data.get("category_id") or "")):
        errors.append("category_id precisa ser um id de categoria de Serviços (MLB...)")
    if not images:
        errors.append("nenhuma foto no template")
    elif len(images) > MAX_PICTURES:
        errors.append(f"{len(images)} fotos; máximo {MAX_PICTURES}")
    return errors


def check_service_category(ml: MLClient, category_id: str) -> str:
    """Confere que a categoria é folha dentro de Serviços e é de classificado."""
    info = ml.get(f"/categories/{category_id}", auth=False)
    path = [p.get("id") for p in info.get("path_from_root", [])]
    names = " > ".join(p.get("name", "") for p in info.get("path_from_root", []))
    if not path or path[0] != SERVICES_ROOT:
        raise ServiceError(f"{category_id} ({names}) não está dentro de Serviços ({SERVICES_ROOT})")
    if info.get("children_categories"):
        raise ServiceError(f"{category_id} ({names}) não é folha; escolha uma subcategoria")
    modes = (info.get("settings") or {}).get("buying_modes") or []
    if "classified" not in modes:
        raise ServiceError(f"{category_id} não aceita classificado (buying_modes={modes})")
    return names


def resolve_city(ml: MLClient, state: str, city: str) -> dict:
    """Nome de estado/cidade -> {"id", "name"} da cidade (endpoints públicos)."""
    country = ml.get("/classified_locations/countries/BR", auth=False)
    st = next((s for s in country.get("states", []) if _norm(s["name"]) == _norm(state)), None)
    if not st:
        raise ServiceError(f"Estado '{state}' não encontrado em classified_locations")
    info = ml.get(f"/classified_locations/states/{st['id']}", auth=False)
    ct = next((c for c in info.get("cities", []) if _norm(c["name"]) == _norm(city)), None)
    if not ct:
        raise ServiceError(f"Cidade '{city}' não encontrada em {st['name']}")
    return {"id": ct["id"], "name": ct["name"], "state": st["name"]}


def city_from_profile(ml: MLClient) -> tuple[str | None, str | None]:
    """Cidade/estado do endereço cadastrado na conta (fallback do template)."""
    me = ml.me()
    addr = me.get("address") or {}
    state = addr.get("state") or ""
    # /users/me costuma trazer "BR-SP"; classified_locations usa o nome
    state = _STATE_BY_UF.get(state.replace("BR-", "").upper(), state) or None
    return state, addr.get("city") or None


def available_listing_types(ml: MLClient, category_id: str) -> list[dict]:
    uid = ml.me()["id"]
    resp = ml.get(f"/users/{uid}/available_listing_types?category_id={category_id}")
    return resp.get("available", []) if isinstance(resp, dict) else resp


def _clean_contact(contact: dict | None) -> dict | None:
    contact = {k: v for k, v in (contact or {}).items() if v not in (None, "")}
    return contact or None


def build_service_payload(data: dict, *, city_id: str | None, pictures: list[dict]) -> dict:
    title = " ".join(data["title"].split())
    payload = {
        "site_id": "MLB",
        "category_id": data["category_id"],
        "price": normalize_ending(float(data["price_brl"])),
        "currency_id": "BRL",
        "available_quantity": 1,
        "buying_mode": "classified",
        "listing_type_id": data.get("listing_type_id"),
        "pictures": pictures,
    }
    if city_id:
        payload["location"] = {"city": {"id": city_id}}
    contact = _clean_contact(data.get("seller_contact"))
    if contact:
        payload["seller_contact"] = contact
    # Classificado não usa User Products: sempre `title`, nunca `family_name`
    # (o ML rejeita family_name em Serviços mesmo em conta migrada).
    payload["title"] = title
    return payload


_STATE_BY_UF = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}
