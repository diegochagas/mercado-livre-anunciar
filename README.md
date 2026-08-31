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
5. Sobe as fotos, cria o item **já ativo** (nunca pausado), publica a
   descrição e imprime o resumo com o link.

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
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | opcional — se definidas, envia só a URL do anúncio pro Telegram quando ele é criado com sucesso, ou um alerta de erro se a criação falhar |

### Criando o app no Mercado Livre

1. Acesse <https://developers.mercadolivre.com.br> logado na conta vendedora e
   crie uma aplicação ("Criar aplicação" / DevCenter).
2. Defina uma **Redirect URI** (pode ser qualquer URL sua, ex.
   `https://example.com/callback` — você só vai copiar o `code` dela).
3. Marque os escopos de leitura/escrita (read, write, offline_access).
4. Copie o App ID e a Secret Key para o `.env`.

## Autenticação (uma vez)

```bash
cd ~/Projects/mercado-livre-anunciar
source .venv/bin/activate
anunciar --auth
```

O comando monta a URL de autorização do ML com o `ML_CLIENT_ID` e a
`ML_REDIRECT_URI` do seu `.env`, imprime essa URL no terminal e fica
aguardando o `code`. Passo a passo:

1. Abra a URL impressa no navegador, **logado na conta que vai vender**.
2. Clique em "Autorizar". O navegador é redirecionado para a sua
   `ML_REDIRECT_URI` com `?code=TG-...` no final — essa é a "URL de
   redirect". Se a Redirect URI apontar para uma página que não existe
   (ex. `https://example.com/callback`), o navegador vai mostrar um
   erro/404: **não tem problema** — o que interessa é só a URL que ficou
   na barra de endereço.
3. Copie a URL completa da barra de endereço (ou apenas o `code=TG-...`)
   e cole de volta no terminal, onde o comando está esperando.

Os tokens ficam em `~/.config/anunciar/tokens.json` (permissão 600) e são
renovados automaticamente a cada execução (o refresh token do ML é de uso
único; o novo par é sempre persistido). O `code` expira em poucos minutos —
se a troca falhar por demora, rode `anunciar --auth` de novo e repita.

## Configuração (`~/.config/anunciar/config.toml`)

Criada automaticamente na primeira execução com os padrões do Diego:

- sempre **usado**, quantidade 1, **Premium**, **sem garantia**, disponibilidade
  1 dia, criado **já ativo** (nunca pausado);
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
# cria o anúncio já ativo (nunca pausado) e publica a descrição

# --activate existe só como utilitário manual, para o caso raro de um item
# ter ficado pausado (ex.: regra da categoria no ML) e precisar ser ativado
anunciar --activate MLB1234567890

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

## Bot do Telegram (`start_bot.py`)

Fluxo alternativo sem terminal: fotografe o produto sobre um quadro branco
físico e mande as fotos pelo Telegram — o bot baixa cada uma, redimensiona
em quadrado (o fundo branco já vem na própria foto, sem remoção de fundo)
e dispara a identificação + criação do anúncio.

Pré-requisitos no `.env`: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, além
do ML já autenticado (`anunciar --auth` acima, uma vez).

```bash
cd ~/Projects/mercado-livre-anunciar
./.venv/bin/python start_bot.py
```

Use sempre `start_bot.py` (na raiz do repo, não `anunciar-bot` direto) para
subir o bot: ele confere se há um token/refresh token válido do Mercado
Livre salvo **antes** de começar o long-polling e, se não houver, roda o
fluxo interativo de `--auth` ali mesmo no terminal. Sem isso, a falta de
token só aparece depois que o Diego já mandou as fotos pelo Telegram e
pediu `/finishanuncio` — nesse ponto o bot não tem como pedir o `code` do
OAuth interativamente, e o anúncio falha com "Sem refresh token salvo".

(Equivalente ao `anunciar-bot` sozinho depois da checagem:
`./.venv/bin/python -m anunciar.bot`. O bot roda em primeiro plano fazendo
long-polling no Telegram — deixe o terminal aberto e pare com `Ctrl+C`. Ele
só responde ao chat do `TELEGRAM_CHAT_ID`.)

Enquanto roda, o bot imprime no terminal cada passo em andamento
(foto recebida, redimensionando, salvando imagem, identificando e
publicando...) — útil pra acompanhar ao vivo o que está acontecendo.

Comandos no chat do Telegram:

- `/startanuncio` — inicia uma sessão (pasta nova de fotos);
- mande as **fotos** (processadas na ordem de chegada, já sobre o quadro
  branco) e, opcionalmente, **texto livre** com detalhes do produto ("é
  novo", "quero R$80"...);
- `/finishanuncio` — identifica o produto (Claude Code headless com a skill
  deste repo — requer o CLI `claude` instalado na máquina) e cria o anúncio
  já ativo. O chat só recebe **uma mensagem no final**: o link do anúncio
  ativo em caso de sucesso, ou um alerta se algo falhar — sem mensagens
  intermediárias de progresso.

### Token expirado/ausente no meio de uma sessão

Se mesmo assim o bot cair com "Sem refresh token salvo" (ex.: revogou o
acesso do app no Mercado Livre, ou o `~/.config/anunciar/tokens.json` foi
apagado), a sessão do Telegram já processada **não se perde**: o template
com a identificação fica salvo em `~/.config/anunciar/logs/template-*.json`
(veja o path no erro). Rode `anunciar --auth` de novo e depois
`anunciar --replay ~/.config/anunciar/logs/template-XXXXXXXX-XXXXXX.json`
para publicar sem repetir a identificação.

## Skill do Claude Code (`mercado-livre-anunciar`)

O repositório inclui uma skill em `.claude/skills/mercado-livre-anunciar/`
(instalada globalmente via symlink em `~/.claude/skills/`). Basta pedir ao
Claude "anuncie a pasta X" (com detalhes opcionais do produto) que ele mesmo
identifica o produto e o preço, preenche o template, roda o `--replay`, cria
o anúncio já ativo via API e confirma o envio da URL no Telegram.

## Observações

- **User Products**: o ML está migrando a estrutura de publicação. A ferramenta
  detecta a tag `user_product_seller` na conta e, quando presente, envia
  `family_name` no lugar de `title`, como exige o novo modelo. Enquanto a conta
  não for migrada, vale o fluxo clássico (`title`).
- `condition: used` é enviado junto com o atributo `ITEM_CONDITION` (o campo
  `condition` está sendo depreciado pelo ML em favor do atributo).
