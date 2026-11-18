"""Book Menu (o catálogo da biblioteca do Diego, em BOOK_MENU_URL) como primeira fonte
dos dados de um livro, HQ ou mangá à venda.

Antes de pesquisar na web, quem identifica o produto procura o item no Book Menu
(`anunciar --book-menu-search "bakuman 1"`) e, achando, gera o template já
preenchido (`anunciar <pasta> --book-menu-id bakuman-1`). Só vêm do Book Menu os
campos que ele tem de fato (editora, ano, páginas, formato, ISBN, créditos, resumo);
o resto — estado, pesquisa de preço, embalagem que faltar — continua sendo
preenchido à mão. Nada é inventado: campo ausente = None.

Exemplo:
    client = BookMenuClient("http://servidor:3070")
    item = client.get("bakuman-1")
    identification = identification_from_item(item)
"""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

TIMEOUT_S = 15

PRODUCT_TYPES = {
    "manga": "Mangá",
    "comic": "HQ",
    "book": "Livro",
    "novel": "Livro",
    "mook": "Livro",
    "artbook": "Livro de arte",
    "magazine": "Revista",
    "other": "Livro",
}
LANGUAGES = {"pt": "Português", "ja": "Japonês", "zh": "Chinês", "en": "Inglês", "es": "Espanhol"}
COUNTRIES = {"br": "Brasil", "jp": "Japão", "cn": "China", "us": "Estados Unidos"}
AUTHOR_ROLES = ("Roteiro", "História", "Argumento", "Autor", "Arte", "Desenho", "Texto")
CONTEXT_MAX_CHARS = 700
PACKAGE_MARGIN_CM = 2


class BookMenuError(Exception):
    pass


class HttpSession(Protocol):
    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> Any: ...


class BookMenuClient:
    """Leitura da API /api/v1/items do Book Menu."""

    def __init__(self, base_url: str, session: HttpSession | None = None):
        if not base_url:
            raise BookMenuError("BOOK_MENU_URL vazio: defina no .env o endereço do Book Menu")
        if session is None:
            import requests

            session = requests.Session()
        self.base_url = base_url.rstrip("/")
        self.session = session

    def _get(self, path: str, params: dict | None = None) -> Any:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=TIMEOUT_S)
        if response.status_code == 404:
            raise BookMenuError(f"Book Menu não tem {path}")
        if response.status_code >= 400:
            raise BookMenuError(
                f"Book Menu respondeu {response.status_code} em {path}: {response.text[:200]}"
            )
        return response.json()

    def search(self, query: str, include_wishlist: bool = False) -> list[dict]:
        """Itens físicos com todas as palavras do texto (título, série, editora, ISBN); por padrão só os que o Diego tem."""
        # Só itens físicos: e-books (digital) não se vendem no ML.
        params = {"search": query, "digital": "false"}
        if not include_wishlist:
            params["ownership"] = "owned"
        return self._get("/api/v1/items", params)["items"]

    def get(self, item_id: str) -> dict:
        return self._get(f"/api/v1/items/{item_id}")


def client_from_env() -> BookMenuClient:
    return BookMenuClient(os.environ.get("BOOK_MENU_URL", ""))


def _dimensions(fmt: str | None) -> tuple[float, float] | None:
    """'(13,5 x 20,5 cm) Preto e branco' -> (13.5, 20.5)."""
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*cm", fmt or "")
    if not match:
        return None
    return float(match.group(1).replace(",", ".")), float(match.group(2).replace(",", "."))


def _authors(item: dict) -> str | None:
    credits = list(item.get("credits") or [])
    for story in item.get("stories") or []:
        credits.extend(story.get("credits") or [])
    names: list[str] = []
    for credit in credits:
        if credit.get("role") in AUTHOR_ROLES:
            names.extend(n for n in credit.get("names", []) if n not in names)
    return ", ".join(names) or None


def _language(item: dict) -> str | None:
    code = (item.get("language") or "").split("-")[0].lower()
    return LANGUAGES.get(code)


def _package(item: dict) -> dict:
    """Altura/largura da embalagem = formato + margem; comprimento e peso só se conhecidos."""
    size = _dimensions(item.get("format"))
    return {
        "height_cm": round(size[1] + PACKAGE_MARGIN_CM, 1) if size else None,
        "width_cm": round(size[0] + PACKAGE_MARGIN_CM, 1) if size else None,
        "length_cm": None,
        "weight_g": item.get("weightGrams"),
    }


def _context(item: dict) -> str | None:
    summary = (item.get("summary") or "").strip()
    if not summary:
        return None
    return (
        summary
        if len(summary) <= CONTEXT_MAX_CHARS
        else summary[: CONTEXT_MAX_CHARS - 1].rstrip() + "…"
    )


def identification_from_item(item: dict) -> dict:
    """Campos de `identification` (ver runlog.TEMPLATE_IDENTIFICATION) que o Book Menu sabe."""
    size = _dimensions(item.get("format"))
    return {
        "title_ml": item.get("title"),
        "product_type": PRODUCT_TYPES.get(item.get("category", ""), "Livro"),
        "full_name": item.get("title"),
        "original_name": item.get("originalTitle"),
        "author_or_cast": _authors(item),
        "publisher": item.get("publisher"),
        "isbn_ean": item.get("isbn"),
        "pages": item.get("pages"),
        "dimensions": f"{size[0]:g} x {size[1]:g} cm".replace(".", ",") if size else None,
        "package": _package(item),
        "language": _language(item),
        "year": item.get("publishedYear"),
        "country_of_origin": COUNTRIES.get(item.get("origin", "")),
        "context": _context(item),
    }


def describe_match(item: dict) -> str:
    """Uma linha por resultado de busca, para escolher o id certo."""
    bits = [item.get("publisher"), str(item.get("publishedYear") or ""), item.get("isbn")]
    owner = f" [de {item['ownerName']}]" if item.get("ownerName") else ""
    return f"{item['id']}\t{item.get('title')}\t{' · '.join(b for b in bits if b)}{owner}"
