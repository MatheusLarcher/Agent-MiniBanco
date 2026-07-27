"""Interface de chat (FastAPI).

Esta camada NÃO é ADK: é só uma casca HTTP em volta do `app/nucleo.py`.
Ela existe para você ver, na tela, o que o ADK está fazendo por baixo:
qual agente respondeu, qual tool rodou e o que tem dentro do State.

Rodar:  python -m app.server      (http://localhost:8010)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from banco.db import banco_existe, buscar_varios
from mini_banco.config import DESCRICAO_MODELO
from app.nucleo import (
    criar_sessao,
    encerrar_sessao,
    enviar_mensagem,
    ler_estado,
    responder_confirmacao,
)

ESTATICO = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Mini Banco com IA — Google ADK")


class NovaSessao(BaseModel):
    cliente_id: str = "CLI001"


class Mensagem(BaseModel):
    user_id: str
    session_id: str
    texto: str


class Confirmacao(BaseModel):
    user_id: str
    session_id: str
    invocation_id: str
    function_call_id: str
    confirmado: bool


@app.get("/")
def home() -> FileResponse:
    return FileResponse(ESTATICO / "index.html")


@app.get("/api/clientes")
def clientes() -> dict[str, Any]:
    if not banco_existe():
        return {"erro": "Banco não criado. Rode: python -m banco.seed"}
    linhas = buscar_varios(
        "SELECT cl.id, cl.nome, cl.score, c.numero, c.saldo FROM clientes cl "
        "JOIN contas c ON c.cliente_id = cl.id ORDER BY cl.id"
    )
    return {"modelo": DESCRICAO_MODELO, "clientes": linhas}


@app.post("/api/sessao")
async def nova_sessao(body: NovaSessao) -> dict[str, Any]:
    return await criar_sessao(body.cliente_id)


@app.post("/api/mensagem")
async def mensagem(body: Mensagem) -> dict[str, Any]:
    r = await enviar_mensagem(body.user_id, body.session_id, body.texto)
    return r.to_dict() | {"state": await ler_estado(body.user_id, body.session_id)}


@app.post("/api/confirmar")
async def confirmar(body: Confirmacao) -> dict[str, Any]:
    r = await responder_confirmacao(
        body.user_id,
        body.session_id,
        body.invocation_id,
        body.function_call_id,
        body.confirmado,
    )
    return r.to_dict() | {"state": await ler_estado(body.user_id, body.session_id)}


@app.get("/api/estado")
async def estado(user_id: str, session_id: str) -> dict[str, Any]:
    return await ler_estado(user_id, session_id)


@app.post("/api/encerrar")
async def encerrar(body: Mensagem) -> dict[str, Any]:
    return await encerrar_sessao(body.user_id, body.session_id)


app.mount("/static", StaticFiles(directory=ESTATICO), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
