"""Notificação por Telegram quando um anúncio é criado."""

import os

import requests

API_BASE = "https://api.telegram.org"


def notify_item_created(title: str, permalink: str, status: str) -> str | None:
    """Envia o link do anúncio pro Telegram. Retorna um aviso em caso de falha, senão None."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None  # notificação não configurada — silencioso

    text = f"✅ Anúncio criado ({status}): {title}\n{permalink}"
    try:
        resp = requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"Falha ao notificar no Telegram: {exc}"
    return None
