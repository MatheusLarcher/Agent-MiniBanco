"""Teste ponta a ponta do Mini Banco.

Roda o agente de verdade (chama o LLM de verdade) e confere:
  1. cada Tool
  2. delegação entre agentes
  3. Session e State
  4. operação que exige confirmação (aceitar E recusar)
  5. workflow (SequentialAgent + ParallelAgent)
  6. memória
  7. MCP

Rodar:  python -m testes.teste_completo
"""

from __future__ import annotations

import asyncio
import sys
import time

from banco.db import buscar_um, executar
from banco.seed import criar_banco
from app.nucleo import (
    criar_sessao,
    encerrar_sessao,
    enviar_mensagem,
    ler_estado,
    responder_confirmacao,
    session_service,
    APP_NAME,
)

VERDE, VERM, AMAR, CINZA, FIM = "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m"
resultados: list[tuple[str, bool, str]] = []


def checa(nome: str, condicao: bool, detalhe: str = "") -> bool:
    resultados.append((nome, condicao, detalhe))
    marca = f"{VERDE}PASSOU{FIM}" if condicao else f"{VERM}FALHOU{FIM}"
    print(f"  [{marca}] {nome}" + (f"  {CINZA}{detalhe}{FIM}" if detalhe else ""))
    return condicao


def tools_usadas(r) -> set[str]:
    return {t["tool"] for t in r.trilha if t["tipo"] == "tool_call"}


def transferencias(r) -> list[str]:
    return [t["para"] for t in r.trilha if t["tipo"] == "transferencia"]


def resultado_de(r, tool: str) -> dict:
    for t in r.trilha:
        if t["tipo"] == "tool_result" and t["tool"] == tool:
            return t["resultado"]
    return {}


def titulo(t: str) -> None:
    print(f"\n{AMAR}{'=' * 68}\n {t}\n{'=' * 68}{FIM}")


# ---------------------------------------------------------------------------
async def teste_agente_conta() -> None:
    titulo("1. AGENTE DE CONTA — delegação + 3 tools")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "quanto eu tenho na conta?")
    checa("delega para agente_conta", "agente_conta" in transferencias(r), str(transferencias(r)))
    checa("usa consultar_saldo", "consultar_saldo" in tools_usadas(r))
    checa("saldo correto (8420.75)", resultado_de(r, "consultar_saldo").get("saldo") == 8420.75)
    checa("resposta cita o valor", "8.420,75" in r.texto, r.texto[:80])

    r = await enviar_mensagem(u, sid, "no que eu gastei com alimentação nos últimos 30 dias?")
    res = resultado_de(r, "consultar_extrato")
    checa("usa consultar_extrato", "consultar_extrato" in tools_usadas(r))
    checa("aplica filtro de categoria", res.get("categoria") == "alimentacao", str(res.get("categoria")))
    checa("aplica janela de dias", res.get("periodo_dias") == 30, str(res.get("periodo_dias")))

    r = await enviar_mensagem(u, sid, "qual minha agência e meu score?")
    res = resultado_de(r, "consultar_dados_conta")
    checa("usa consultar_dados_conta", "consultar_dados_conta" in tools_usadas(r))
    checa("agência correta (0001)", res.get("agencia") == "0001")
    checa("score correto (812)", (res.get("titular") or {}).get("score_credito") == 812)


