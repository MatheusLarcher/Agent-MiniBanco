"""Agente de Conta.

>>> ISTO É UM "SUB-AGENT". <<<
Um LlmAgent normal. O que o torna sub-agente é ele ser listado em
`sub_agents=[...]` do agente principal (ver mini_banco/agent.py).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from mini_banco import prompts
from mini_banco.config import MODELO, RETRY
from mini_banco.limitador import limitar_rpm
from mini_banco.tools.conta_tools import (
    consultar_dados_conta,
    consultar_extrato,
    consultar_saldo,
)
from mini_banco.tools.memoria_tools import listar_preferencias, salvar_preferencia

agente_conta = LlmAgent(
    name="agente_conta",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    # `description` é o que o AGENTE PRINCIPAL lê para decidir se delega para cá.
    # É diferente de `instruction`, que é o system prompt deste agente.
    description=(
        "Especialista em conta: saldo, extrato, movimentações, gastos por categoria, "
        "dados cadastrais, agência, tipo de conta e score de crédito."
    ),
    instruction=prompts.CONTA,
    # Funções Python cruas: o ADK embrulha cada uma em FunctionTool sozinho.
    tools=[
        consultar_saldo,
        consultar_extrato,
        consultar_dados_conta,
        # preferências do cliente (State com prefixo user:) — todo agente tem
        salvar_preferencia,
        listar_preferencias,
    ],
)
