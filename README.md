# Leitor de Notas Fiscais

Aplicação web que recebe uma nota fiscal em **PDF**, usa **IA de visão** (API gratuita do Google Gemini) para ler os dados e grava tudo de forma estruturada em um banco **SQL**.

**Demo online:** https://leitor-notas-k2en.onrender.com — use os botões de nota fictícia. O plano gratuito "dorme" após 15 min sem uso; o primeiro acesso pode levar cerca de 1 minuto.

Campos extraídos: **empresa emitente, CNPJ, valor total, data de emissão e data de vencimento.**

## Como funciona

```
PDF ──► API Gemini (lê o PDF inteiro) ──► validação/normalização ──► SQL (SQLite ou Postgres)
```

1. O navegador envia o PDF para `POST /api/upload`.
2. O servidor manda o PDF ao Gemini com um prompt que exige resposta em JSON.
3. A resposta passa por uma camada de **validação e normalização** (abaixo).
4. O registro é salvo no banco e aparece na tabela da página.

### Validação e normalização

Modelos de linguagem erram, então a resposta nunca vai direto ao banco (`dados.py`):

- **CNPJ:** só é gravado se os dois dígitos verificadores baterem; formato `00.000.000/0000-00`. Inválido vira `NULL`.
- **Datas:** aceita `AAAA-MM-DD`, `DD/MM/AAAA` e `DD-MM-AAAA`; grava em ISO 8601. Datas impossíveis (31/02) viram `NULL`.
- **Valor:** entende o formato brasileiro (`1.287,40`); zero, negativo ou ilegível vira `NULL` em vez de um valor falso.
- **Auditoria:** fora do modo demo, a resposta bruta da IA fica em `resposta_ia`.

## Banco de dados

[`schema.sql`](schema.sql) (SQLite, padrão) e [`schema_postgres.sql`](schema_postgres.sql) (Postgres, com datas `DATE`, valores `NUMERIC(14,2)` e RLS ativo).

| Coluna | Observação |
|---|---|
| `id` | chave primária |
| `empresa`, `cnpj` | emitente; CNPJ validado |
| `valor_total` | em reais |
| `data_emissao`, `data_vencimento` | ISO 8601 |
| `arquivo` | nome do PDF enviado (o PDF em si **não é armazenado**) |
| `resposta_ia` | JSON bruto (fora do modo demo) |
| `sessao` | cookie do visitante, usado para isolar usuários no demo |
| `criado_em` | data/hora |

## Rodar localmente

**Requisitos:** Python 3.10+ e uma chave gratuita do [Google AI Studio](https://aistudio.google.com) (sem cartão). Nenhuma dependência extra com SQLite.

```bash
GEMINI_API_KEY=sua-chave python3 app.py     # http://localhost:8000
```

### Testes

```bash
python3 -m unittest discover -s tests
```

31 testes, sem internet e sem chave de API: validação de CNPJ/datas/valores, limitador de uso, banco (incluindo migração e isolamento por visitante), o formato da requisição ao Gemini (contra um servidor falso) e a API de ponta a ponta.

## Publicar o demo (gratuito)

1. **Chave do Gemini:** crie no [Google AI Studio](https://aistudio.google.com) e confira lá os modelos e limites gratuitos atuais; ajuste `GEMINI_MODELO` se preciso.
2. **Banco:** crie um projeto gratuito no [Supabase](https://supabase.com) e copie a *connection string* (Settings → Database). O app cria a tabela sozinho na primeira execução.
3. **Hospedagem:** no [Render](https://render.com), *New → Blueprint* e aponte para este repositório (`render.yaml`). Informe `GEMINI_API_KEY` e `DATABASE_URL` no painel.
4. Defina um **teto de gasto/cota** na conta da API e acompanhe o uso.

### Variáveis de ambiente (`config.py`)

| Variável | Padrão | Função |
|---|---|---|
| `GEMINI_API_KEY` | — | chave da API (obrigatória) |
| `GEMINI_MODELO` | `gemini-3.1-flash-lite` | modelo usado |
| `DATABASE_URL` | vazio (SQLite) | Postgres |
| `MODO_DEMO` | `0` | isola visitantes, não guarda resposta bruta, apaga dados antigos, ativa limites |
| `LIMITE_IP_HORA`, `LIMITE_DIA` | `5`, `150` no demo | limites de uso (0 = sem limite) |
| `MAX_PDF_MB`, `RETENCAO_HORAS` | `5`, `24` no demo | tamanho máximo e retenção |
| `CONFIAR_PROXY` | `0` | atrás de proxy HTTPS: usa o IP real e cookie `Secure` |

### Proteções do demo público

- Limite de leituras por IP/hora e teto diário global (protege a cota gratuita da API).
- Cada visitante vê **só as próprias notas** (cookie `HttpOnly`); dados apagados após 24 h; PDFs nunca são gravados.
- Limite de tamanho, checagem de assinatura `%PDF`, erros internos sem detalhes para o cliente, sem segredos no código.
- Aviso na página: **não envie notas reais**, pois a API gratuita pode usar o conteúdo para melhorar os produtos do provedor.

## Medindo a acurácia

```bash
python3 scripts/gerar_amostras.py   # gera 12 notas FICTÍCIAS + gabarito em samples/
GEMINI_API_KEY=... python3 scripts/avaliar.py   # acurácia por campo; grava samples/resultado_avaliacao.json
```

Resultado com `gemini-3.1-flash-lite` em **12 notas fictícias** (3 layouts diferentes, 1 a 4 s por nota):

| Campo | Acertos |
|---|---|
| empresa | 12/12 (100%) |
| cnpj | 12/12 (100%) |
| valor_total | 12/12 (100%) |
| data_emissao | 12/12 (100%) |
| data_vencimento | 12/12 (100%) |

> **Atenção:** são notas sintéticas, com texto limpo e rótulos claros — o melhor cenário possível. Em notas reais (escaneadas, com ruído, layouts densos) o resultado tende a ser pior. Gabarito em `samples/gabarito.json`, resultado detalhado em `samples/resultado_avaliacao.json`.

## Decisões técnicas

- **IA na nuvem (Gemini):** aceita PDF direto, responde em segundos e o plano gratuito basta para um demo. Uma versão com modelo local (Ollama) foi tentada e abandonada: numa máquina de 8 GB de RAM sem GPU, o sistema encerrava o processo por falta de memória.
- **Só biblioteca padrão:** `http.server`, `sqlite3`, `urllib`. A única dependência (`psycopg`) é de produção.
- **Postgres com RLS:** o Supabase expõe o schema `public` por REST; sem RLS a tabela ficaria aberta à chave pública.
- **Privacidade:** a API gratuita pode usar o conteúdo enviado para melhorar produtos do provedor; por isso o demo usa notas fictícias e avisa o visitante.

## Limitações

- Limitador de uso em memória: reinicia com o servidor e não é compartilhado entre várias instâncias.
- Sem autenticação: pensado para `localhost` ou demo com notas fictícias.
- Depende da cota gratuita da API, que muda com o tempo.
- Sem GIF/captura de tela ainda.

## Autor

André Labella — [github.com/andrelabella35-web](https://github.com/andrelabella35-web)  ·  Licença [MIT](LICENSE)
