"""Log de execução em ~/.config/anunciar/logs/ + replay sem nova identificação."""

import json
import time
from pathlib import Path

from .config import LOGS_DIR
from .images import list_images

# Preencha à mão (identificação e pesquisa de preço feitas por quem estiver
# rodando o comando) e rode `anunciar --replay`.
TEMPLATE_IDENTIFICATION = {
    "title_ml": None,
    "product_type": None,
    "full_name": None,
    "original_name": None,
    "brand": None,
    "model": None,
    "author_or_cast": None,
    "publisher": None,
    "isbn_ean": None,
    "pages": None,
    "dimensions": None,
    # embalagem de envio (obrigatório no ML): cm e gramas
    "package": {"height_cm": None, "width_cm": None, "length_cm": None, "weight_g": None},
    "language": None,
    "year": None,
    "country_of_origin": None,
    "context": None,
    "origin_where_sold": None,
    "event_edition_location_dates": None,
    "condition_notes": None,
    "condition_override": None,
    "format_override": None,
    "is_imported_rare": False,
    "price_research": [],
    "suggested_price_brl": None,
}


def save_template(folder: Path, prefill: dict | None = None, source: dict | None = None) -> Path:
    """Gera um JSON no formato de log (pronto para --replay) com a
    identificação em branco, para preenchimento manual sem chamar a Anthropic.
    `prefill` (ex.: dados do Book Menu) preenche os campos que tiver; `source`
    registra de onde vieram (id/URL do item)."""
    images = list_images(folder)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = LOGS_DIR / f"template-{stamp}.json"
    entry = {
        "folder": str(folder),
        "images": [str(p) for p in images],
        "identification": _merge_prefill(prefill or {}),
    }
    if source:
        entry["source"] = source
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _merge_prefill(prefill: dict) -> dict:
    merged = json.loads(json.dumps(TEMPLATE_IDENTIFICATION))
    for key, value in prefill.items():
        if key == "package" and isinstance(value, dict):
            merged["package"].update({k: v for k, v in value.items() if v is not None})
        elif value is not None:
            merged[key] = value
    return merged


def save_log(entry: dict) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = LOGS_DIR / f"run-{stamp}.json"
    path.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def load_log(path: str) -> dict:
    log_path = Path(path).expanduser()
    if not log_path.exists():
        candidate = LOGS_DIR / path
        if candidate.exists():
            log_path = candidate
        else:
            raise SystemExit(f"Log não encontrado: {path}")
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Log inválido ({log_path}): {exc}")
