"""Configuração do modelo de LLM.

>>> ESTE É O ÚNICO ARQUIVO QUE VOCÊ MEXE PARA TROCAR O LLM. <<<

O ADK aceita duas formas no campo `model=` de um LlmAgent:
  1. uma STRING  -> modelo nativo do Google (ex.: "gemini-2.5-flash")
  2. um OBJETO   -> LiteLlm(...) para qualquer outro provider (OpenAI, DeepSeek,
     Anthropic, Ollama...). LiteLlm faz parte do ADK (google.adk.models.lite_llm).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

_PADRAO = {
    # flash-lite tem cota MUITO maior no free tier do AI Studio.
    # O gemini-3.6-flash é melhor, mas o gratuito dá só 5 req/min — e uma única
    # mensagem num app multi-agent gasta 3 ou 4 chamadas. Se você tiver conta
    # paga, troque para "gemini-3.6-flash" no .env.
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}

NOME_MODELO = os.getenv("LLM_MODEL", "").strip() or _PADRAO.get(PROVIDER, "gemini-3.5-flash-lite")


def get_model():
    """Devolve o que vai no campo `model=` do LlmAgent."""
    if PROVIDER == "gemini":
        # Gemini é nativo: basta a string. O ADK lê GOOGLE_API_KEY do ambiente.
        return NOME_MODELO

    # Qualquer outro provider passa pelo LiteLLM (também nativo do ADK).
    from google.adk.models.lite_llm import LiteLlm

    if PROVIDER == "deepseek":
        return LiteLlm(model=f"deepseek/{NOME_MODELO}")
    return LiteLlm(model=f"openai/{NOME_MODELO}")


MODELO = get_model()

DESCRICAO_MODELO = f"{PROVIDER}:{NOME_MODELO}"


# ---------------------------------------------------------------------------
# >>> RETRY nativo do ADK <<<
# Todo LlmAgent aceita `retry_config=`. Quando a chamada ao LLM falha (429 de
# cota, instabilidade da API), o ADK espera e tenta de novo sozinho, com
# backoff exponencial — sem isso, o free tier do Gemini derruba a conversa no
# meio. Aplicado a todos os agentes do projeto.
# ---------------------------------------------------------------------------
from google.adk.workflow._retry_config import RetryConfig  # noqa: E402

RETRY = RetryConfig(
    max_attempts=5,
    initial_delay=8.0,     # o Gemini free costuma pedir ~50s; começamos alto
    max_delay=70.0,
    backoff_factor=2.0,
    jitter=0.3,
    # SÓ erro transitório: cota estourada (429) e falha do servidor (5xx).
    # Não ponha `ClientError` genérico aqui: ele cobre 400/403 também, que nunca
    # vão passar na segunda tentativa — só faz o nó rodar de novo à toa e pode
    # deixar pedido de confirmação órfão no meio do caminho.
    exceptions=["_ResourceExhaustedError", "ServerError"],
)
