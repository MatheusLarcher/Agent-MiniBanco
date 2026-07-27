"""Agente de Crédito.

Mostra os DOIS jeitos de registrar uma tool:
  - função crua           -> tool de leitura, roda direto
  - FunctionTool(..., require_confirmation=...) -> tool de escrita, pede OK
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, ToolContext
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from mini_banco import prompts
from mini_banco.config import MODELO, RETRY
from mini_banco.limitador import limitar_rpm
from mini_banco.tools.credito_tools import (
    consultar_condicoes_credito,
    consultar_emprestimos,
    contratar_emprestimo,
    simular_emprestimo,
)
from mini_banco.tools.memoria_tools import listar_preferencias, salvar_preferencia


def _precisa_confirmar_contratacao(
    valor: float = 0,
    parcelas: int = 0,
    produto: str = "",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> bool:
    """Regra de segurança: contratar empréstimo SEMPRE pede confirmação.

    O ADK aceita aqui um bool fixo ou uma função como esta, que recebe os
    mesmos argumentos da tool. Dá para fazer regra por valor, por exemplo
    `return valor >= 1000`.
    """
    return True


# ---------------------------------------------------------------------------
# >>> MCP <<<  liga o agente a um servidor externo de tools.
# O McpToolset sobe o processo do servidor MCP (stdio), lê a lista de tools
# dele e as entrega ao agente como se fossem tools normais. O agente não sabe
# a diferença entre uma tool local e uma tool vinda do MCP.
# Ligue/desligue com MCP_INDICADORES=1 no .env.
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent.parent


def _toolset_mcp() -> list:
    if os.getenv("MCP_INDICADORES", "1").strip() not in ("1", "true", "True"):
        return []
    return [
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "mcp_server.servidor_indicadores"],
                    cwd=str(RAIZ),
                ),
                timeout=30.0,
            ),
            # Só estas tools do servidor entram no agente.
            tool_filter=["taxa_selic_atual", "media_mercado_credito", "inflacao_e_poupanca"],
        )
    ]


agente_credito = LlmAgent(
    name="agente_credito",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    description=(
        "Especialista em crédito: simulação de empréstimo, taxas e condições, "
        "empréstimos contratados, saldo devedor, contratação de crédito novo e "
        "indicadores de mercado (Selic, CDI, IPCA, poupança, média do mercado)."
    ),
    instruction=prompts.CREDITO,
    tools=[
        # leitura -> direto
        consultar_condicoes_credito,
        simular_emprestimo,
        consultar_emprestimos,
        # ESCRITA, estilo 3 (condicional): require_confirmation recebe uma
        # FUNÇÃO que decide, em tempo de execução, se pede confirmação.
        FunctionTool(contratar_emprestimo, require_confirmation=_precisa_confirmar_contratacao),
        # preferências do cliente (State com prefixo user:) — todo agente tem
        salvar_preferencia,
        listar_preferencias,
        # tools que vêm de FORA, por MCP
        *_toolset_mcp(),
    ],
)
