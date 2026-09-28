"""CLI `anunciar-servico`: anúncio de SERVIÇO (classificado) no Mercado Livre.

    anunciar-servico /pasta/de/fotos                   # gera o template em branco
    anunciar-servico --dry-run --replay template.json  # valida, sem criar nada
    anunciar-servico --replay template.json            # cria o anúncio ATIVO

O dry-run nunca cria nada e nunca notifica o Telegram. Com tokens válidos ele
consulta a categoria, a cidade, os tipos de publicação disponíveis e roda
POST /items/validate (validação do ML, sem criar item). Sem tokens, mostra o
payload offline com um aviso.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .listing import upload_pictures
from .ml_api import MLClient, MLError
from .notify import notify_error, notify_success
from .runlog import load_log
from .servico import (
    ServiceError,
    available_listing_types,
    build_service_payload,
    check_service_category,
    city_from_profile,
    resolve_city,
    save_service_log,
    save_service_template,
    validate_service,
)
from .tokens import AuthError


def _fmt_price(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _public_checks(ml: MLClient, data: dict) -> dict:
    """Categoria e cidade: endpoints públicos, funcionam sem token."""
    out = {"category_path": check_service_category(ml, data["category_id"])}
    if data.get("state") and data.get("city"):
        out["city"] = resolve_city(ml, data["state"], data["city"])
        out["city_source"] = "template"
    return out


def _auth_checks(ml: MLClient, data: dict, out: dict) -> None:
    """Consultas que exigem token (leitura apenas)."""
    if "city" not in out:
        state, city = city_from_profile(ml)
        if not (state and city):
            raise ServiceError("Sem cidade/estado no template nem no endereço da conta ML")
        out["city"] = resolve_city(ml, state, city)
        out["city_source"] = "endereço da conta ML"
    out["listing_types"] = available_listing_types(ml, data["category_id"])


def _check_listing_type(data: dict, available: list[dict]) -> str | None:
    wanted = data.get("listing_type_id")
    ids = [t.get("id") for t in available]
    if not wanted:
        return "listing_type_id não escolhido. Disponíveis: " + (
            ", ".join(f"{t.get('id')} ({t.get('name')})" for t in available) or "nenhum"
        )
    if wanted not in ids:
        return f"listing_type_id '{wanted}' não está disponível nesta categoria: {ids}"
    return None


def _validate_warnings(exc: MLError, data: dict) -> list[str]:
    if exc.status == 402 or exc.body.get("status") == "payment_required":
        lt = data.get("listing_type_id")
        return [
            (
                f"/items/validate: payload OK, mas '{lt}' é pago — o anúncio nasce "
                "payment_required e só fica ativo depois de pago no site do ML"
            )
        ]
    causes = [
        c.get("message", str(c)) if isinstance(c, dict) else str(c) for c in exc.causes()
    ] or [str(exc)]
    return [f"/items/validate: {c}" for c in causes]


def _print_report(payload: dict, description: str, info: dict, warnings: list[str]) -> None:
    print("\n--- DESCRIÇÃO ---\n")
    print(description)
    print("\n--- PAYLOAD (POST /items) ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n" + "=" * 62)
    print("RESUMO DO ANÚNCIO DE SERVIÇO")
    print("=" * 62)
    for label, value in [
        ("Título", payload.get("title") or payload.get("family_name")),
        ("Preço", _fmt_price(payload["price"])),
        ("Categoria", info.get("category")),
        ("Cidade", info.get("city")),
        ("Tipo de publicação", payload.get("listing_type_id") or "(não escolhido)"),
        ("Modo", "classificado — sem condição, sem frete"),
        ("Item", info.get("item_id")),
        ("Link", info.get("permalink")),
        ("Status", info.get("status")),
    ]:
        if value:
            print(f"{label:>20}: {value}")
    for w in warnings:
        print(f"{'Aviso':>20}: {w}")
    if info.get("log"):
        print(f"{'Log':>20}: {info['log']}")
    print("=" * 62)


def run(args) -> int:
    if args.folder and not args.replay:
        path = save_service_template(Path(args.folder).expanduser())
        print(f"Template de serviço salvo em {path}")
        print("Preencha o bloco 'service' e rode:")
        print(f"  anunciar-servico --dry-run --replay {path}")
        return 0
    if not args.replay:
        raise SystemExit("informe a pasta de fotos (gera o template) ou --replay")

    log = load_log(args.replay)
    if log.get("kind") != "servico" or "service" not in log:
        raise SystemExit(
            "Este arquivo não é um template de serviço (use o `anunciar` para produtos)."
        )
    data = log["service"]
    images = [Path(p) for p in log.get("images", [])]
    errors = validate_service(data, images)
    if errors:
        raise SystemExit("Template inválido:\n  - " + "\n  - ".join(errors))

    description = data["description"].strip()
    warnings: list[str] = []
    info: dict = {}
    ml = MLClient("MLB")
    checks: dict = {}
    authed = False
    try:
        checks = _public_checks(ml, data)
        _auth_checks(ml, data, checks)
        authed = True
    except AuthError as exc:
        if not args.dry_run:
            raise
        warnings.append(
            f"Sem autenticação no ML ({exc}); tipo de publicação e /items/validate não conferidos."
        )
    except (MLError, ServiceError) as exc:
        if not args.dry_run:
            raise
        warnings.append(f"Checagem no ML falhou: {exc}")

    info["category"] = (
        f"{data['category_id']} — {checks['category_path']}"
        if "category_path" in checks
        else f"{data['category_id']} (não conferida)"
    )
    if "city" in checks:
        c = checks["city"]
        info["city"] = f"{c['name']}/{c['state']} ({c['id']}, via {checks['city_source']})"
    else:
        warnings.append("Cidade não resolvida (preencha city/state no template ou autentique).")
    if authed:
        lt_problem = _check_listing_type(data, checks["listing_types"])
        if lt_problem:
            if not args.dry_run:
                raise ServiceError(lt_problem)
            warnings.append(lt_problem)

    payload = build_service_payload(
        data,
        city_id=checks["city"]["id"] if "city" in checks else None,
        pictures=[],
    )
    entry = {
        "kind": "servico",
        "folder": log.get("folder"),
        "images": [str(p) for p in images],
        "service": data,
        "description": description,
        "payload": payload,
        "warnings": warnings,
    }

    if args.dry_run:
        if authed and not data.get("listing_type_id"):
            warnings.append("/items/validate pulado: escolha o listing_type_id primeiro")
        elif authed:
            try:
                ml.post("/items/validate", {**payload, "pictures": []})
                warnings.append("POST /items/validate: OK (fotos não enviadas no dry-run)")
            except MLError as exc:
                warnings += _validate_warnings(exc, data)
        payload["pictures"] = [{"source": f"file://{p}"} for p in images]
        info["status"] = "dry-run (nada foi criado no Mercado Livre)"
        info["log"] = str(save_service_log(entry, "dry-run"))
        _print_report(payload, description, info, warnings)
        return 0

    missing = [str(p) for p in images if not p.exists()]
    if missing:
        raise SystemExit("Fotos não encontradas: " + ", ".join(missing))
    print("Enviando fotos (ordem alfabética; a 1ª é a capa)...")
    payload["pictures"] = upload_pictures(ml, images)
    try:
        item = ml.create_item(payload)
    except MLError as exc:
        entry["error"] = {"status": exc.status, "body": exc.body}
        print(f"Log do erro: {save_service_log(entry, 'error')}", file=sys.stderr)
        raise
    try:
        ml.set_description(item["id"], description)
    except MLError as exc:
        warnings.append(f"Falha ao definir a descrição (corrija com set_description): {exc}")
    info.update(item_id=item["id"], permalink=item.get("permalink"), status=item.get("status"))
    entry["item"] = {k: info[k] for k in ("item_id", "permalink", "status")}
    info["log"] = str(save_service_log(entry, "publish"))
    notify_warning = notify_success(item.get("permalink", "-"))
    if notify_warning:
        warnings.append(notify_warning)
    _print_report(payload, description, info, warnings)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anunciar-servico",
        description="Cria um anúncio de SERVIÇO (classificado) no Mercado Livre.",
    )
    parser.add_argument("folder", nargs="?", help="pasta de fotos -> gera o template")
    parser.add_argument("--replay", metavar="TEMPLATE", help="template de serviço preenchido")
    parser.add_argument("--dry-run", action="store_true", help="valida sem criar nada")
    args = parser.parse_args(argv)

    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    try:
        return run(args)
    except (MLError, AuthError, ServiceError) as exc:
        text = exc.pretty() if isinstance(exc, MLError) else str(exc)
        if not args.dry_run:
            notify_error(text)
        print(f"\nERRO: {text}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
