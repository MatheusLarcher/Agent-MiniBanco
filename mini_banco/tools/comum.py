"""Helpers compartilhados pelas Tools.

O truque importante aqui é `conta_da_sessao`: o número da conta NÃO vem do LLM,
vem do STATE da Session (quem está logado). Assim o modelo não consegue
"alucinar" um número de conta e ler o extrato de outra pessoa.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from banco.db import buscar_um


class SemContaError(Exception):
    pass


def conta_da_sessao(tool_context: ToolContext) -> str:
    """Lê o número da conta do State da sessão (chave 'conta_numero')."""
    numero = tool_context.state.get("conta_numero")
    if not numero:
        raise SemContaError(
            "Nenhum cliente autenticado nesta sessão (state['conta_numero'] vazio)."
        )
    return str(numero)


def erro(mensagem: str, **extra: Any) -> dict[str, Any]:
    return {"status": "erro", "mensagem": mensagem, **extra}


def ok(**dados: Any) -> dict[str, Any]:
    return {"status": "ok", **dados}


def brl(valor: float) -> str:
    """Formata 1234.5 -> 'R$ 1.234,50'."""
    s = f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {s}"


def dados_conta(numero: str) -> dict[str, Any] | None:
    return buscar_um(
        """
        SELECT c.numero, c.agencia, c.tipo, c.saldo, c.limite_especial,
               c.aberta_em, c.status,
               cl.id AS cliente_id, cl.nome, cl.cpf, cl.email, cl.telefone, cl.score
        FROM contas c
        JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.numero = ?
        """,
        (numero,),
    )
