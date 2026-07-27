"""Tools que mexem em STATE e em MEMÓRIA.

Diferença que confunde todo mundo:

  STATE   = dicionário da conversa atual (Session). Sobrevive entre mensagens.
            Prefixos especiais do ADK:
              "user:"  -> vale para TODAS as sessões daquele usuário
              "app:"   -> vale para o app inteiro
              "temp:"  -> só dura a invocação atual, não é salvo
  MEMÓRIA = busca no histórico de conversas ANTIGAS (MemoryService).
            No ADK se usa a tool nativa `load_memory`.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from mini_banco.tools.comum import ok


def salvar_preferencia(chave: str, valor: str, tool_context: ToolContext) -> dict[str, Any]:
    """Guarda uma preferência do cliente para lembrar nas próximas conversas.

    Use quando o cliente disser algo que vale a pena lembrar depois, por exemplo:
    "me chame de Matheus", "prefiro resposta curta", "meu objetivo é comprar um
    carro", "não me ofereça empréstimo".

    Args:
        chave: Nome curto da preferência, em minúsculas e sem espaço.
            Ex.: "apelido", "estilo_resposta", "objetivo", "nao_ofertar".
        valor: O conteúdo a lembrar. Ex.: "Matheus", "respostas curtas".

    Returns:
        dict confirmando o que foi guardado.
    """
    chave_limpa = (chave or "").strip().lower().replace(" ", "_")
    # O prefixo "user:" faz o ADK persistir isso para TODAS as sessões do usuário.
    tool_context.state[f"user:pref_{chave_limpa}"] = valor
    return ok(mensagem="Preferência guardada.", chave=chave_limpa, valor=valor)


def listar_preferencias(tool_context: ToolContext) -> dict[str, Any]:
    """Lista as preferências que já foram guardadas sobre este cliente.

    Use quando o cliente perguntar "o que você sabe sobre mim?", "o que você
    lembra?" ou antes de personalizar uma resposta.

    Returns:
        dict com todas as preferências salvas.
    """
    prefs = {
        k.replace("user:pref_", ""): v
        for k, v in tool_context.state.to_dict().items()
        if k.startswith("user:pref_")
    }
    return ok(quantidade=len(prefs), preferencias=prefs)
