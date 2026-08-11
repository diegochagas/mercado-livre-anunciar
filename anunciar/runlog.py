"""Log de execução em ~/.config/anunciar/logs/ + replay sem nova identificação."""

import json
import time
from pathlib import Path

from .config import LOGS_DIR


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
