# mercado-livre-anunciar

Cria um anúncio no **Mercado Livre** (mercadolivre.com.br, site MLB) a partir de
uma pasta de fotos de um produto — tudo pela API oficial, sem automação de
navegador.

```bash
anunciar /home/diego/Downloads/fuma
# preencha o JSON gerado com os dados reais do produto
anunciar --replay ~/.config/anunciar/logs/template-*.json
```

O que acontece:

1. `anunciar /pasta` lê as imagens em **ordem alfabética** (a primeira vira a
   capa) e gera um JSON modelo em `~/.config/anunciar/logs/` com os campos de
   identificação em branco. As fotos **não são alteradas** — o upload usa os
   arquivos originais.
2. A identificação (o que é o produto, estado de conservação, pesquisa de
   preço) **não é feita por nenhuma API de IA embutida no CLI** — é feita por
   quem estiver rodando o comando (tipicamente um agente Claude, olhando as
   fotos e pesquisando na web: Guia dos Quadrinhos, Amazon, Mercari JP,
   Suruga-ya, Yahoo Auctions etc.), preenchendo o JSON à mão.
3. `anunciar --replay template.json` aplica as regras de preço em código
   (final **,90**; piso de 2,5–3x para item raro importado) e monta a
   descrição em pt-BR só com os fatos preenchidos.
4. Resolve categoria (predictor + fallback em "Livros, Revistas e Comics"),
   atributos, garantia ("Sem garantia") e tipo Premium dinamicamente.
5. Sobe as fotos, cria o item **pausado** para revisão, publica a descrição e
   imprime o resumo com o link.

## Instalação

```bash
cd ~/Projects/mercado-livre-anunciar
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

(O `pip install -e .` instala as dependências do `requirements.txt` e o comando
`anunciar` dentro da venv.)

## Credenciais (.env)

Copie `.env.example` para `.env` na raiz do projeto e preencha:

| Variável | Onde obter |
|---|---|
| `ML_CLIENT_ID` / `ML_CLIENT_SECRET` | app criado em developers.mercadolivre.com.br |
| `ML_REDIRECT_URI` | a mesma Redirect URI cadastrada no app |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | opcional — se definidas, envia o link do anúncio pro Telegram quando ele é criado |

### Criando o app no Mercado Livre

1. Acesse <https://developers.mercadolivre.com.br> logado na conta vendedora e
   crie uma aplicação ("Criar aplicação" / DevCenter).
2. Defina uma **Redirect URI** (pode ser qualquer URL sua, ex.
   `https://example.com/callback` — você só vai copiar o `code` dela).
3. Marque os escopos de leitura/escrita (read, write, offline_access).
4. Copie o App ID e a Secret Key para o `.env`.

## Autenticação (uma vez)

```bash
anunciar --auth
```

Abra a URL impressa, autorize, cole a URL de redirect (ou só o `code`). Os
tokens ficam em `~/.config/anunciar/tokens.json` (permissão 600) e são
renovados automaticamente a cada execução (o refresh token do ML é de uso
único; o novo par é sempre persistido).

## Configuração (`~/.config/anunciar/config.toml`)

Criada automaticamente na primeira execução com os padrões do Diego:

- sempre **usado**, quantidade 1, **Premium**, **sem garantia**, disponibilidade
  1 dia, criado **pausado**;
- frete grátis somente se preço > R$ 200 (nunca Flex);
- preço termina em ,90; item raro importado = preço exterior × 2,5–3.

Edite o arquivo para mudar qualquer regra (veja `config.example.toml` com
comentários) — nada disso é hardcoded. Para um cenário pontual:

```bash
anunciar --config /caminho/outro.toml /pasta/das/fotos
```

## Uso no dia a dia

```bash
# gerar o JSON modelo de identificação (em branco) para uma pasta de fotos
anunciar /pasta/das/fotos

# preencha "identification" no JSON gerado à mão (veja a seção abaixo) e então:
anunciar --replay ~/.config/anunciar/logs/template-20260825-101530.json

# revisar no site e então ativar
anunciar --activate MLB1234567890

# publicar já ativo, sem pausa para revisão
anunciar --publish --replay ~/.config/anunciar/logs/template-....json

# ensaio: precifica e monta o payload SEM escrever no ML
anunciar --dry-run --replay ~/.config/anunciar/logs/template-....json
```

Todo run gera um JSON em `~/.config/anunciar/logs/` com a identificação e o
payload — um dry-run pode ser "promovido" a publicação real via `--replay`, e
uma falha de validação do ML pode ser reexecutada sem repetir a identificação.

Se a criação falhar, o corpo completo do erro do ML é impresso, incluindo o
array `cause`, que aponta o atributo problemático.

### Preenchendo o modelo

O JSON gerado tem o formato `folder`, `images`, `identification` e pode ser
editado e reenviado com `anunciar --replay caminho.json`. Os campos de
`identification` (`title_ml`, `product_type`, `full_name`, `author_or_cast`,
`price_research`, `suggested_price_brl` etc.) são preenchidos à mão — por
quem estiver rodando o comando (tipicamente um agente Claude, olhando as
fotos e pesquisando o produto e o preço na web) — e não por nenhuma chamada
de API embutida no CLI. Campo não encontrado = `null`; nunca invente dado.

Um campo extra, opcional, é aceito em `identification`:

- `category_id_override`: força um `category_id` do ML (ex. `"MLB1227"`),
  pulando a predição automática (`resolve_category`). Útil quando a predição
  erra a categoria (ex. sugere "Seriados" para uma coleção de livros) ou
  quando a categoria certa exige um atributo que o item não tem (ex. GTIN/ISBN
  único para um lote com vários volumes) — nesse caso vale a pena mirar uma
  categoria irmã mais genérica (ex. "Outros" dentro de "Livros, Revistas e
  Comics").

## Skill do Claude Code (`mercado-livre-anunciar`)

O repositório inclui uma skill em `.claude/skills/mercado-livre-anunciar/`
(instalada globalmente via symlink em `~/.claude/skills/`). Basta pedir ao
Claude "anuncie a pasta X" (com detalhes opcionais do produto) que ele mesmo
identifica o produto e o preço, preenche o template, roda o `--replay`, cria
o anúncio pausado via API e confirma o envio da URL no Telegram.

## Observações

- **User Products**: o ML está migrando a estrutura de publicação. A ferramenta
  detecta a tag `user_product_seller` na conta e, quando presente, envia
  `family_name` no lugar de `title`, como exige o novo modelo. Enquanto a conta
  não for migrada, vale o fluxo clássico (`title`).
- `condition: used` é enviado junto com o atributo `ITEM_CONDITION` (o campo
  `condition` está sendo depreciado pelo ML em favor do atributo).
