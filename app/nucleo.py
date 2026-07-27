"""NÚCLEO: liga o agente ao Runner, à Session, ao State e à Memória.

>>> AQUI ESTÃO Runner, Session, State e Memory. <<<

Fluxo do ADK, em uma frase:
    Runner recebe a mensagem -> carrega a Session (com o State) ->
    roda o Agent -> o Agent chama Tools -> tudo vira Event ->
    o Runner salva os Events e o State de volta na Session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from banco.db import buscar_um
from mini_banco.agent import root_agent

APP_NAME = "mini_banco"
RAIZ = Path(__file__).resolve().parent.parent
BANCO_SESSOES = RAIZ / "data" / "sessoes.db"

# Nome interno que o ADK usa para a "tool sintética" de confirmação.
TOOL_CONFIRMACAO = "adk_request_confirmation"

# --- SESSION SERVICE -------------------------------------------------------
# InMemorySessionService() perde tudo ao reiniciar. Usamos o de banco para
# provar que Session e State realmente persistem.
BANCO_SESSOES.parent.mkdir(exist_ok=True)
session_service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{BANCO_SESSOES.as_posix()}")

# --- MEMORY SERVICE --------------------------------------------------------
# Guarda conversas ENCERRADAS para a tool `load_memory` pesquisar depois.
memory_service = InMemoryMemoryService()

# --- RUNNER ----------------------------------------------------------------
runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
    memory_service=memory_service,
)


# ---------------------------------------------------------------------------
#  Sessão
# ---------------------------------------------------------------------------
async def criar_sessao(cliente_id: str = "CLI001") -> dict[str, Any]:
    """Cria uma Session já com o STATE inicial (o "login" do cliente)."""
    linha = buscar_um(
        "SELECT cl.id, cl.nome, c.numero FROM clientes cl "
        "JOIN contas c ON c.cliente_id = cl.id WHERE cl.id = ?",
        (cliente_id,),
    )
    if not linha:
        raise ValueError(f"Cliente {cliente_id} não existe.")

    # >>> ISTO É "STATE" <<< dicionário inicial da sessão.
    estado_inicial = {
        "cliente_id": linha["id"],
        "nome_cliente": linha["nome"],
        "conta_numero": linha["numero"],
    }

    sessao = await session_service.create_session(
        app_name=APP_NAME,
        user_id=linha["id"],      # o user_id agrupa as sessões do mesmo cliente
        state=estado_inicial,
    )
    return {
        "session_id": sessao.id,
        "user_id": linha["id"],
        "nome": linha["nome"],
        "conta": linha["numero"],
        "state": dict(sessao.state),
    }


async def ler_estado(user_id: str, session_id: str) -> dict[str, Any]:
    sessao = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    return dict(sessao.state) if sessao else {}


async def encerrar_sessao(user_id: str, session_id: str) -> dict[str, Any]:
    """Joga a conversa inteira na MEMÓRIA de longo prazo."""
    sessao = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not sessao:
        return {"ok": False, "erro": "sessão não encontrada"}
    await memory_service.add_session_to_memory(sessao)
    return {"ok": True, "eventos_memorizados": len(sessao.events)}


# ---------------------------------------------------------------------------
#  Conversa
# ---------------------------------------------------------------------------
@dataclass
class Resposta:
    texto: str = ""
    agente_final: str = ""
    trilha: list[dict[str, Any]] = field(default_factory=list)
    confirmacao_pendente: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "agente_final": self.agente_final,
            "trilha": self.trilha,
            "confirmacao_pendente": self.confirmacao_pendente,
        }


async def enviar_mensagem(user_id: str, session_id: str, texto: str) -> Resposta:
    """Manda uma mensagem de texto normal para o agente."""
    conteudo = types.Content(role="user", parts=[types.Part(text=texto)])
    r = await _rodar(user_id, session_id, conteudo)
    r.confirmacao_pendente = await _confirmacao_pendente(user_id, session_id)
    return r


async def _confirmacao_pendente(user_id: str, session_id: str) -> dict[str, Any] | None:
    """Descobre se há um pedido de confirmação ABERTO, lendo a Session persistida.

    Por que não usar o que passou no stream: se o ADK precisar repetir um nó
    (retry por 429, por exemplo), a tentativa abortada pode deixar no stream um
    pedido de confirmação que nunca virou evento válido na sessão. Responder a
    esse id órfão dá `ValueError: Tool 'x' does not require confirmation`.
    A Session gravada é a fonte de verdade — é assim que o próprio `adk run` faz.
    """
    sessao = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not sessao:
        return None

    for evento in reversed(sessao.events):
        if not evento.long_running_tool_ids:
            continue
        for fc in evento.get_function_calls() or []:
            if fc.name == TOOL_CONFIRMACAO and fc.id in evento.long_running_tool_ids:
                return {
                    "function_call_id": fc.id,
                    "invocation_id": evento.invocation_id,
                    "agente": evento.author or "",
                    **_detalhe_confirmacao(fc),
                }
        return None  # o interrupt mais recente não é de confirmação
    return None


async def responder_confirmacao(
    user_id: str,
    session_id: str,
    invocation_id: str,
    function_call_id: str,
    confirmado: bool,
    payload: dict[str, Any] | None = None,
) -> Resposta:
    """Responde ao pedido de confirmação e RETOMA a mesma invocação.

    Em vez de mandar texto, mandamos um FunctionResponse com o id do pedido de
    confirmação. O ADK então executa (ou cancela) a tool que estava esperando.
    """
    resposta: dict[str, Any] = {"confirmed": bool(confirmado)}
    if payload is not None:
        resposta["payload"] = payload

    conteudo = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=function_call_id,
                    name=TOOL_CONFIRMACAO,
                    response=resposta,
                )
            )
        ],
    )
    r = await _rodar(user_id, session_id, conteudo, invocation_id=invocation_id)
    # pode encadear: uma confirmação liberar outra operação que também precisa de OK
    r.confirmacao_pendente = await _confirmacao_pendente(user_id, session_id)
    return r


async def _rodar(
    user_id: str,
    session_id: str,
    conteudo: types.Content,
    invocation_id: str | None = None,
) -> Resposta:
    """Consome o stream de Events do Runner e monta a resposta para a UI."""
    out = Resposta()
    textos: list[str] = []

    async for evento in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=conteudo,
        invocation_id=invocation_id,
    ):
        autor = evento.author or ""

        # 1) chamadas de tool e transferências entre agentes
        for fc in evento.get_function_calls() or []:
            if fc.name == "transfer_to_agent":
                out.trilha.append(
                    {
                        "tipo": "transferencia",
                        "de": autor,
                        "para": (fc.args or {}).get("agent_name", "?"),
                    }
                )
            elif fc.name == TOOL_CONFIRMACAO:
                pass  # tratado depois, lendo a Session persistida
            else:
                out.trilha.append(
                    {"tipo": "tool_call", "agente": autor, "tool": fc.name, "args": fc.args or {}}
                )

        # 2) resultados das tools
        for fr in evento.get_function_responses() or []:
            if fr.name in (TOOL_CONFIRMACAO, "transfer_to_agent"):
                continue
            out.trilha.append(
                {
                    "tipo": "tool_result",
                    "agente": autor,
                    "tool": fr.name,
                    "resultado": _json_seguro(fr.response),
                }
            )

        # 3) texto final do agente
        if evento.is_final_response() and evento.content and evento.content.parts:
            pedaco = "".join(p.text for p in evento.content.parts if p.text)
            if pedaco.strip():
                textos.append(pedaco.strip())
                out.agente_final = autor

    out.texto = "\n\n".join(textos)
    return out


def _json_seguro(valor: Any) -> Any:
    """Converte o retorno de uma tool para algo que o FastAPI consiga serializar.

    Nem toda tool devolve dict puro: a `load_memory` do ADK, por exemplo,
    devolve um objeto Pydantic (LoadMemoryResponse).
    """
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, dict):
        return {str(k): _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_json_seguro(v) for v in valor]
    if hasattr(valor, "model_dump"):  # objetos Pydantic (ADK e google.genai)
        try:
            return _json_seguro(valor.model_dump(mode="json", exclude_none=True))
        except Exception:  # noqa: BLE001
            pass
    return str(valor)


def _detalhe_confirmacao(fc: Any) -> dict[str, Any]:
    """Extrai da chamada de confirmação qual tool e quais argumentos estão em espera."""
    args = fc.args or {}
    bruto = args.get("originalFunctionCall") or args.get("original_function_call") or {}
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except (json.JSONDecodeError, ValueError):
            bruto = {}
    hint = args.get("toolConfirmation", {}) or args.get("tool_confirmation", {}) or {}
    if isinstance(hint, str):
        try:
            hint = json.loads(hint)
        except (json.JSONDecodeError, ValueError):
            hint = {}

    return {
        "tool": bruto.get("name", "operação sensível"),
        "args": bruto.get("args", {}),
        "hint": hint.get("hint") or "Esta operação altera dados. Confirma?",
        "args_brutos": args,
    }
