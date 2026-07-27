"""Login demo — preenche o State quando a sessão nasce vazia.

>>> ISTO É UM "before_agent_callback". <<<

O ADK chama esta função UMA VEZ, antes do agente raiz começar a trabalhar.
Como ela recebe o `Context`, dá para mexer no State antes de qualquer prompt
ser montado.

Por que existe: o `app/server.py` cria a Session já com o cliente logado
(`conta_numero` no State). Mas a UI oficial `adk web` não sabe disso — ela cria
sessões com State VAZIO. Aí a interpolação `{nome_cliente}` das instruções
estourava com `KeyError: Context variable not found`.

Aqui a gente resolve: se ninguém está autenticado, entra o cliente de
demonstração. Num banco de verdade, este seria o ponto onde você validaria o
token do usuário e carregaria o cadastro dele.
"""

from __future__ import annotations

import os

from banco.db import buscar_um

CLIENTE_DEMO = os.getenv("CLIENTE_DEMO", "CLI001")


def login_demo(callback_context) -> None:
    """Garante que o State tenha cliente autenticado. Devolver None = segue o fluxo."""
    estado = callback_context.state
    if estado.get("conta_numero"):
        return None  # já tem alguém logado (veio do app/server.py)

    linha = buscar_um(
        "SELECT cl.id, cl.nome, c.numero FROM clientes cl "
        "JOIN contas c ON c.cliente_id = cl.id WHERE cl.id = ?",
        (CLIENTE_DEMO,),
    )
    if not linha:
        return None

    estado["cliente_id"] = linha["id"]
    estado["nome_cliente"] = linha["nome"]
    estado["conta_numero"] = linha["numero"]
    return None