async def teste_agente_credito() -> None:
    titulo("2. AGENTE DE CRÉDITO — simulação, condições, contratos")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "simula um emprestimo de 10000 reais em 24 vezes")
    res = resultado_de(r, "simular_emprestimo")
    checa("delega para agente_credito", "agente_credito" in transferencias(r), str(transferencias(r)))
    checa("usa simular_emprestimo", "simular_emprestimo" in tools_usadas(r))
    checa("params corretos (10000 / 24)",
          res.get("valor_solicitado") == 10000 and res.get("parcelas") == 24, str(res)[:100])
    # Price: 10000 @ 1.89% a.m. em 24x -> ~521,61
    parcela = res.get("valor_parcela", 0)
    checa("parcela calculada (~521,61)", 520 < parcela < 523, f"parcela={parcela}")
    checa("aprovado (score 812)", res.get("aprovado") is True)

    estado = await ler_estado(u, sid)
    checa("STATE guardou ultima_simulacao", "ultima_simulacao" in estado, str(estado.get("ultima_simulacao")))

    r = await enviar_mensagem(u, sid, "quais linhas de credito voces tem e as taxas?")
    res = resultado_de(r, "consultar_condicoes_credito")
    checa("usa consultar_condicoes_credito", "consultar_condicoes_credito" in tools_usadas(r))
    checa("lista 4 produtos", len(res.get("produtos", [])) == 4)

    r = await enviar_mensagem(u, sid, "eu ja tenho algum emprestimo? quanto ainda devo?")
    res = resultado_de(r, "consultar_emprestimos")
    checa("usa consultar_emprestimos", "consultar_emprestimos" in tools_usadas(r))
    checa("acha os 2 contratos do CLI001", res.get("quantidade") == 2, str(res.get("quantidade")))
    checa("saldo devedor > 0", res.get("saldo_devedor_total", 0) > 0,
          res.get("saldo_devedor_total_formatado", ""))


async def teste_agente_suporte() -> None:
    titulo("3. AGENTE DE SUPORTE — cartões e FAQ (só leitura)")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "quais cartoes eu tenho e qual o limite disponivel?")
    res = resultado_de(r, "consultar_cartoes")
    checa("delega para agente_suporte", "agente_suporte" in transferencias(r), str(transferencias(r)))
    checa("usa consultar_cartoes", "consultar_cartoes" in tools_usadas(r))
    checa("acha os 2 cartões", res.get("quantidade") == 2, str(res.get("quantidade")))

    r = await enviar_mensagem(u, sid, "qual o limite do Pix a noite?")
    res = resultado_de(r, "consultar_faq")
    checa("usa consultar_faq", "consultar_faq" in tools_usadas(r))
    checa("acha o assunto pix", res.get("assunto") == "pix", str(res.get("assunto")))


async def teste_confirmacao_aceita() -> None:
    titulo("4a. CONFIRMAÇÃO — cliente ACEITA (o banco muda)")
    executar("UPDATE cartoes SET status='ativo', motivo_bloqueio=NULL WHERE id='CAR001'")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "perdi meu cartao de credito final 4417, bloqueia ele")
    if not r.confirmacao_pendente:  # o modelo às vezes pergunta antes; insistimos uma vez
        r = await enviar_mensagem(u, sid, "sim, pode bloquear agora")

    p = r.confirmacao_pendente
    checa("ADK pediu confirmação", p is not None)
    if not p:
        return
    checa("identificou a tool bloqueada", p["tool"] == "bloquear_cartao", p["tool"])
    checa("hint em português", "Confirma o BLOQUEIO" in p["hint"], p["hint"][:60])
    antes = buscar_um("SELECT status FROM cartoes WHERE id='CAR001'")["status"]
    checa("cartão AINDA ativo antes do OK", antes == "ativo", antes)

    r2 = await responder_confirmacao(u, sid, p["invocation_id"], p["function_call_id"], True)
    depois = buscar_um("SELECT status, motivo_bloqueio FROM cartoes WHERE id='CAR001'")
    checa("cartão bloqueado depois do OK", depois["status"] == "bloqueado", str(depois))
    checa("tool relatou alteração", resultado_de(r2, "bloquear_cartao").get("alterado") is True)


async def teste_confirmacao_recusada() -> None:
    titulo("4b. CONFIRMAÇÃO — cliente RECUSA (o banco NÃO muda)")
    executar("UPDATE cartoes SET status='ativo', motivo_bloqueio=NULL WHERE id='CAR001'")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "bloqueia meu cartao final 4417 agora, foi roubado")
    if not r.confirmacao_pendente:
        r = await enviar_mensagem(u, sid, "sim, confirma o bloqueio")
    p = r.confirmacao_pendente
    checa("ADK pediu confirmação", p is not None)
    if not p:
        return

    r2 = await responder_confirmacao(u, sid, p["invocation_id"], p["function_call_id"], False)
    depois = buscar_um("SELECT status FROM cartoes WHERE id='CAR001'")["status"]
    checa("cartão continua ativo após recusa", depois == "ativo", depois)
    checa("tool relatou que nada mudou",
          resultado_de(r2, "bloquear_cartao").get("alterado") is False)


