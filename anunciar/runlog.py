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
    "language": None,
    "year": None,
    "country_of_origin": None,
    "context": None,
    "origin_where_sold": None,
    "event_edition_location_dates": None,
    "condition_notes": None,
    "is_imported_rare": False,
    "price_research": [],
    "suggested_price_brl": None,
}


def save_template(folder: Path) -> Path:
    """Gera um JSON no formato de log (pronto para --replay) com a
    identificação em branco, para preenchimento manual sem chamar a Anthropic."""
    images = list_images(folder)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = LOGS_DIR / f"template-{stamp}.json"
    entry = {
        "folder": str(folder),
        "images": [str(p) for p in images],
        "identification": TEMPLATE_IDENTIFICATION,
    }
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


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
