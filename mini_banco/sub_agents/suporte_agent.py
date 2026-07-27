"""Agente de Suporte (cartões + dúvidas gerais)."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from mini_banco import prompts
from mini_banco.config import MODELO, RETRY
from mini_banco.limitador import limitar_rpm
from mini_banco.tools.suporte_tools import (
    bloquear_cartao,
    consultar_cartoes,
    consultar_faq,
    desbloquear_cartao,
)
from mini_banco.tools.memoria_tools import listar_preferencias, salvar_preferencia

agente_suporte = LlmAgent(
    name="agente_suporte",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    description=(
        "Especialista em suporte: status/limite de cartão, bloqueio e desbloqueio de "
        "cartão, perda, roubo, fraude e dúvidas gerais do banco (Pix, tarifas, "
        "fatura, senha, segunda via)."
    ),
    instruction=prompts.SUPORTE,
    tools=[
        # leitura -> direto
        consultar_cartoes,
        consultar_faq,
        # ESCRITA, estilo 1 (manual): a própria função chama
        # tool_context.request_confirmation() com um texto nosso em português.
        # Por isso ela entra aqui como função crua, sem require_confirmation.
        bloquear_cartao,
        # ESCRITA, estilo 2 (automático): o ADK monta o pedido de confirmação
        # sozinho, sem uma linha de código dentro da função.
        FunctionTool(desbloquear_cartao, require_confirmation=True),
        # preferências do cliente (State com prefixo user:) — todo agente tem
        salvar_preferencia,
        listar_preferencias,
    ],
)
