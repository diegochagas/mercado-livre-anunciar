"""Montagem do anúncio: categoria, atributos, sale_terms, payload e publicação.

Segue a estrutura vigente de publicação (POST /items). Se o vendedor já estiver
migrado para User Products (tag "user_product_seller" em /users/me), o campo
`title` é substituído por `family_name`, conforme a nova estrutura.
"""

import unicodedata
from pathlib import Path

from .config import Config
from .ml_api import MLClient

# categoria raiz e subcategorias de fallback para publicações
_BOOKS_ROOT_HINT = "livros"
_FALLBACK_KEYWORDS = {
    "pamphlet": ["catálogos", "catalogos"],
    "panfleto": ["catálogos", "catalogos"],
    "catálogo": ["catálogos", "catalogos"],
    "catalogo": ["catálogos", "catalogos"],
    "programa": ["catálogos", "catalogos"],
    "revista": ["revistas"],
    "hq": ["quadrinhos", "gibis", "hqs", "livros físicos", "livros fisicos"],
    "mangá": ["quadrinhos", "mangás", "mangas", "livros físicos", "livros fisicos"],
    "manga": ["quadrinhos", "mangás", "mangas", "livros físicos", "livros fisicos"],
    "gibi": ["quadrinhos", "gibis", "livros físicos", "livros fisicos"],
    "livro": ["livros físicos", "livros fisicos", "livros"],
    "artbook": ["livros físicos", "livros fisicos", "livros"],
}

# atributo da categoria -> campo da identificação
_ATTR_SOURCES = {
    "BRAND": "brand",
    "MODEL": "model",
    "ISBN": "isbn_ean",
    "GTIN": "isbn_ean",
    "AUTHOR": "author_or_cast",
    "BOOK_AUTHOR": "author_or_cast",
    "PUBLISHER": "publisher",
    "BOOK_PUBLISHER": "publisher",
    "LANGUAGE": "language",
    "BOOK_LANGUAGE": "language",
    "PUBLICATION_YEAR": "year",
    "BOOK_PUBLICATION_YEAR": "year",
    "PAGES_NUMBER": "pages",
    "BOOK_PAGES_NUMBER": "pages",
    "BOOK_TITLE": "full_name",
    "TITLE": "full_name",
    "MAGAZINE_NAME": "full_name",
}

