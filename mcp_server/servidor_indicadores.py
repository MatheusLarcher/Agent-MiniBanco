"""SERVIDOR MCP — indicadores de mercado.

>>> ISTO É "MCP". <<<

MCP (Model Context Protocol) é um padrão aberto para expor tools por fora do
seu código. A ideia: em vez de a tool ser uma função Python dentro do projeto,
ela mora em OUTRO processo (ou em outra empresa/servidor) e o agente conversa
com ele por um protocolo.

Este arquivo NÃO importa nada do Google ADK. É um servidor MCP puro, rodando
por stdio. Quem faz a ponte é o `McpToolset` do ADK
(ver mini_banco/sub_agents/credito_agent.py).

Para testar sozinho:  python -m mcp_server.servidor_indicadores
(ele fica esperando mensagens MCP no stdin — é o comportamento correto)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

servidor = FastMCP("indicadores-mercado")

# Dados fictícios, congelados numa data, só para o exemplo.
INDICADORES = {
    "selic": 10.75,
    "cdi": 10.65,
    "ipca_12m": 4.32,
    "poupanca_ano": 7.55,
    "juro_medio_credito_pessoal_mes": 5.87,
    "juro_medio_consignado_mes": 1.72,
    "referencia": "2026-07-27",
}


@servidor.tool()
def taxa_selic_atual() -> dict:
    """Retorna a taxa Selic e o CDI atuais, em % ao ano.

    Use para explicar ao cliente se a taxa de um empréstimo está cara ou barata
    em relação ao mercado.
    """
    return {
        "selic_ano_percentual": INDICADORES["selic"],
        "cdi_ano_percentual": INDICADORES["cdi"],
        "data_referencia": INDICADORES["referencia"],
    }


@servidor.tool()
def media_mercado_credito(produto: str) -> dict:
    """Retorna o juro MÉDIO cobrado pelo mercado numa linha de crédito, em % ao mês.

    Args:
        produto: "pessoal" ou "consignado".
    """
    chave = (produto or "").strip().lower()
    if "consig" in chave:
        return {
            "produto": "consignado",
            "juro_medio_mes_percentual": INDICADORES["juro_medio_consignado_mes"],
            "data_referencia": INDICADORES["referencia"],
        }
    return {
        "produto": "pessoal",
        "juro_medio_mes_percentual": INDICADORES["juro_medio_credito_pessoal_mes"],
        "data_referencia": INDICADORES["referencia"],
    }


@servidor.tool()
def inflacao_e_poupanca() -> dict:
    """Retorna a inflação (IPCA 12 meses) e o rendimento da poupança, em % ao ano.

    Use para comparar se vale mais a pena guardar dinheiro ou quitar dívida.
    """
    return {
        "ipca_12m_percentual": INDICADORES["ipca_12m"],
        "poupanca_ano_percentual": INDICADORES["poupanca_ano"],
        "data_referencia": INDICADORES["referencia"],
    }


if __name__ == "__main__":
    servidor.run(transport="stdio")
