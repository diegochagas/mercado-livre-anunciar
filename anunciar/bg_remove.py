"""Remoção de fundo via API self-hosted do withoutbg (WITHOUTBG_URL no .env)."""

import os

import requests


def remove_background(image_bytes: bytes, content_type: str = "image/jpeg") -> bytes:
    """Envia a imagem para a API withoutbg e devolve o PNG RGBA (fundo removido)."""
    url = os.environ.get("WITHOUTBG_URL")
    if not url:
        raise SystemExit("WITHOUTBG_URL não configurada no .env.")
    resp = requests.post(
        f"{url.rstrip('/')}/v1/remove-background",
        params={"output": "cutout"},
        data=image_bytes,
        headers={"Content-Type": content_type},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content
