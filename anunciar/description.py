"""Monta a descrição pt-BR do anúncio a partir dos dados pesquisados.

Nunca inclui linha de "Detalhes" cujo dado não foi encontrado — sem enchimento.
"""

from .config import Config


def _detail_lines(data: dict) -> list[str]:
    lines: list[str] = []
    if data.get("origin_where_sold"):
        lines.append(f"- {data['origin_where_sold']}")
    if data.get("event_edition_location_dates"):
        lines.append(f"- {data['event_edition_location_dates']}")
    if data.get("author_or_cast"):
        lines.append(f"- Autor/elenco: {data['author_or_cast']}")
    if data.get("publisher"):
        pub = f"- Editora: {data['publisher']}"
        if data.get("isbn_ean"):
            pub += f" — ISBN/Código universal: {data['isbn_ean']}"
        lines.append(pub)
    elif data.get("isbn_ean"):
        lines.append(f"- ISBN/Código universal: {data['isbn_ean']}")
    fmt_bits = []
    if data.get("dimensions"):
        fmt_bits.append(data["dimensions"])
    if data.get("pages"):
        fmt_bits.append(f"{data['pages']} páginas")
    if fmt_bits:
        lines.append(f"- Formato: {', '.join(fmt_bits)}")
    if data.get("language"):
        lines.append(f"- Idioma: {data['language']}")
    if data.get("year"):
        lines.append(f"- Ano de publicação: {data['year']}")
    return lines


def build_description(data: dict, cfg: Config) -> str:
    parts: list[str] = []

    tipo = (data.get("product_type") or "Item").capitalize()
    nome = (data.get("full_name") or "").strip()
    original = data.get("original_name")
    # se full_name já começa com o tipo ("Pamphlet oficial ..."), não duplica
    if nome.lower().startswith(tipo.lower()):
        header = nome[0].upper() + nome[1:]
    else:
        header = f"{tipo} oficial {nome}"
    if original and original.strip() and original.strip() != nome.strip():
        header += f" ({original})"
    context = (data.get("context") or "").strip()
    if context:
        header += f", {context[0].lower()}{context[1:]}" if context[0].isupper() else f", {context}"
    if not header.endswith("."):
        header += "."
    parts.append(header)

    if data.get("is_imported_rare"):
        pais = data.get("country_of_origin") or "exterior"
        parts.append(cfg.description["rare_import_line"].replace("{país}", pais))

    details = _detail_lines(data)
    if details:
        parts.append("Detalhes:\n" + "\n".join(details))

    if data.get("condition_notes"):
        parts.append(f"Estado de conservação: {data['condition_notes']}")

    parts.append(cfg.description["closing_line"])
    return "\n\n".join(parts)
