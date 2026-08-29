"""Notificação por Telegram: silenciosa em caso de sucesso (só a URL do
anúncio), e um alerta em caso de erro na criação."""

import os

import requests

API_BASE = "https://api.telegram.org"


def _send(text: str) -> str | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None  # notificação não configurada — silencioso

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


def notify_success(permalink: str) -> str | None:
    """Envia só a URL do anúncio criado. Retorna um aviso em caso de falha, senão None."""
    return _send(permalink)


def notify_error(message: str) -> str | None:
    """Notifica falha na criação do anúncio. Retorna um aviso em caso de falha, senão None."""
    return _send(f"❌ Falha ao criar anúncio no Mercado Livre:\n{message}")