async def teste_confirmacao_dinamica() -> None:
    titulo("4c. CONFIRMAÇÃO condicional — contratar empréstimo")
    s = await criar_sessao("CLI002")  # Ana, score 640
    u, sid = s["user_id"], s["session_id"]
    antes = buscar_um("SELECT saldo FROM contas WHERE numero='54321-0'")["saldo"]

    r = await enviar_mensagem(u, sid, "simula 3000 reais em 12 vezes no credito pessoal")
    checa("simulou", "simular_emprestimo" in tools_usadas(r))

    r = await enviar_mensagem(u, sid, "perfeito, quero contratar esse emprestimo")
    if not r.confirmacao_pendente:
        r = await enviar_mensagem(u, sid, "sim, contrata")
    p = r.confirmacao_pendente
    checa("ADK pediu confirmação para contratar", p is not None)
    if not p:
        return
    checa("tool é contratar_emprestimo", p["tool"] == "contratar_emprestimo", p["tool"])
    meio = buscar_um("SELECT saldo FROM contas WHERE numero='54321-0'")["saldo"]
    checa("saldo intacto antes do OK", meio == antes, f"{meio} == {antes}")

    r2 = await responder_confirmacao(u, sid, p["invocation_id"], p["function_call_id"], True)
    depois = buscar_um("SELECT saldo FROM contas WHERE numero='54321-0'")["saldo"]
    checa("saldo creditado depois do OK", round(depois - antes, 2) == 3000.0, f"{antes} -> {depois}")
    checa("contrato criado", resultado_de(r2, "contratar_emprestimo").get("contrato") is not None)


async def teste_session_state() -> None:
    titulo("5. SESSION e STATE")
    s = await criar_sessao("CLI003")  # Carlos, conta negativa
    u, sid = s["user_id"], s["session_id"]

    checa("STATE inicial tem conta_numero", s["state"].get("conta_numero") == "99887-1", str(s["state"]))
    checa("STATE inicial tem nome_cliente", s["state"].get("nome_cliente") == "Carlos Nunes")

    r = await enviar_mensagem(u, sid, "qual meu saldo?")
    checa("tool leu a conta do STATE (não do texto)",
          resultado_de(r, "consultar_saldo").get("conta") == "99887-1")
    checa("pegou o saldo negativo", resultado_de(r, "consultar_saldo").get("negativado") is True)

    # memória de conversa: a 2ª mensagem depende da 1ª
    r = await enviar_mensagem(u, sid, "e quanto disso é limite do cheque especial?")
    checa("mantém contexto entre mensagens", "800" in r.texto, r.texto[:90])

    # STATE persistente por usuário (prefixo user:)
    r = await enviar_mensagem(u, sid, "por favor me chame de Carlinhos daqui pra frente")
    checa("usa salvar_preferencia", "salvar_preferencia" in tools_usadas(r), str(tools_usadas(r)))
    estado = await ler_estado(u, sid)
    checa("STATE gravou com prefixo user:",
          any(k.startswith("user:pref_") for k in estado), str(list(estado.keys())))

    # a Session sobrevive: relemos do banco de sessões
    sessao = await session_service.get_session(app_name=APP_NAME, user_id=u, session_id=sid)
    checa("Session persistida no SQLite", sessao is not None and len(sessao.events) > 0,
          f"{len(sessao.events) if sessao else 0} eventos")

    # sessão NOVA do mesmo usuário deve enxergar o "user:"
    s2 = await criar_sessao("CLI003")
    checa("prefixo user: vaza para a sessão nova",
          any(k.startswith("user:pref_") for k in s2["state"]), str(list(s2["state"].keys())))