_NA_VALUE_NAMES = {"n/a", "não aplica", "nao aplica", "não se aplica", "nao se aplica"}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def truncate_title(title: str, limit: int = 60) -> str:
    title = " ".join((title or "").split())
    if len(title) <= limit:
        return title
    cut = title[: limit + 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut[:limit].strip()


def is_user_products_seller(ml: MLClient) -> bool:
    try:
        return "user_product_seller" in (ml.me().get("tags") or [])
    except Exception:
        return False


def resolve_listing_type(ml: MLClient, cfg: Config) -> tuple[str, str]:
    """Resolve "premium" dinamicamente via /sites/{site}/listing_types."""
    wanted = str(cfg.listing["listing_type"]).strip()
    types = ml.listing_types()
    if _norm(wanted) in {"premium", "clássico", "classico", "grátis", "gratis"}:
        for entry in types:
            if _norm(entry.get("name", "")) == _norm(wanted):
                return entry["id"], entry.get("name", wanted)
    for entry in types:
        if entry.get("id") == wanted:
            return entry["id"], entry.get("name", wanted)
    raise SystemExit(
        f"Tipo de publicação '{wanted}' não encontrado em listing_types: "
        + ", ".join(f"{t['id']} ({t.get('name')})" for t in types)
    )


def _category_root_name(ml: MLClient, category_id: str) -> tuple[str, list[str]]:
    info = ml.category(category_id)
    path = [p.get("name", "") for p in info.get("path_from_root", [])]
    return (path[0] if path else info.get("name", "")), path


def _find_books_fallback(ml: MLClient, product_type: str) -> str | None:
    keywords = None
    ptype = _norm(product_type)
    for key, kws in _FALLBACK_KEYWORDS.items():
        if _norm(key) in ptype or ptype in _norm(key):
            keywords = kws
            break
    if keywords is None:
        keywords = ["livros físicos", "livros fisicos", "livros"]

    roots = ml.site_categories()
    books_root = next(
        (r for r in roots if _BOOKS_ROOT_HINT in _norm(r.get("name", ""))), None
    )
    if not books_root:
        return None

    # busca em largura até 3 níveis dentro de "Livros, Revistas e Comics"
    queue = [books_root["id"]]
    depth = 0
    while queue and depth < 3:
        next_queue = []
        for cat_id in queue:
            info = ml.category(cat_id)
            for child in info.get("children_categories", []):
                child_name = _norm(child.get("name", ""))
                if any(_norm(kw) == child_name or _norm(kw) in child_name
                       for kw in keywords):
                    return _descend_to_leaf(ml, child["id"])
                next_queue.append(child["id"])
        queue = next_queue
        depth += 1
    return None


def _descend_to_leaf(ml: MLClient, category_id: str) -> str:
    """Se a categoria tiver filhos, tenta um filho genérico ('Outros'); senão fica."""
    info = ml.category(category_id)
    children = info.get("children_categories", [])
    if not children:
        return category_id
    other = next(
        (c for c in children if _norm(c.get("name", "")).startswith("outr")), None
    )
    if other:
        return _descend_to_leaf(ml, other["id"])
    return category_id


def resolve_category(ml: MLClient, data: dict, cfg: Config) -> tuple[str, str]:
    """Predição por domain_discovery com fallback para a árvore de Livros."""
    query = data["title_ml"]
    predictions = ml.domain_discovery(query)
    predicted = predictions[0]["category_id"] if predictions else None

    book_like = _norm(data.get("product_type", "")) in {
        _norm(k) for k in _FALLBACK_KEYWORDS
    }

    if predicted:
        root_name, path = _category_root_name(ml, predicted)
        if not book_like or _BOOKS_ROOT_HINT in _norm(root_name):
            return predicted, " > ".join(path)
        # predição fora de Livros para um item que é publicação: tenta fallback
        fallback = _find_books_fallback(ml, data.get("product_type", ""))
        if fallback:
            _, path = _category_root_name(ml, fallback)
            return fallback, " > ".join(path) + " (fallback)"
        return predicted, " > ".join(path) + " (predição mantida)"

    fallback = _find_books_fallback(ml, data.get("product_type", ""))
    if fallback:
        _, path = _category_root_name(ml, fallback)
        return fallback, " > ".join(path) + " (fallback)"
    raise SystemExit("Não foi possível determinar a categoria do anúncio.")


def _match_list_value(attr: dict, wanted: str) -> dict | None:
    wanted_n = _norm(str(wanted))
    for value in attr.get("values") or []:
        name_n = _norm(value.get("name", ""))
        if name_n == wanted_n or wanted_n in name_n or name_n in wanted_n:
            return value
    return None


def build_attributes(
    ml: MLClient, category_id: str, data: dict, cfg: Config
) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    attrs: list[dict] = []
    condition_name = "usado" if cfg.listing["condition"] == "used" else "novo"

    for attr in ml.category_attributes(category_id):
        attr_id = attr.get("id", "")
        tags = attr.get("tags") or {}
        required = bool(tags.get("required"))
        has_values = bool(attr.get("values"))

        if attr_id == "ITEM_CONDITION":
            value = _match_list_value(attr, condition_name)
            if value:
                attrs.append({"id": attr_id, "value_id": value["id"]})
            else:
                attrs.append({"id": attr_id, "value_name": condition_name.capitalize()})
            continue

        source = _ATTR_SOURCES.get(attr_id)
        raw = data.get(source) if source else None
        if raw not in (None, ""):
            if has_values:
                value = _match_list_value(attr, str(raw))
                if value:
                    attrs.append({"id": attr_id, "value_id": value["id"]})
                elif required:
                    notes.append(
                        f"Atributo {attr_id}: valor '{raw}' não consta na lista "
                        "de valores da categoria; não enviado."
                    )
            else:
                attrs.append({"id": attr_id, "value_name": str(raw)})
            continue

        if required:
            na = next(
                (
                    v
                    for v in attr.get("values") or []
                    if _norm(v.get("name", "")) in _NA_VALUE_NAMES
                ),
                None,
            )
            if na:
                attrs.append({"id": attr_id, "value_id": na["id"]})
                notes.append(f"Atributo obrigatório {attr_id} preenchido com N/A.")
            else:
                notes.append(
                    f"Atributo obrigatório {attr_id} ({attr.get('name')}) sem dado "
                    "pesquisado e sem valor N/A — pode gerar erro de validação."
                )
    return attrs, notes


def build_sale_terms(
    ml: MLClient, category_id: str, cfg: Config
) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    terms: list[dict] = []
    available = {t.get("id"): t for t in ml.category_sale_terms(category_id)}

    if cfg.listing["warranty"] == "none" and "WARRANTY_TYPE" in available:
        value = _match_list_value(available["WARRANTY_TYPE"], "sem garantia")
        if value:
            terms.append({"id": "WARRANTY_TYPE", "value_id": value["id"]})
        else:
            terms.append({"id": "WARRANTY_TYPE", "value_name": "Sem garantia"})
    elif cfg.listing["warranty"] == "none":
        notes.append("Categoria não expõe WARRANTY_TYPE; garantia não enviada.")

    days = int(cfg.listing["availability_days"])
    if "MANUFACTURING_TIME" in available:
        terms.append({"id": "MANUFACTURING_TIME", "value_name": f"{days} dias"})
    return terms, notes


def build_shipping(price: float, cfg: Config) -> dict:
    if cfg.shipping.get("flex"):
        raise SystemExit(
            "shipping.flex=true não é suportado: Flex nunca deve ser habilitado "
            "(regra de negócio fixa). Ajuste config.toml para flex = false."
        )
    free = price > float(cfg.shipping["free_shipping_threshold"])
    return {
        "mode": "me2",
        "local_pick_up": False,
        "free_shipping": free,
    }


def build_payload(
    *,
    title: str,
    category_id: str,
    price: float,
    listing_type_id: str,
    attributes: list[dict],
    sale_terms: list[dict],
    shipping: dict,
    cfg: Config,
    up_seller: bool,
    pictures: list[dict] | None = None,
) -> dict:
    payload = {
        "site_id": cfg.listing["site_id"],
        "category_id": category_id,
        "price": price,
        "currency_id": "BRL",
        "available_quantity": int(cfg.listing["available_quantity"]),
        "buying_mode": "buy_it_now",
        "condition": cfg.listing["condition"],
        "listing_type_id": listing_type_id,
        "attributes": attributes,
        "sale_terms": sale_terms,
        "shipping": shipping,
        "pictures": pictures or [],
    }
    # User Products: title deixa de ser enviado; family_name assume a função
    if up_seller:
        payload["family_name"] = title
    else:
        payload["title"] = title
    return payload


def upload_pictures(ml: MLClient, images: list[Path]) -> list[dict]:
    ids = []
    for path in images:
        result = ml.upload_picture(path)
        pic_id = result.get("id")
        if not pic_id:
            raise SystemExit(f"Upload de {path.name} não retornou id: {result}")
        print(f"  foto enviada: {path.name} -> {pic_id}")
        ids.append({"id": pic_id})
    return ids
