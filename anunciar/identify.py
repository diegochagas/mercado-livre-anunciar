"""Identificação do produto + pesquisa de preço via API da Anthropic.

Envia todas as fotos com a ferramenta de web search habilitada e exige uma
resposta JSON estrita. Parsing defensivo: remove cercas de markdown e refaz a
pergunta uma vez se o JSON vier inválido.
"""

import json
import os
from pathlib import Path

import anthropic

from .config import Config
from .images import image_blocks, list_images

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 15}
MAX_CONTINUATIONS = 5

SCHEMA = """{
  "title_ml": "string, máx 60 caracteres, rico em palavras-chave: tipo do item + nome + ano + origem",
  "product_type": "livro | hq | mangá | revista | pamphlet | catálogo | ...",
  "full_name": "nome completo do produto SEM repetir o tipo (ex.: 'Fūma no Kojirō — peça teatral 2008', não 'Pamphlet da peça...')",
  "original_name": "nome original se estrangeiro, senão null",
  "brand": "editora/marca; 'Genérica' se não houver",
  "model": "nome curto do produto + ano, ex. 'Fuma no Kojiro Butai-ban 2008'",
  "author_or_cast": "string ou null",
  "publisher": "string ou null",
  "isbn_ean": "ISBN/EAN se encontrado, senão null",
  "pages": null_ou_inteiro,
  "dimensions": "string ou null",
  "language": "idioma do item, em português (ex.: 'Japonês', 'Português')",
  "year": inteiro_ou_null,
  "country_of_origin": "país de origem em português (ex.: 'Japão'), ou null",
  "context": "contexto histórico pesquisado que agrega valor (raridade, obras relacionadas, tiragem, onde era vendido, evento/local/datas)",
  "condition_notes": "avaliação honesta do estado de conservação com base nas fotos",
  "is_imported_rare": true_ou_false,
  "price_research": [
    {"source": "string", "price_brl": 0.0, "is_brazil": true_ou_false, "notes": "string"}
  ],
  "suggested_price_brl": 189.90
}"""


def _build_prompt(cfg: Config) -> str:
    pricing = cfg.pricing
    return f"""Você é um especialista em catalogação e precificação de publicações e itens colecionáveis para venda no Mercado Livre Brasil.

As imagens acima são fotos de UM único produto (livro, HQ, mangá, revista, pamphlet, catálogo ou similar). Sua tarefa:

1. IDENTIFIQUE a publicação exata (edição, ano, país de origem) a partir das fotos — leia capa, lombada, colofão, códigos de barras/ISBN visíveis.

2. PESQUISE na internet (use a ferramenta de busca) para confirmar a identificação e levantar dados reais. Fontes preferenciais por tipo de produto:
   - HQs/quadrinhos brasileiros: Guia dos Quadrinhos (guiadosquadrinhos.com) e Amazon.
   - Livros: Amazon — busque também ISBN/EAN, editora, páginas, dimensões, ano.
   - Itens japoneses (pamphlets, artbooks, mangás em japonês, colecionáveis): Mercari Japan (jp.mercari.com), Suruga-ya (suruga-ya.jp), Yahoo Auctions (auctions.yahoo.co.jp); Wikipedia e CoRich (stage.corich.jp) para dados de peças de teatro/eventos.

3. PESQUISE O PREÇO do MESMO produto à venda em: Mercado Livre, Estante Virtual, Amazon, eBay, Mercari JP, Suruga-ya. Regras de precificação:
   - Se houver anúncios no Brasil: precifique dentro da faixa encontrada, LIGEIRAMENTE ABAIXO do mais barato em condição similar (estratégia: {pricing['undercut_strategy']}).
   - Se só encontrar no exterior (item raro importado): converta para BRL na cotação atual e multiplique por ~{pricing['import_multiplier_min']}–{pricing['import_multiplier_max']}x (frete de importação + raridade).
   - O preço final deve terminar em ,90 (ex.: 189.90).
   - Em price_research, liste cada achado com o preço JÁ CONVERTIDO para BRL e marque is_brazil corretamente.

4. AVALIE o estado de conservação honestamente pelas fotos (capa, lombada, páginas, amassados, amarelamento).

Regras de resposta:
- Todos os textos em português do Brasil ({cfg.ai['language']}). Traduza informações em língua estrangeira.
- title_ml: máx 60 caracteres, sem promessas (frete, desconto), sem estado (novo/usado), seguindo "tipo + nome + ano + origem". Ex.: "Pamphlet Teatral Fuma No Kojiro 2008 Japão Saint Seiya".
- NUNCA invente dados: campo não encontrado = null.
- context deve conter apenas fatos pesquisados e verificáveis.

RESPONDA APENAS com um objeto JSON válido, sem nenhum texto antes ou depois, sem cercas de markdown, exatamente neste formato:

{SCHEMA}"""


class IdentificationError(Exception):
    pass


def _extract_text(message) -> str:
    return "\n".join(b.text for b in message.content if b.type == "text")


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip().rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise json.JSONDecodeError("sem objeto JSON", cleaned, 0)
    return json.loads(cleaned[start : end + 1])


def _run_turn(client, cfg: Config, messages: list) -> "anthropic.types.Message":
    """Roda um turno, retomando automaticamente em pause_turn (web search)."""
    for _ in range(MAX_CONTINUATIONS):
        with client.messages.stream(
            model=cfg.ai["model"],
            max_tokens=16000,
            thinking={"type": "adaptive"},
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": message.content}]
            continue
        if message.stop_reason == "refusal":
            raise IdentificationError("A API recusou a solicitação (refusal).")
        return message
    raise IdentificationError("Turno pausado repetidamente; tente novamente.")


def identify(folder: Path, cfg: Config) -> tuple[dict, list[Path]]:
    """Identifica o produto da pasta. Retorna (dados, lista ordenada de fotos)."""
    images = list_images(folder)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY não definida no .env.")
    print(f"Fotos encontradas ({len(images)}): "
          + ", ".join(p.name for p in images))
    print("Identificando o produto e pesquisando preços (pode levar alguns minutos)...")

    content = image_blocks(images) + [{"type": "text", "text": _build_prompt(cfg)}]
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": content}]
    message = _run_turn(client, cfg, messages)
    text = _extract_text(message)

    try:
        data = _parse_json(text)
    except json.JSONDecodeError:
        print("Resposta não era JSON válido; pedindo correção...")
        retry_messages = [
            messages[0],
            {"role": "assistant", "content": text or "(vazio)"},
            {
                "role": "user",
                "content": (
                    "Sua resposta anterior não era um JSON válido. Reenvie AGORA "
                    "apenas o objeto JSON completo, sem markdown e sem comentários."
                ),
            },
        ]
        message = _run_turn(client, cfg, retry_messages)
        try:
            data = _parse_json(_extract_text(message))
        except json.JSONDecodeError as exc:
            raise IdentificationError(
                f"JSON inválido mesmo após retry: {exc}"
            ) from exc

    _validate(data)
    return data, images


def _validate(data: dict) -> None:
    required = ["title_ml", "product_type", "full_name", "suggested_price_brl"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise IdentificationError(
            f"Resposta da identificação sem campos obrigatórios: {missing}"
        )
