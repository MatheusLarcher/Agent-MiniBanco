"""Acesso ao SQLite.

Isto NÃO é Google ADK — é a camada de dados comum do projeto.
As Tools do ADK importam daqui para consultar/alterar o banco.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data"
CAMINHO_BANCO = DADOS / "banco.db"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, devolve linhas como dicionário e SEMPRE fecha no fim.

    Cuidado: `with sqlite3.connect(...)` sozinho faz commit/rollback mas NÃO
    fecha a conexão. No Windows isso deixa o arquivo .db travado ("já está
    sendo usado por outro processo") e derruba o `python -m banco.seed`.
    Por isso o `closing()`.
    """
    DADOS.mkdir(exist_ok=True)
    with closing(sqlite3.connect(CAMINHO_BANCO)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        yield con


def buscar_um(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with conectar() as con:
        linha = con.execute(sql, params).fetchone()
        return dict(linha) if linha else None


def buscar_varios(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conectar() as con:
        return [dict(l) for l in con.execute(sql, params).fetchall()]


def executar(sql: str, params: tuple = ()) -> int:
    with conectar() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount


def banco_existe() -> bool:
    return CAMINHO_BANCO.exists()
