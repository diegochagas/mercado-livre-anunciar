"""Bot Telegram: recebe fotos (produto já fotografado sobre o quadro branco
físico) e dispara a criação + ativação do anúncio via Claude Code headless.

Fluxo no Telegram (só responde ao TELEGRAM_CHAT_ID do .env):
    /startanuncio   -> inicia uma sessão nova (pasta limpa)
    <enviar fotos>  -> cada foto é baixada e salva como o Telegram manda
                       (sem nenhum processamento), em ordem de chegada na
                       pasta da sessão
    <texto livre>   -> qualquer mensagem de texto (que não seja um comando)
                       enviada durante a sessão vira um "detalhe" do produto
                       (ex.: "é novo, nunca usado", "edição de 2019", "quero
                       vender por R$80") repassado à identificação
    /finishanuncio  -> roda a identificação (Claude Code headless com a
                       skill mercado-livre-anunciar), cria o anúncio já ativo,
                       e manda o link final no Telegram (só essa mensagem —
                       sem etapas intermediárias — ou um alerta se falhar)

Rodar (laptop ligado, para teste manual — não pelo Claude Code):
    ./.venv/bin/python -m anunciar.bot

Prefira `./.venv/bin/python start_bot.py` (na raiz do repo): confere o
token do Mercado Livre antes de subir o bot e roda `--auth` na hora se
precisar, em vez de descobrir isso só quando um /finishanuncio falhar.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from .config import CONFIG_DIR

API_BASE = "https://api.telegram.org"
SESSIONS_DIR = CONFIG_DIR / "bot-sessions"
PROJECT_DIR = Path(__file__).resolve().parents[1]
HEADLESS_TIMEOUT_S = 15 * 60


def _log(step: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {step}", flush=True)


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "permalink": {"type": "string"},
        "title": {"type": "string"},
        "price_brl": {"type": "number"},
        "status": {"type": "string"},
    },
    "required": ["item_id", "permalink", "title", "status"],
}


def _load_env() -> tuple[str, str]:
    load_dotenv()
    load_dotenv(PROJECT_DIR / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID precisam estar no .env.")
    return token, chat_id


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as exc:
        print(f"Falha ao enviar mensagem no Telegram: {exc}", file=sys.stderr)


def _download_file(token: str, file_id: str) -> bytes:
    info = requests.get(
        f"{API_BASE}/bot{token}/getFile", params={"file_id": file_id}, timeout=15
    )
    info.raise_for_status()
    file_path = info.json()["result"]["file_path"]
    data = requests.get(f"{API_BASE}/file/bot{token}/{file_path}", timeout=60)
    data.raise_for_status()
    return data.content


class Session:
    def __init__(self):
        self.active = False
        self.folder: Path | None = None
        self.count = 0
        self.details: list[str] = []

    def start(self) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.folder = SESSIONS_DIR / stamp
        self.folder.mkdir(parents=True, exist_ok=True)
        self.active = True
        self.count = 0
        self.details = []
        return self.folder

    def stop(self) -> None:
        self.active = False


def _process_photo(token: str, session: Session, file_id: str) -> str:
    _log("Foto recebida, baixando do Telegram...")
    raw = _download_file(token, file_id)
    session.count += 1
    name = f"{session.count:03d}.jpg"
    _log(f"Salvando {name} em {session.folder}...")
    (session.folder / name).write_bytes(raw)
    return name


def _run_headless_claude(folder: Path, details: list[str]) -> dict:
    """Identificação + `anunciar --replay` (cria já ativo) via Claude Code
    headless, usando a skill mercado-livre-anunciar."""
    details_block = ""
    if details:
        bullets = "\n".join(f"- {d}" for d in details)
        details_block = (
            "\n\nDetalhes que o Diego informou pelo Telegram (use como ponto "
            "de partida, mas confirme/complete com pesquisa na web):\n"
            f"{bullets}"
        )
    prompt = (
        "Use a skill mercado-livre-anunciar para identificar o produto nas "
        f"fotos em {folder} (produto sobre o quadro branco) e criar o "
        "anúncio no Mercado Livre com `anunciar --replay` (já cria ativo). "
        "Pesquise produto e preço na web como a skill descreve. Ao "
        "final responda apenas com item_id, permalink, title, price_brl e "
        "status do anúncio criado." + details_block
    )
    _log("Identificando produto e publicando (claude -p headless, pode levar minutos)...")
    # ANUNCIAR_SKIP_NOTIFY: o `anunciar --replay` chamado aqui dentro (pelo
    # Bash do claude headless) notificaria o Telegram sozinho (só a URL),
    # duplicando a mensagem que _finish já manda com o resultado completo.
    env = {**os.environ, "ANUNCIAR_SKIP_NOTIFY": "1"}
    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--permission-mode", "bypassPermissions",
            "--tools", "Bash,Read,WebSearch,WebFetch,Edit,Write,Skill",
            "--add-dir", str(folder),
            "--json-schema", json.dumps(RESULT_SCHEMA),
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=HEADLESS_TIMEOUT_S,
        env=env,
    )
    _log("claude -p terminou, lendo resultado...")
    print("--- claude -p stdout ---", file=sys.stderr)
    print(result.stdout, file=sys.stderr)
    print("--- claude -p stderr ---", file=sys.stderr)
    print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p saiu com código {result.returncode} — veja o terminal "
            "do bot para stdout/stderr completos."
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            "Saída do claude -p não é o JSON esperado — veja o terminal do "
            "bot para a saída completa."
        )


def _finish(token: str, chat_id: str, session: Session) -> None:
    if session.count == 0:
        _log("Finalizar pedido sem fotos, abortando.")
        _send(token, chat_id, "Nenhuma foto recebida nessa sessão.")
        session.stop()
        return
    _log(f"Finalizando sessão com {session.count} foto(s)...")
    try:
        info = _run_headless_claude(session.folder, session.details)
        if not info.get("permalink", "").startswith("http"):
            _log(f"Anúncio não foi criado: {info.get('status')!r}")
            _send(
                token, chat_id,
                f"⚠️ Anúncio não foi criado: {info.get('status') or '(sem detalhes)'}",
            )
            return
        _log(f"Anúncio publicado: {info['permalink']}")
        _send(
            token, chat_id,
            f"✅ Anúncio ativo: {info.get('title', '')}\n{info['permalink']}",
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        _log(f"Falha ao criar o anúncio: {exc}")
        _send(token, chat_id, f"❌ Falha ao criar o anúncio: {exc}")
    finally:
        session.stop()


def main() -> int:
    token, chat_id = _load_env()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session = Session()
    offset = None
    print("Bot rodando. Ctrl+C para parar.")
    _send(token, chat_id, "🤖 Bot de anúncios online. /startanuncio para começar.")

    try:
        while True:
            try:
                resp = requests.get(
                    f"{API_BASE}/bot{token}/getUpdates",
                    params={"timeout": 30, "offset": offset},
                    timeout=40,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                print(f"Erro no polling: {exc}", file=sys.stderr)
                time.sleep(5)
                continue

            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg or str(msg["chat"]["id"]) != str(chat_id):
                    continue

                text = msg.get("text", "")
                if text == "/startanuncio":
                    _log("Recebido /startanuncio, iniciando sessão nova...")
                    session.start()
                    _send(
                        token, chat_id,
                        "📸 Sessão iniciada. Manda as fotos e, se quiser, detalhes do "
                        "produto em texto (ex.: \"é novo, nunca usado\", \"quero vender "
                        "por R$80\"). Quando terminar, /finishanuncio.",
                    )
                elif text == "/finishanuncio":
                    _log("Recebido /finishanuncio.")
                    if not session.active:
                        _send(token, chat_id, "Nenhuma sessão ativa. Use /startanuncio primeiro.")
                    else:
                        _finish(token, chat_id, session)
                elif "photo" in msg:
                    if not session.active:
                        _send(token, chat_id, "Use /startanuncio antes de mandar fotos.")
                        continue
                    file_id = msg["photo"][-1]["file_id"]
                    try:
                        name = _process_photo(token, session, file_id)
                        _log(f"Foto {session.count} pronta ({name}).")
                    except Exception as exc:
                        _log(f"Falha ao processar foto: {exc}")
                        _send(token, chat_id, f"❌ Falha ao processar foto: {exc}")
                elif text and not text.startswith("/"):
                    if not session.active:
                        _send(token, chat_id, "Use /startanuncio antes de mandar detalhes.")
                        continue
                    _log(f"Detalhe recebido: {text}")
                    session.details.append(text)
                    _send(token, chat_id, f"📝 Detalhe adicionado: {text}")
                elif text.startswith("/"):
                    _send(token, chat_id, f"Comando desconhecido: {text}")
    except KeyboardInterrupt:
        print("\nEncerrado.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
