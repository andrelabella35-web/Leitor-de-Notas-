"""Acesso ao banco: SQLite (padrão) ou Postgres (quando DATABASE_URL está definida)."""
import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import config


def _pg() -> bool:
    return bool(config.DATABASE_URL)


@contextmanager
def conexao():
    if _pg():
        import psycopg  # só necessário em produção (requirements.txt)
        from psycopg.rows import dict_row
        con = psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
    else:
        con = sqlite3.connect(config.SQLITE_PATH)
        con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _exec(con, sql: str, params=()):
    return con.execute(sql.replace("?", "%s") if _pg() else sql, params)


def iniciar():
    with conexao() as con:
        if _pg():
            for comando in (config.BASE / "schema_postgres.sql").read_text().split(";"):
                if comando.strip():
                    con.execute(comando)
            return
        con.executescript((config.BASE / "schema.sql").read_text())
        existentes = {r["name"] for r in con.execute("PRAGMA table_info(notas)")}
        for c in ("cnpj", "data_vencimento", "sessao"):  # migração de bancos antigos
            if c not in existentes:
                con.execute(f"ALTER TABLE notas ADD COLUMN {c} TEXT")


def inserir(dados: dict, arquivo: str, resposta_ia: str | None, sessao: str | None) -> int:
    emissao, venc = dados["data_emissao"], dados["data_vencimento"]
    if _pg():  # coluna DATE: entregar objetos date, não texto
        emissao = date.fromisoformat(emissao) if emissao else None
        venc = date.fromisoformat(venc) if venc else None
    with conexao() as con:
        cur = _exec(
            con,
            "INSERT INTO notas (empresa, cnpj, valor_total, data_emissao, data_vencimento, arquivo, resposta_ia, sessao) "
            "VALUES (?,?,?,?,?,?,?,?) RETURNING id",
            (dados["empresa"], dados["cnpj"], dados["valor_total"], emissao, venc, arquivo, resposta_ia, sessao),
        )
        return cur.fetchone()["id"]


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ", timespec="seconds") if hasattr(v, "hour") else v.isoformat()
    return v


def listar(sessao: str | None = None) -> list[dict]:
    """Lista as notas (mais novas primeiro). Com `sessao`, só as daquele visitante."""
    sql = "SELECT id, empresa, cnpj, valor_total, data_emissao, data_vencimento, arquivo, criado_em FROM notas"
    params = ()
    if sessao is not None:
        sql, params = sql + " WHERE sessao = ?", (sessao,)
    with conexao() as con:
        rows = _exec(con, sql + " ORDER BY id DESC", params).fetchall()
    return [{k: _json(v) for k, v in dict(r).items()} for r in rows]


def apagar_antigas(horas: int) -> int:
    if horas <= 0:
        return 0
    with conexao() as con:
        if _pg():
            cur = con.execute("DELETE FROM notas WHERE criado_em < now() - make_interval(hours => %s)", (horas,))
        else:
            cur = con.execute("DELETE FROM notas WHERE criado_em < datetime('now','localtime', ?)", (f"-{horas} hours",))
        return cur.rowcount
