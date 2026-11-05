CREATE TABLE IF NOT EXISTS notas (
    id              BIGSERIAL PRIMARY KEY,
    empresa         TEXT,
    cnpj            TEXT,
    valor_total     NUMERIC(14,2),
    data_emissao    DATE,
    data_vencimento DATE,
    arquivo         TEXT NOT NULL,
    resposta_ia     TEXT,
    sessao          TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notas_sessao_idx ON notas (sessao);
-- Supabase expõe o schema public pela API REST: sem RLS e sem políticas, a tabela fica fechada para a chave anônima.
-- O app conecta direto como dono do banco (DATABASE_URL), que ignora o RLS.
ALTER TABLE notas ENABLE ROW LEVEL SECURITY;
