"""Limitador de chamadas ao LLM (rate limit do free tier).

>>> ISTO É UM "CALLBACK" DO ADK. <<<

Todo LlmAgent aceita `before_model_callback=`: uma função que o ADK chama
IMEDIATAMENTE ANTES de mandar o request para o LLM. Dá para inspecionar o
prompt, alterá-lo, ou — como aqui — segurar a chamada.

Por que isso existe neste projeto:
  O free tier do Gemini (AI Studio) dá poucas requisições por minuto
  (5/min no gemini-3.6-flash, 15/min no gemini-3.5-flash-lite). Num app
  multi-agent, UMA mensagem do cliente gasta 3 ou 4 chamadas: o root decide,
  o especialista pensa, chama a tool, e pensa de novo com o resultado.
  Estourar a cota não só derruba a resposta: o ADK repete o nó, e um nó
  repetido pode emitir um SEGUNDO pedido de confirmação, deixando o primeiro
  órfão. Segurar antes é muito melhor do que remediar depois.

Desligue com LLM_MAX_RPM=0 no .env (conta paga não precisa disto).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque

MAX_RPM = int(os.getenv("LLM_MAX_RPM", "12") or 0)
JANELA = 60.0

_marcas: deque[float] = deque()
_trava = asyncio.Lock()


async def limitar_rpm(callback_context, llm_request) -> None:
    """Segura a chamada se já batemos o teto de requisições no último minuto.

    Devolver None = "pode seguir e chamar o LLM".
    (Se devolvesse um LlmResponse, o ADK usaria ele e NÃO chamaria o modelo.)
    """
    if MAX_RPM <= 0:
        return None

    while True:
        async with _trava:
            agora = time.monotonic()
            while _marcas and agora - _marcas[0] >= JANELA:
                _marcas.popleft()
            if len(_marcas) < MAX_RPM:
                _marcas.append(agora)
                return None
            espera = JANELA - (agora - _marcas[0]) + 0.2
        await asyncio.sleep(espera)
