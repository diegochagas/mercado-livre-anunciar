# mercado-livre-anunciar

Cria um anúncio no **Mercado Livre** (mercadolivre.com.br, site MLB) a partir de
uma pasta de fotos de um produto — tudo pela API oficial, sem automação de
navegador.

```bash
anunciar /home/diego/Downloads/fuma
```

O que acontece:

1. Lê as imagens da pasta em **ordem alfabética** (a primeira vira a capa).
   As fotos **não são alteradas** — o upload usa os arquivos originais.
2. Envia todas as fotos para a API da Anthropic (com busca na web habilitada),
   que identifica a publicação, pesquisa dados reais (Guia dos Quadrinhos,
   Amazon, Mercari JP, Suruga-ya, Yahoo Auctions etc.) e sugere um preço.
3. Aplica as regras de preço em código (final **,90**; piso de 2,5–3x para item
   raro importado) e monta a descrição em pt-BR só com fatos pesquisados.
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
| `ANTHROPIC_API_KEY` | console.anthropic.com |
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
- preço termina em ,90; item raro importado = preço exterior × 2,5–3;
- modelo de IA e idioma da descrição.

Edite o arquivo para mudar qualquer regra (veja `config.example.toml` com
comentários) — nada disso é hardcoded. Para um cenário pontual:

```bash
anunciar --config /caminho/outro.toml /pasta/das/fotos
```

## Uso no dia a dia

```bash
# criar anúncio (pausado para revisão)
anunciar /pasta/das/fotos

# revisar no site e então ativar
anunciar --activate MLB1234567890

# publicar já ativo, sem pausa para revisão
anunciar --publish /pasta/das/fotos

# ensaio: identifica, precifica e monta o payload SEM escrever no ML
anunciar --dry-run /pasta/das/fotos

# repetir uma execução usando o log salvo (não chama a Anthropic de novo)
anunciar --replay ~/.config/anunciar/logs/run-20260807-101530.json

# gerar um JSON modelo para preencher a identificação à mão (sem gastar
# créditos da Anthropic) e depois publicar com --replay
anunciar --template /pasta/das/fotos
```

Todo run gera um JSON em `~/.config/anunciar/logs/` com a identificação e o
payload — um dry-run pode ser "promovido" a publicação real via `--replay`, e
uma falha de validação do ML pode ser reexecutada sem custo de identificação.

Cada identificação (via `identify()`, não via `--replay`/`--template`) imprime
no resumo final os tokens de entrada/saída gastos na chamada à Anthropic e uma
estimativa de custo em USD (tabela de preços pública, aproximada).

Se a criação falhar, o corpo completo do erro do ML é impresso, incluindo o
array `cause`, que aponta o atributo problemático.

### Preenchendo o modelo (`--template`)

O JSON gerado tem o mesmo formato de um log (`folder`, `images`,
`identification`) e pode ser editado e reenviado com `anunciar --replay
caminho.json`. Os campos de `identification` seguem o mesmo schema pedido à
Anthropic em `identify.py` — preencha à mão ou peça para qualquer assistente
pesquisar e preencher por você.

Um campo extra, opcional, é aceito em `identification`:

- `category_id_override`: força um `category_id` do ML (ex. `"MLB1227"`),
  pulando a predição automática (`resolve_category`). Útil quando a predição
  erra a categoria (ex. sugere "Seriados" para uma coleção de livros) ou
  quando a categoria certa exige um atributo que o item não tem (ex. GTIN/ISBN
  único para um lote com vários volumes) — nesse caso vale a pena mirar uma
  categoria irmã mais genérica (ex. "Outros" dentro de "Livros, Revistas e
  Comics").

## Observações

- **User Products**: o ML está migrando a estrutura de publicação. A ferramenta
  detecta a tag `user_product_seller` na conta e, quando presente, envia
  `family_name` no lugar de `title`, como exige o novo modelo. Enquanto a conta
  não for migrada, vale o fluxo clássico (`title`).
- `condition: used` é enviado junto com o atributo `ITEM_CONDITION` (o campo
  `condition` está sendo depreciado pelo ML em favor do atributo).
- O modelo de IA configurado precisa suportar web search + adaptive thinking
  (família Claude 4.6+).
