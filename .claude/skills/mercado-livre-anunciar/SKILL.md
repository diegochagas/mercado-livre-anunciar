---
name: mercado-livre-anunciar
description: >-
  Cria um anúncio no Mercado Livre (mercadolivre.com.br) pela API oficial a
  partir de uma pasta de fotos, usando o CLI `anunciar` de
  ~/Projects/mercado-livre-anunciar, e envia a URL do anúncio pronto no
  Telegram. Use SEMPRE que o Diego pedir para "criar um anúncio", "anunciar",
  "vender no Mercado Livre / ML / Meli", ou apontar uma pasta de fotos de um
  produto para venda (livro, HQ, mangá, pamphlet, colecionável etc.), mesmo
  sem citar a palavra "anúncio". Esta skill substitui qualquer fluxo por
  navegador (skill mercadolivre-anuncio / Claude in Chrome) — anúncio no ML é
  sempre via API com esta skill. Aceita detalhes opcionais do produto
  informados pelo Diego (edição, ano, defeitos, preço desejado...).
---

# Criar anúncio no Mercado Livre via API (CLI `anunciar`)

Cria o anúncio com o CLI `anunciar` deste repositório — **nunca por automação
de navegador** (Claude in Chrome, Claude Browser, Playwright). O fluxo por
navegador é frágil e lento; o CLI resolve categoria, atributos, sale_terms,
frete e tipo de anúncio direto na API oficial.

O CLI **não chama nenhuma API de IA para identificar o produto** — essa parte
é sempre feita por você (Claude), olhando as fotos e pesquisando o produto e o
preço na web, exatamente como faria para responder ao Diego em qualquer outra
tarefa. Não existe `ANTHROPIC_API_KEY` a configurar para isso.

## Entradas

1. **Pasta de fotos** (obrigatória) — a ordem alfabética dos arquivos define a
   ordem das fotos; a primeira vira a capa. Se o Diego não indicou a pasta,
   pergunte antes de rodar.
2. **Detalhes do produto** (opcional) — qualquer informação extra que o Diego
   der na conversa (edição, ano, estado, defeitos, preço desejado, história do
   item, ou se são vários itens formando um kit/lote). Use isso como ponto de
   partida da identificação, mas confirme/complete com pesquisa na web.

## Fluxo principal

```bash
cd ~/Projects/mercado-livre-anunciar
./.venv/bin/anunciar --template /caminho/das/fotos
```

Isso gera um JSON em branco em `~/.config/anunciar/logs/template-*.json` com
os campos de `identification`. Preencha você mesmo (leia as fotos com a
ferramenta Read, pesquise o produto e o preço com WebSearch), seguindo estas
regras:

- Estado: `used` (usado) é o padrão da conta; ajuste `condition_notes` para
  refletir a realidade de cada item, mesmo que a config geral seja "usado".
- Tipo de anúncio Premium, sem garantia — isso já é resolvido pelo config,
  não precisa preencher no JSON.
- Frete grátis só valerá acima de R$200 (regra de preço aplicada
  automaticamente); não precisa calcular isso no JSON.
- Preço final deve terminar em `,90` — o CLI ajusta automaticamente o
  `suggested_price_brl` para o valor mais próximo terminado em ,90, então pode
  sugerir o preço "redondo" que fizer sentido pela pesquisa.
- **NUNCA invente dado**: campo não encontrado/não pesquisável = `null`.
- Se o Diego já deu um preço desejado, use-o como `suggested_price_brl` (ele
  ainda será normalizado para terminar em ,90) e deixe `price_research: []`.
- Se a pesquisa encontrar anúncios similares, preencha `price_research` como
  lista de objetos `{"source", "price_brl", "is_brazil", "notes"}`.

Depois de preencher o JSON, publique:

```bash
./.venv/bin/anunciar --replay /caminho/do/template.json
```

- O `--replay` precifica, resolve categoria/atributos, cria o item
  **pausado** para revisão, publica a descrição e **envia a URL do anúncio no
  Telegram automaticamente** (via `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` do
  `.env`).
- Só use `--publish` (anúncio já ativo, sem revisão) se o Diego pedir
  explicitamente.

## Depois de rodar

1. Confira no resumo final o campo **Link** (permalink) e o **Item** (MLB...).
2. Confirme que **não** apareceu o aviso `Falha ao notificar no Telegram` —
   se apareceu, ou se `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` não estiverem no
   `.env`, avise o Diego que o Telegram não recebeu o link e cole o permalink
   na conversa.
3. Reporte ao Diego: título, preço, categoria, link, e lembre que o anúncio
   está pausado — para ativar após revisão:
   `./.venv/bin/anunciar --activate MLB1234567890`.

## Erros e correções

- **Falha na criação** (`MLError`): o log fica salvo em
  `~/.config/anunciar/logs/`. Corrija o JSON (ex.: categoria pedindo atributo
  que o item não tem → adicione `category_id_override` em `identification`
  mirando uma categoria irmã mais genérica, ex. "Outros" dentro de "Livros,
  Revistas e Comics") e rode `--replay` no log corrigido.
- **Item já criado com problema** (ex.: descrição rejeitada): **não rode
  `--replay` de novo** — isso duplica o anúncio. Corrija via API num script
  Python pontual com `anunciar.ml_api.MLClient`
  (`set_description(item_id, texto)` / `update_item`).
- **Descrição rejeitada por caracteres CJK** (`item.description.type.invalid`):
  o ML não aceita chinês/japonês/coreano na descrição — romanize ou remova os
  nomes originais.
- **Sem tokens do ML**: rode `./.venv/bin/anunciar --auth` (fluxo OAuth único,
  interativo — peça para o Diego fazer).
