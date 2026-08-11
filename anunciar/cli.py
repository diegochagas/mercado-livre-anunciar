"""CLI do anunciar.

Uso típico:
    anunciar /caminho/da/pasta          # identifica, precifica e cria pausado
    anunciar --dry-run /caminho/pasta   # tudo, menos chamadas de escrita no ML
    anunciar --auth                     # fluxo OAuth único
    anunciar --activate MLB123456789    # ativa um anúncio revisado
    anunciar --replay run-...json       # repete uma execução sem nova identificação
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import tokens as tk
from .config import load_config
from .description import build_description
from .identify import IdentificationError, identify
from .listing import (
    build_attributes,
    build_payload,
    build_sale_terms,
    build_shipping,
    is_user_products_seller,
    resolve_category,
    resolve_listing_type,
    truncate_title,
    upload_pictures,
)
from .ml_api import MLClient, MLError
from .pricing import apply_rules
from .runlog import load_log, save_log
from .tokens import AuthError, run_auth_flow


def _load_env() -> None:
    load_dotenv()  # .env do diretório atual, se houver
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _fmt_price(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _print_report(info: dict) -> None:
    print("\n" + "=" * 62)
    print("RESUMO DO ANÚNCIO")
    print("=" * 62)
    for label, key in [
        ("Título", "title"),
        ("Categoria", "category"),
        ("Preço", "price"),
        ("Frete", "shipping"),
        ("Tipo de publicação", "listing_type"),
        ("Condição/quantidade", "condition"),
        ("Item", "item_id"),
        ("Link", "permalink"),
        ("Status", "status"),
    ]:
        if info.get(key):
            print(f"{label:>20}: {info[key]}")
    for warning in info.get("warnings", []):
        print(f"{'Aviso':>20}: {warning}")
    if info.get("log"):
        print(f"{'Log':>20}: {info['log']}")
    print("=" * 62)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="anunciar",
        description="Cria um anúncio no Mercado Livre a partir de uma pasta de fotos.",
    )
    parser.add_argument("folder", nargs="?", help="pasta com as fotos do produto")
    parser.add_argument("--auth", action="store_true",
                        help="executa o fluxo OAuth do Mercado Livre (uma vez)")
    parser.add_argument("--activate", metavar="ITEM_ID",
                        help="ativa um anúncio criado pausado")
    parser.add_argument("--dry-run", action="store_true",
                        help="identifica e monta tudo sem chamadas de escrita no ML")
    parser.add_argument("--publish", action="store_true",
                        help="deixa o anúncio ativo em vez de pausado para revisão")
    parser.add_argument("--replay", metavar="LOGFILE",
                        help="reusa a identificação de um log anterior")
    parser.add_argument("--config", metavar="PATH",
                        help="config TOML alternativa (padrão ~/.config/anunciar/config.toml)")
    args = parser.parse_args()

    _load_env()
    try:
        return _run(args, parser)
    except (MLError,) as exc:
        print("\nERRO da API do Mercado Livre:", file=sys.stderr)
        print(exc.pretty(), file=sys.stderr)
        causes = exc.causes()
        if causes:
            print("\nCausas (cause):", file=sys.stderr)
            for cause in causes:
                print(f"  - {cause}", file=sys.stderr)
        return 1
    except (AuthError, IdentificationError) as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        return 1


def _run(args, parser) -> int:
    cfg = load_config(args.config)

    if args.auth:
        run_auth_flow()
        return 0

    if args.activate:
        ml = MLClient(cfg.listing["site_id"])
        result = ml.update_item(args.activate, {"status": "active"})
        print(f"Anúncio {args.activate} ativado (status: {result.get('status')}).")
        print(f"Link: {result.get('permalink', '-')}")
        return 0

    # ---------------------------------------------------------- identificação
    if args.replay:
        log = load_log(args.replay)
        data = log["identification"]
        images = [Path(p) for p in log.get("images", [])]
        folder = log.get("folder", "")
        print(f"Replay de {args.replay} (sem nova chamada à Anthropic).")
        if not args.dry_run:
            missing = [str(p) for p in images if not p.exists()]
            if missing:
                raise SystemExit(
                    "Fotos do log não encontradas (necessárias para upload): "
                    + ", ".join(missing)
                )
    elif args.folder:
        folder = str(Path(args.folder).expanduser())
        data, images = identify(Path(folder), cfg)
    else:
        parser.error("informe a pasta de fotos (ou use --auth / --activate / --replay)")
        return 2

    # ------------------------------------------------------- preço e descrição
    price, warnings = apply_rules(data, cfg)
    description = build_description(data, cfg)
    title = truncate_title(data["title_ml"])
    shipping = build_shipping(price, cfg)

    # ------------------------------------------------------- consultas ao ML
    ml = MLClient(cfg.listing["site_id"])
    have_tokens = tk.load_tokens() is not None
    category_id = None
    category_path = "(não resolvida — sem autenticação no ML)"
    listing_type_id = cfg.listing["listing_type"]
    listing_type_name = listing_type_id
    attributes: list[dict] = []
    sale_terms: list[dict] = []
    up_seller = False

    if not have_tokens and not args.dry_run:
        raise SystemExit("Sem tokens do Mercado Livre. Rode `anunciar --auth` primeiro.")

    if have_tokens:
        try:
            category_id, category_path = resolve_category(ml, data, cfg)
            listing_type_id, listing_type_name = resolve_listing_type(ml, cfg)
            attributes, attr_notes = build_attributes(ml, category_id, data, cfg)
            terms, term_notes = build_sale_terms(ml, category_id, cfg)
            sale_terms = terms
            warnings += attr_notes + term_notes
            up_seller = is_user_products_seller(ml)
            if up_seller:
                warnings.append(
                    "Conta migrada para User Products: enviando family_name "
                    "em vez de title."
                )
        except MLError:
            if not args.dry_run:
                raise
            warnings.append(
                "Consultas ao ML falharam; payload do dry-run está incompleto."
            )

    payload = build_payload(
        title=title,
        category_id=category_id or "(pendente)",
        price=price,
        listing_type_id=listing_type_id,
        attributes=attributes,
        sale_terms=sale_terms,
        shipping=shipping,
        cfg=cfg,
        up_seller=up_seller,
        pictures=None,
    )

    frete = (
        f"grátis por conta do vendedor (preço > "
        f"{_fmt_price(float(cfg.shipping['free_shipping_threshold']))})"
        if shipping["free_shipping"]
        else "por conta do comprador"
    )
    log_entry = {
        "folder": folder,
        "images": [str(p) for p in images],
        "identification": data,
        "price": price,
        "warnings": warnings,
        "description": description,
        "category_id": category_id,
        "category_path": category_path,
        "payload": payload,
    }

    # ------------------------------------------------------------- dry-run
    if args.dry_run:
        payload["pictures"] = [{"source": f"file://{p}"} for p in images]
        log_path = save_log({**log_entry, "mode": "dry-run"})
        print("\n--- IDENTIFICAÇÃO ---")
        import json as _json

        print(_json.dumps(data, indent=2, ensure_ascii=False))
        print("\n--- DESCRIÇÃO ---\n")
        print(description)
        print("\n--- PAYLOAD (POST /items) ---")
        print(_json.dumps(payload, indent=2, ensure_ascii=False))
        _print_report(
            {
                "title": title,
                "category": f"{category_id or '-'} — {category_path}",
                "price": _fmt_price(price),
                "shipping": frete,
                "listing_type": f"{listing_type_id} ({listing_type_name})",
                "condition": f"{cfg.listing['condition']} — "
                             f"{cfg.listing['available_quantity']} un.",
                "status": "dry-run (nada foi enviado ao Mercado Livre)",
                "warnings": warnings,
                "log": str(log_path),
            }
        )
        print(f"\nPara publicar esta execução sem nova identificação:\n"
              f"  anunciar --replay {log_path}")
        return 0

    # ------------------------------------------------------------ publicação
    print("\nEnviando fotos ao Mercado Livre (ordem = ordem alfabética dos arquivos)...")
    payload["pictures"] = upload_pictures(ml, images)

    try:
        item = ml.create_item(payload)
    except MLError as exc:
        log_entry["error"] = {"status": exc.status, "body": exc.body}
        log_path = save_log({**log_entry, "mode": "error"})
        print(f"\nFalha na criação do item. Log salvo em {log_path}", file=sys.stderr)
        print(f"Replay depois de corrigir: anunciar --replay {log_path}",
              file=sys.stderr)
        raise

    item_id = item["id"]
    print(f"Item criado: {item_id}")

    try:
        ml.set_description(item_id, description)
        print("Descrição publicada.")
    except MLError as exc:
        warnings.append(f"Falha ao definir a descrição: {exc.pretty()}")

    status = item.get("status", "active")
    if args.publish:
        pass  # permanece ativo
    elif cfg.listing["default_status"] == "paused" and status == "active":
        ml.update_item(item_id, {"status": "paused"})
        status = "paused"

    log_entry["item"] = {
        "id": item_id,
        "permalink": item.get("permalink"),
        "status": status,
    }
    log_path = save_log({**log_entry, "mode": "publish"})

    _print_report(
        {
            "title": payload.get("title") or payload.get("family_name"),
            "category": f"{category_id} — {category_path}",
            "price": _fmt_price(price),
            "shipping": frete,
            "listing_type": f"{listing_type_id} ({listing_type_name})",
            "condition": f"{cfg.listing['condition']} — "
                         f"{cfg.listing['available_quantity']} un.",
            "item_id": item_id,
            "permalink": item.get("permalink", "-"),
            "status": status
            + ("" if args.publish else
               f"  (revise e rode: anunciar --activate {item_id})"),
            "warnings": warnings,
            "log": str(log_path),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
