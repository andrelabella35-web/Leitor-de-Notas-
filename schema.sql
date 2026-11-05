CREATE TABLE IF NOT EXISTS notas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa      TEXT,
    cnpj         TEXT,             -- formato 00.000.000/0000-00 (dígitos verificadores validados)
    valor_total  NUMERIC,          -- em reais
    data_emissao TEXT,             -- ISO 8601: AAAA-MM-DD
    data_vencimento TEXT,          -- ISO 8601: AAAA-MM-DD
    arquivo      TEXT NOT NULL,
    resposta_ia  TEXT,             -- resposta bruta do modelo, para auditoria
    sessao       TEXT,             -- visitante (cookie); usado no modo demo
    criado_em    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