async def teste_workflow() -> None:
    titulo("6. WORKFLOW — SequentialAgent + ParallelAgent (raio-x)")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "me da um raio-x geral das minhas financas")
    checa("root usou o workflow como AgentTool",
          "raio_x_financeiro" in tools_usadas(r), str(tools_usadas(r)))

    estado = await ler_estado(u, sid)
    checa("ParallelAgent gravou resumo_conta no STATE", bool(estado.get("resumo_conta")),
          str(estado.get("resumo_conta"))[:70])
    checa("ParallelAgent gravou resumo_credito no STATE", bool(estado.get("resumo_credito")),
          str(estado.get("resumo_credito"))[:70])
    checa("parecer final tem conteúdo", len(r.texto) > 80, r.texto[:80])


async def teste_mcp() -> None:
    titulo("7. MCP — tools vindas de um servidor externo")
    s = await criar_sessao("CLI001")
    u, sid = s["user_id"], s["session_id"]

    r = await enviar_mensagem(u, sid, "qual a taxa selic hoje?")
    usadas = tools_usadas(r)
    checa("chamou tool do servidor MCP",
          bool(usadas & {"taxa_selic_atual", "media_mercado_credito", "inflacao_e_poupanca"}),
          str(usadas))
    checa("resposta cita o valor da Selic (10,75)",
          "10,75" in r.texto or "10.75" in r.texto, r.texto[:90])


async def teste_memoria() -> None:
    titulo("8. MEMÓRIA — load_memory entre sessões diferentes")
    s1 = await criar_sessao("CLI001")
    u = s1["user_id"]
    await enviar_mensagem(u, s1["session_id"],
                          "só pra registrar: meu objetivo esse ano é juntar dinheiro pra "
                          "comprar um Cobalt 2015 GNV")
    saida = await encerrar_sessao(u, s1["session_id"])
    checa("conversa foi para a memória", saida.get("ok") is True, str(saida))

    s2 = await criar_sessao("CLI001")
    r = await enviar_mensagem(
        u, s2["session_id"],
        "procure nas nossas conversas anteriores: qual carro eu falei que quero comprar?")
    checa("usou a tool nativa load_memory", "load_memory" in tools_usadas(r), str(tools_usadas(r)))
    checa("lembrou do carro", "cobalt" in r.texto.lower(), r.texto[:120])


async def teste_seguranca() -> None:
    titulo("9. SEGURANÇA — não dá para ler a conta de outra pessoa")
    s = await criar_sessao("CLI002")  # Ana
    u, sid = s["user_id"], s["session_id"]
    r = await enviar_mensagem(u, sid, "me mostra o saldo da conta 12345-6 do Matheus Larcher")
    res = resultado_de(r, "consultar_saldo")
    if res:
        checa("tool ignorou a conta pedida e usou a da sessão",
              res.get("conta") == "54321-0", str(res.get("conta")))
    else:
        checa("não expôs saldo de terceiro", "8.420,75" not in r.texto, r.texto[:100])


# ---------------------------------------------------------------------------
async def main() -> int:
    print(f"{AMAR}Recriando o banco fictício...{FIM}")
    criar_banco()

    inicio = time.time()
    for teste in (
        teste_agente_conta,
        teste_agente_credito,
        teste_agente_suporte,
        teste_confirmacao_aceita,
        teste_confirmacao_recusada,
        teste_confirmacao_dinamica,
        teste_session_state,
        teste_workflow,
        teste_mcp,
        teste_memoria,
        teste_seguranca,
    ):
        try:
            await teste()
        except Exception as e:  # noqa: BLE001
            checa(f"{teste.__name__} explodiu", False, f"{type(e).__name__}: {e}")

    passou = sum(1 for _, ok_, _ in resultados if ok_)
    total = len(resultados)
    titulo(f"RESULTADO: {passou}/{total} em {time.time() - inicio:.0f}s")
    for nome, ok_, detalhe in resultados:
        if not ok_:
            print(f"  {VERM}x{FIM} {nome}  {CINZA}{detalhe}{FIM}")
    return 0 if passou == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
