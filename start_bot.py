#!/usr/bin/env python3
"""Garante um token válido do Mercado Livre antes de subir o bot do Telegram.

Sem isso, um anúncio só falha (sem token/refresh salvo) depois que o Diego já
mandou as fotos pelo Telegram e pediu /finishanuncio — nesse ponto o fluxo de
auth (`anunciar --auth`) é interativo e não dá pra rodar de dentro do bot.
Este script roda a autenticação primeiro, ainda no terminal, e só sobe o bot
depois de confirmar que há um token (ou refresh token) utilizável.

Rodar (laptop ligado, terminal interativo — não pelo Claude Code):
    cd ~/Projects/mercado-livre-anunciar
    ./.venv/bin/python start_bot.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from anunciar import bot
from anunciar import tokens as tk

PROJECT_DIR = Path(__file__).resolve().parent


def _ensure_auth() -> None:
    load_dotenv()
    load_dotenv(PROJECT_DIR / ".env")
    try:
        tk.get_access_token()
        print("Autenticação com o Mercado Livre OK.")
    except tk.AuthError:
        print("Sem token válido do Mercado Livre salvo — iniciando autenticação...\n")
        tk.run_auth_flow()


def main() -> int:
    _ensure_auth()
    return bot.main()


if __name__ == "__main__":
    sys.exit(main())
