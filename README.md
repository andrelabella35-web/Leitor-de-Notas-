# Leitor de Notas Fiscais

Aplicação web que recebe uma nota fiscal em **PDF**, usa **IA de visão** para ler os dados e grava tudo de forma estruturada em um banco **SQL**.

Campos extraídos: **empresa emitente, CNPJ, valor total, data de emissão e data de vencimento.**

Dois modos de uso, escolhidos por configuração:

| | Local (privado) | Nuvem (demo público) |
|---|---|---|
| IA | `qwen2.5vl` via [Ollama](https://ollama.com) | API gratuita do Google Gemini |
| Banco | SQLite | PostgreSQL (Supabase) |
| Velocidade | ~50 s por nota (CPU, sem GPU) | segundos |
| Dados saem da máquina? | Não | Sim, para a API de IA |

## Como funciona

```
PDF ─► motor de leitura ─► validação/normalização ─► SQL
        ├─ Ollama: pdftoppm (PDF→PNG) + qwen2.5vl      (local)
        └─ Gemini: PDF enviado direto à API             (nuvem)
```

1. O navegador envia o PDF para `POST /api/upload`.
2. O motor escolhido (`MOTOR=ollama|gemini`) devolve um JSON com os campos.
3. A resposta passa por uma camada de **validação e normalização** (abaixo).
4. O registro é salvo no banco e aparece na tabela da página.

### Validação e normalização

Modelos de linguagem erram, então a resposta nunca vai direto ao banco (`dados.py`):

- **CNPJ:** só é gravado se os dois dígitos verificadores baterem; formato `00.000.000/0000-00`. Inválido vira `NULL`.
- **Datas:** aceita `AAAA-MM-DD`, `DD/MM/AAAA` e `DD-MM-AAAA`; grava em ISO 8601. Datas impossíveis (31/02) viram `NULL`.
- **Valor:** entende o formato brasileiro (`1.287,40`); zero, negativo ou ilegível vira `NULL` em vez de um valor falso.
- **Auditoria:** no modo local, a resposta bruta do modelo fica em `resposta_ia`.

## Banco de dados

[`schema.sql`](schema.sql) (SQLite) e [`schema_postgres.sql`](schema_postgres.sql) (Postgres, com datas `DATE`, valores `NUMERIC(14,2)` e RLS ativo).

| Coluna | Observação |
|---|---|
| `id` | chave primária |
| `empresa`, `cnpj` | emitente; CNPJ validado |
| `valor_total` | em reais |
| `data_emissao`, `data_vencimento` | ISO 8601 |
| `arquivo` | nome do PDF enviado (o PDF em si **não é armazenado**) |
| `resposta_ia` | JSON bruto (só no modo local) |
| `sessao` | cookie do visitante, usado para isolar usuários no demo |
| `criado_em` | data/hora |

## Rodar localmente

**Requisitos:** Python 3.10+, `pdftoppm` (`sudo apt install poppler-utils`) e Ollama. Sem dependências Python extras.

```bash
ollama pull qwen2.5vl:3b
python3 app.py          # http://localhost:8000
```

Para usar o Gemini localmente: `MOTOR=gemini GEMINI_API_KEY=... python3 app.py`.

### Testes

```bash
python3 -m unittest discover -s tests
```

32 testes, sem Ollama, sem internet e sem chave de API: validação de CNPJ/datas/valores, limitador de uso, banco (incluindo migração e isolamento por visitante), o formato da requisição ao Gemini (contra um servidor falso) e a API de ponta a ponta.

## Publicar o demo (gratuito)

1. **Chave do Gemini:** crie em [Google AI Studio](https://aistudio.google.com) (sem cartão). Confira lá os modelos e limites gratuitos atuais e ajuste `GEMINI_MODELO` se preciso.
2. **Banco:** crie um projeto gratuito no [Supabase](https://supabase.com) e copie a *connection string* (Settings → Database). O app cria a tabela sozinho na primeira execução.
3. **Hospedagem:** no [Render](https://render.com), *New → Blueprint* e aponte para este repositório (`render.yaml`). Informe `GEMINI_API_KEY` e `DATABASE_URL` no painel.
4. Defina um **teto de gasto/cota** na conta da API e acompanhe o uso.

### Variáveis de ambiente (`config.py`)

| Variável | Padrão | Função |
|---|---|---|
| `MOTOR` | `ollama` | `ollama` ou `gemini` |
| `GEMINI_API_KEY`, `GEMINI_MODELO` | — / `gemini-2.5-flash` | motor Gemini |
| `OLLAMA_MODELO`, `OLLAMA_URL`, `DPI` | `qwen2.5vl:3b`, `localhost:11434`, `100` | motor local |
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
python3 scripts/avaliar.py          # roda o motor configurado e imprime a acurácia por campo
```

Resultado com `qwen2.5vl:3b` (motor local, 100 dpi) em **12 notas fictícias** (3 layouts, ~48 s por nota):

| Campo | Acertos |
|---|---|
| empresa | 12/12 (100%) |
| cnpj | 12/12 (100%) |
| valor_total | 12/12 (100%) |
| data_emissao | 12/12 (100%) |
| data_vencimento | 12/12 (100%) |

> **Atenção:** são notas sintéticas, com texto limpo e rótulos claros. É o melhor cenário possível; em notas reais (escaneadas, com ruído, layouts densos) o resultado tende a ser pior. O gabarito está em `samples/gabarito.json` e o resultado detalhado em `samples/resultado_avaliacao.json`. O Gemini ainda não foi avaliado.

## Decisões técnicas

- **Dois motores:** o local mostra privacidade e custo zero; o da nuvem torna o demo acessível sem exigir 4 GB de RAM livres.
- **Modelo 3B e 100 dpi:** desenvolvido numa máquina de 8 GB de RAM, sem GPU. O `qwen2.5vl:7b` e a renderização a 150 dpi foram encerrados pelo OOM killer do Linux.
- **Só biblioteca padrão:** `http.server`, `sqlite3`, `urllib`. A única dependência (`psycopg`) é de produção.
- **Postgres com RLS:** o Supabase expõe o schema `public` por REST; sem RLS a tabela ficaria aberta à chave pública.

## Limitações

- O motor local lê só a **primeira página**; o Gemini recebe o PDF inteiro.
- O motor local leva cerca de 1 minuto por nota; modelos pequenos erram mais em notas densas ou escaneadas, por isso campos inválidos viram `NULL`.
- Limitador de uso em memória: reinicia com o servidor e não é compartilhado entre várias instâncias.
- Avaliada apenas em notas sintéticas de texto limpo; o desempenho em notas reais tende a ser menor.
- Sem autenticação: pensado para `localhost` ou demo com notas fictícias.

## Autor

André Labella — [github.com/andrelabella35-web](https://github.com/andrelabella35-web)  ·  Licença [MIT](LICENSE)
