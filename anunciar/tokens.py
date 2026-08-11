"""OAuth 2.0 do Mercado Livre: fluxo authorization-code + refresh automático.

Tokens ficam em ~/.config/anunciar/tokens.json (chmod 600). Access tokens do ML
duram ~6h; refresh tokens são de uso único, então o novo par é sempre persistido.
"""

import json
import os
import time
import urllib.parse

import requests

from .config import CONFIG_DIR, TOKENS_PATH

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


class AuthError(Exception):
    pass


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AuthError(
            f"Variável {name} não definida. Preencha o arquivo .env "
            "(veja .env.example) antes de continuar."
        )
    return value


def load_tokens() -> dict | None:
    if not TOKENS_PATH.exists():
        return None
    try:
        return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_tokens(payload: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tokens = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "user_id": payload.get("user_id"),
        "expires_at": time.time() + int(payload.get("expires_in", 21600)),
    }
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    os.chmod(TOKENS_PATH, 0o600)


def _exchange(data: dict) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data=data,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise AuthError(f"Falha ao obter token ({resp.status_code}): {resp.text}")
    return resp.json()


def run_auth_flow() -> dict:
    """Fluxo interativo: imprime a URL de autorização e troca o code por tokens."""
    client_id = _env("ML_CLIENT_ID")
    client_secret = _env("ML_CLIENT_SECRET")
    redirect_uri = _env("ML_REDIRECT_URI")

    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
    )
    print("1. Abra esta URL no navegador, logado na conta que vai vender:\n")
    print(f"   {AUTH_URL}?{params}\n")
    print("2. Autorize o app. Você será redirecionado para a Redirect URI")
    print("   com ?code=TG-... na URL.\n")
    raw = input("3. Cole aqui a URL completa do redirect (ou só o code): ").strip()

    if raw.startswith("TG-"):
        code = raw
    else:
        query = urllib.parse.urlparse(raw).query
        code = urllib.parse.parse_qs(query).get("code", [""])[0]
    if not code:
        raise AuthError("Não foi possível extrair o code da entrada fornecida.")

    payload = _exchange(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )
    save_tokens(payload)
    print(f"\nAutenticado! user_id={payload.get('user_id')}")
    print(f"Tokens salvos em {TOKENS_PATH}")
    return payload


def refresh_tokens() -> dict:
    tokens = load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        raise AuthError("Sem refresh token salvo. Rode `anunciar --auth` primeiro.")
    payload = _exchange(
        {
            "grant_type": "refresh_token",
            "client_id": _env("ML_CLIENT_ID"),
            "client_secret": _env("ML_CLIENT_SECRET"),
            "refresh_token": tokens["refresh_token"],
        }
    )
    # user_id não vem no refresh; preserva o que já tínhamos
    payload.setdefault("user_id", tokens.get("user_id"))
    save_tokens(payload)
    return load_tokens()


def get_access_token() -> str:
    """Retorna um access token válido, renovando de forma transparente."""
    tokens = load_tokens()
    if not tokens:
        raise AuthError("Nenhum token salvo. Rode `anunciar --auth` primeiro.")
    if time.time() > tokens.get("expires_at", 0) - 120:
        tokens = refresh_tokens()
    return tokens["access_token"]
