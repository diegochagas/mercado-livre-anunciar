---
name: mercado-livre-anunciar-servico
description: Cria um anúncio de SERVIÇO no Mercado Livre (classificado dentro de Serviços, ex. restauração de fotos, aulas, manutenção, design) pela API oficial, usando o CLI `anunciar-servico` de ~/Projects/mercado-livre-anunciar. Use SEMPRE que o Diego pedir para "anunciar um serviço", "publicar serviço no ML/Mercado Livre", "anúncio de serviço", ou quando o que ele quer vender é trabalho/mão de obra/serviço digital e não um objeto físico — mesmo que ele cite a skill de produto. Para objeto físico (livro, HQ, colecionável) use a skill `mercado-livre-anunciar`.
---

# Anunciar SERVIÇO no Mercado Livre (CLI `anunciar-servico`)

Serviço no ML **não é produto**: fica na árvore **Serviços (MLB1540)**, que só
aceita **classificado**. Por isso esta skill usa um CLI próprio,
`anunciar-servico`, e **nunca** o `anunciar` de produto. O `anunciar` mandaria
`buy_it_now`, `condition`, Mercado Envios, Premium e uma descrição de "item
real que será enviado", e o ML rejeitaria ou o anúncio sairia errado.

Nunca use automação de navegador. Tudo passa pela API oficial.

O que o CLI já garante (não precisa preencher nem ajustar):

- `buying_mode: classified`;
- **sem `condition`**: Serviços tem `item_conditions: not_allowed`, então nem
  "new" é aceito. Se o Diego pedir "condição novo", explique isso;
- **sem frete**: nada de Mercado Envios, e a regra de frete grátis acima de
  R$200 não vale para serviço;
- `location` com a cidade do classificado (obrigatória);
- preço normalizado para terminar em `,90`;
- título acima de 60 caracteres dá **erro**. Não há corte automático: você
  encurta e mostra ao Diego;
- templates/logs com nome único, então nenhum sobrescreve outro.

## Fluxo

```bash
cd ~/Projects/mercado-livre-anunciar
./.venv/bin/anunciar-servico /caminho/da/pasta-de-fotos
```

Um template por anúncio. Se o Diego quer dois anúncios (ex. dois níveis de
serviço), são duas pastas e dois templates. O template vai para
`~/.config/anunciar/logs/servico-template-<pasta>-<data>.json` com o bloco
`service`:

| Campo | Como preencher |
|---|---|
| `title` | Até 60 caracteres. Se o Diego deu um título maior, proponha uma versão curta e mostre as duas |
| `description` | Texto livre, exatamente o que vai ao anúncio. Sem CJK (o ML rejeita). Deixe claro que é serviço digital, como o cliente envia/recebe e o prazo. Preço variável ("a partir de") vai aqui |
| `price_brl` | Número. "A partir de R$59,90" → `59.9` + frase na descrição |
| `category_id` | Folha dentro de Serviços. Veja "Categoria" abaixo |
| `listing_type_id` | Deixe `null` no 1º dry-run: ele lista os tipos disponíveis. **O Diego escolhe**, porque classificado pode ter custo |
| `city` / `state` | Nomes ("Campinas", "São Paulo"). Se `null`, o CLI usa o endereço da conta ML. Não invente: pergunte se não souber |
| `seller_contact` | Opcional (`contact`, `area_code`, `phone`, `email`, `other_info`). Só com dados que o Diego der. Campos `null` não são enviados |
| `notes` | Anotações suas, não vão ao ML |

A primeira foto em ordem alfabética é a capa (máx. 12). Para serviço, as fotos
são **exemplos do trabalho** (antes/depois, portfólio). Nunca diga que são
"o item que será enviado".

### Categoria

O `domain_discovery` quase sempre erra em serviço: "restauração de fotos",
por exemplo, cai em *Antiguidades e Coleções > Fotos*, que é produto. Não use
predição. Navegue a árvore pública e escolha a **folha** mais específica:

```bash
curl -s https://api.mercadolibre.com/categories/MLB1540 | python3 -m json.tool
```

Referências já pesquisadas (2026-09-28):

| Serviço | Categoria |
|---|---|
| Restauração / edição / tratamento de fotos | **MLB63927** Serviços > Gráficas e Impressão > Outros (não existe folha própria). Alternativas: MLB63887 …> Impressão de Fotos, MLB9016 Outros Serviços > Outros |
| Criação de sites | MLB63949 |
| Marketing online | MLB63948 |
| Recuperação de dados | MLB94657 |
| Aulas particulares | MLB1568 |
| Tradução | MLB9018 |
| Genérico | MLB9016 Outros Serviços > Outros · MLB1894 Outros Profissionais > Outros |

O CLI recusa categoria fora de Serviços, que não seja folha ou que não aceite
classificado.

### Dry-run (obrigatório antes de publicar)

```bash
./.venv/bin/anunciar-servico --dry-run --replay ~/.config/anunciar/logs/servico-template-....json
```

- Nunca cria nada e **nunca manda Telegram**.
- Sem token: confere categoria e cidade (endpoints públicos) e avisa que tipo
  de publicação e `/items/validate` ficaram sem conferir.
- Com token: lista os `listing_type_id` disponíveis e roda
  `POST /items/validate`, a validação do próprio ML, que não cria item. As
  causas aparecem como `Aviso: /items/validate: ...`.

Mostre ao Diego, para **cada** anúncio: título, preço, categoria (id +
caminho), cidade, tipo de publicação, descrição completa e os avisos. Depois
**espere o OK explícito** antes de publicar.

### Tipos de publicação e custo (visto na API real, 2026-09-28)

- `free` (Grátis): **uma** publicação grátis de serviço por conta, valendo em
  todas as categorias de Serviços. Depois de usada, `free` some da lista. O
  dry-run de vários anúncios mostra `free` em todos, mas só o primeiro a
  publicar consegue usar. Avise isso antes de publicar mais de um.
- `bronze`/`silver` (Com Destaque 90/180) e `gold`/`gold_premium` (Super
  Destaque 90/180) são pagos. O `/items/validate` responde 402 e o anúncio
  nasce `payment_required`: só fica ativo depois que o Diego paga no site do
  ML. A API não informa o preço, então diga isso ao Diego antes de publicar.
- O ML capitaliza o título por conta própria, e siglas viram "Ia", "Ti",
  "Dj". Evite siglas no título (o Diego pediu para tirar o "IA") e deixe
  a sigla na descrição.

### Publicar (só com OK do Diego)

```bash
./.venv/bin/anunciar-servico --replay ~/.config/anunciar/logs/servico-template-....json
```

Recusa publicar sem token, sem cidade ou sem `listing_type_id` disponível. Cria
o anúncio **ativo**, sobe as fotos, publica a descrição e manda só a URL no
Telegram (erro manda alerta). Reporte título, preço, categoria, item (MLB…) e
link. Se aparecer `Falha ao notificar no Telegram`, cole o link na conversa.

## Erros

- **Sem tokens / `Sem refresh token salvo`**: o Diego roda
  `./.venv/bin/anunciar --auth` (interativo). O token é o mesmo do `anunciar`.
- **Item criado com problema** (ex. descrição rejeitada): **não** rode
  `--replay` de novo, porque duplica o anúncio. Corrija com
  `anunciar.ml_api.MLClient().set_description(item_id, texto)` /
  `update_item(...)` num script pontual.
- **`/items/validate` pedindo atributo/campo**: ajuste o template (ou a
  categoria) e rode o dry-run de novo. Se o campo não existir no template,
  avise o Diego e trate como mudança de código (com teste em
  `tests/test_servico.py`).
