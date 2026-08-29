# mercado-livre-anunciar

Regra fixa: qualquer anúncio no Mercado Livre criado a partir deste projeto
(ou a pedido do Diego para "criar um anúncio", "anunciar" um produto etc.)
**deve ser criado pela API oficial do Mercado Livre usando o CLI `anunciar`
deste repositório — nunca por automação de navegador** (Claude in Chrome,
Claude Browser, Playwright ou similar).

Por quê: o fluxo por navegador (usado pela skill `mercadolivre-anuncio`) é
frágil (coordenadas de tela desalinham, dialogs nativos de upload não são
visíveis) e mais lento. O `anunciar` já resolve categoria, atributos,
sale_terms, frete e tipo de anúncio direto na API, sem esses problemas.

Como usar (a skill `mercado-livre-anunciar`, em
`.claude/skills/mercado-livre-anunciar/` e symlinkada em `~/.claude/skills/`,
descreve o fluxo completo — prefira invocá-la):

O CLI **não chama nenhuma API de IA para identificar o produto** — não há
`ANTHROPIC_API_KEY` a configurar. A identificação (o que é o produto, estado
de conservação, preço de mercado) é sempre feita pelo Claude que estiver
rodando o comando, olhando as fotos e pesquisando na web, e preenchida à mão
no JSON de identificação:

```bash
cd ~/Projects/mercado-livre-anunciar
source .venv/bin/activate   # ou chame ./.venv/bin/anunciar diretamente
anunciar --template /caminho/das/fotos
# preencha manualmente o campo "identification" do JSON gerado (pesquise o
# produto e o preço você mesmo: usado, Premium, sem garantia, frete grátis só
# acima de R$200, preço terminado em ,90, nunca inventar dado — campo não
# encontrado = null)
anunciar --replay /caminho/do/template.json
```

Regra fixa: o anúncio é sempre criado **já ativo** — nunca pausado para
revisão. Não existe flag para pausar a publicação.

Notificação no Telegram (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` no `.env`) é
**silenciosa em caso de sucesso**: envia só a URL final do anúncio, sem
título/status. Só manda uma mensagem de alerta se a criação **falhar**; se o
resumo mostrar `Falha ao notificar no Telegram` (falha ao entregar a própria
notificação), repasse o link manualmente ao Diego.

Note bem:

- `--replay` sempre chama `POST /items` (cria um item novo). Para corrigir
  um item já criado (ex.: descrição rejeitada por caracteres não-latinos),
  **não rode `--replay` de novo** — isso duplica o anúncio. Corrija os dados
  e chame a API diretamente (`MLClient().set_description(item_id, texto)` /
  `update_item`) num script Python pontual usando o client do próprio
  pacote (`anunciar.ml_api.MLClient`).
- A descrição do ML (`POST /items/{id}/description`) rejeita caracteres
  CJK (chinês/japonês/coreano) com erro `item.description.type.invalid` —
  mantenha nomes originais em outro idioma fora da descrição (ou romanizados)
  quando o produto for chinês/japonês/coreano.
- Se a categoria prevista (`domain_discovery`) pedir atributo que o item não
  tem (ex. GTIN/ISBN único para item sem editora oficial), use
  `category_id_override` no JSON de identificação mirando uma categoria
  irmã mais genérica (ex. "Outros" dentro de "Livros, Revistas e Comics").
