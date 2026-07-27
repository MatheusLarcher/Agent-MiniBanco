"""Function Tools do Agente de Crédito.

Repare em `contratar_emprestimo`: ela é uma operação de ESCRITA e por isso
é registrada com `FunctionTool(..., require_confirmation=...)` no agente
(ver mini_banco/sub_agents/credito_agent.py).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from google.adk.tools import ToolContext

from banco.db import buscar_um, buscar_varios, executar
from mini_banco.tools.comum import SemContaError, brl, conta_da_sessao, dados_conta, erro, ok

HOJE = date(2026, 7, 27)


def _price(valor: float, taxa_mes: float, parcelas: int) -> float:
    """Tabela Price: parcela fixa de um financiamento."""
    if taxa_mes <= 0:
        return valor / parcelas
    fator = (1 + taxa_mes) ** parcelas
    return valor * (taxa_mes * fator) / (fator - 1)


def consultar_condicoes_credito(tool_context: ToolContext) -> dict[str, Any]:
    """Lista as linhas de crédito do banco e suas condições (taxa, prazo, limites).

    Use quando o cliente perguntar "quais empréstimos vocês têm", "qual a taxa
    de juros", "qual a diferença entre consignado e pessoal", "quanto posso
    pegar emprestado" ou pedir explicação sobre as condições de crédito.
    Também informa quais linhas o score do cliente já aprova.

    Returns:
        dict com a lista de produtos de crédito e se o cliente é elegível a cada um.
    """
    produtos = buscar_varios("SELECT * FROM produtos_credito ORDER BY taxa_mes")

    score = None
    try:
        conta = dados_conta(conta_da_sessao(tool_context))
        score = conta["score"] if conta else None
    except SemContaError:
        pass

    return ok(
        score_do_cliente=score,
        produtos=[
            {
                "codigo": p["codigo"],
                "nome": p["nome"],
                "taxa_mes_percentual": round(p["taxa_mes"] * 100, 2),
                "taxa_ano_percentual": round(((1 + p["taxa_mes"]) ** 12 - 1) * 100, 2),
                "prazo_meses": f"{p['prazo_min']} a {p['prazo_max']}",
                "valor_min": p["valor_min"],
                "valor_max": p["valor_max"],
                "score_minimo": p["score_minimo"],
                "elegivel": None if score is None else score >= p["score_minimo"],
                "descricao": p["descricao"],
            }
            for p in produtos
        ],
    )


def simular_emprestimo(
    valor: float,
    parcelas: int,
    produto: str = "PESSOAL",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Simula um empréstimo e devolve o valor da parcela, o total pago e o CET.

    Use sempre que o cliente pedir uma simulação, perguntar "quanto fica a
    parcela de X reais em Y vezes", "quanto vou pagar de juros" ou quiser
    comparar prazos. Esta tool NÃO contrata nada — é só cálculo, pode rodar
    direto sem pedir confirmação.

    Args:
        valor: Quanto o cliente quer pegar emprestado, em reais (ex.: 10000).
        parcelas: Em quantas vezes quer pagar (ex.: 24).
        produto: Código da linha de crédito. Um de: PESSOAL, CONSIGNADO,
            GARANTIA_VEICULO, CARTAO_PARCELADO. Padrão: PESSOAL.

    Returns:
        dict com valor da parcela, total a pagar, total de juros, taxa e se foi aprovado.
    """
    p = buscar_um("SELECT * FROM produtos_credito WHERE codigo = ?", (produto.strip().upper(),))
    if not p:
        return erro(
            f"Produto '{produto}' não existe.",
            produtos_validos=["PESSOAL", "CONSIGNADO", "GARANTIA_VEICULO", "CARTAO_PARCELADO"],
        )

    valor = float(valor)
    parcelas = int(parcelas)

    problemas = []
    if not (p["valor_min"] <= valor <= p["valor_max"]):
        problemas.append(
            f"Valor fora da faixa: {p['nome']} aceita de {brl(p['valor_min'])} a {brl(p['valor_max'])}."
        )
    if not (p["prazo_min"] <= parcelas <= p["prazo_max"]):
        problemas.append(
            f"Prazo fora da faixa: {p['nome']} aceita de {p['prazo_min']} a {p['prazo_max']} parcelas."
        )

    score = None
    try:
        conta = dados_conta(conta_da_sessao(tool_context))
        if conta:
            score = conta["score"]
            if score < p["score_minimo"]:
                problemas.append(
                    f"Score {score} abaixo do mínimo {p['score_minimo']} para {p['nome']}."
                )
    except SemContaError:
        pass

    parcela = _price(valor, p["taxa_mes"], parcelas)
    total = parcela * parcelas

    resultado = ok(
        aprovado=not problemas,
        restricoes=problemas,
        produto=p["nome"],
        codigo_produto=p["codigo"],
        valor_solicitado=round(valor, 2),
        parcelas=parcelas,
        valor_parcela=round(parcela, 2),
        valor_parcela_formatado=brl(parcela),
        total_a_pagar=round(total, 2),
        total_a_pagar_formatado=brl(total),
        total_juros=round(total - valor, 2),
        total_juros_formatado=brl(total - valor),
        taxa_mes_percentual=round(p["taxa_mes"] * 100, 2),
        taxa_ano_percentual=round(((1 + p["taxa_mes"]) ** 12 - 1) * 100, 2),
        score_do_cliente=score,
    )

    # >>> ISTO É "STATE" <<<  guardamos a última simulação na sessão para que o
    # cliente possa dizer só "quero contratar essa" na mensagem seguinte.
    if tool_context is not None and not problemas:
        tool_context.state["ultima_simulacao"] = {
            "produto": p["codigo"],
            "valor": round(valor, 2),
            "parcelas": parcelas,
            "valor_parcela": round(parcela, 2),
        }

    return resultado


def consultar_emprestimos(tool_context: ToolContext) -> dict[str, Any]:
    """Lista os empréstimos que o cliente já tem no banco (ativos e quitados).

    Use quando o cliente perguntar "tenho algum empréstimo?", "quanto ainda
    devo?", "quantas parcelas faltam", "qual meu saldo devedor" ou pedir o
    histórico de financiamentos.

    Returns:
        dict com cada contrato, parcelas pagas/restantes e saldo devedor total.
    """
    try:
        numero = conta_da_sessao(tool_context)
    except SemContaError as e:
        return erro(str(e))

    linhas = buscar_varios(
        "SELECT * FROM emprestimos WHERE conta_numero = ? ORDER BY status, contratado_em DESC",
        (numero,),
    )

    contratos = []
    devedor_total = 0.0
    for l in linhas:
        restantes = l["parcelas"] - l["parcelas_pagas"]
        saldo = restantes * l["valor_parcela"]
        if l["status"] == "ativo":
            devedor_total += saldo
        contratos.append(
            {
                "id": l["id"],
                "produto": l["produto"],
                "status": l["status"],
                "valor_contratado": round(l["valor_contratado"], 2),
                "taxa_mes_percentual": round(l["taxa_mes"] * 100, 2),
                "parcelas": l["parcelas"],
                "parcelas_pagas": l["parcelas_pagas"],
                "parcelas_restantes": restantes,
                "valor_parcela": round(l["valor_parcela"], 2),
                "valor_parcela_formatado": brl(l["valor_parcela"]),
                "saldo_devedor": round(saldo, 2),
                "saldo_devedor_formatado": brl(saldo),
                "contratado_em": l["contratado_em"],
            }
        )

    return ok(
        conta=numero,
        quantidade=len(contratos),
        saldo_devedor_total=round(devedor_total, 2),
        saldo_devedor_total_formatado=brl(devedor_total),
        emprestimos=contratos,
    )


# ------------------------------------------------------------------
#  OPERAÇÃO DE ESCRITA — exige confirmação (ver credito_agent.py)
# ------------------------------------------------------------------
def contratar_emprestimo(
    valor: float,
    parcelas: int,
    produto: str = "PESSOAL",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """CONTRATA de verdade um empréstimo e credita o dinheiro na conta.

    ATENÇÃO: esta é uma operação que ALTERA dados. Só chame depois de o cliente
    ter visto uma simulação e ter dito claramente que quer contratar.
    O ADK vai pedir a confirmação explícita do cliente antes de executar.

    Args:
        valor: Valor do empréstimo em reais.
        parcelas: Número de parcelas.
        produto: Código da linha de crédito (PESSOAL, CONSIGNADO,
            GARANTIA_VEICULO, CARTAO_PARCELADO).

    Returns:
        dict com o contrato criado e o novo saldo da conta.
    """
    try:
        numero = conta_da_sessao(tool_context)
    except SemContaError as e:
        return erro(str(e))

    simulacao = simular_emprestimo(valor, parcelas, produto, tool_context)
    if simulacao["status"] == "erro":
        return simulacao
    if not simulacao["aprovado"]:
        return erro("Contratação recusada.", restricoes=simulacao["restricoes"])

    p = buscar_um("SELECT * FROM produtos_credito WHERE codigo = ?", (produto.strip().upper(),))
    quantos = buscar_um("SELECT COUNT(*) AS n FROM emprestimos")["n"]
    novo_id = f"EMP{quantos + 1:03d}"

    executar(
        "INSERT INTO emprestimos VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            novo_id,
            numero,
            p["nome"],
            round(float(valor), 2),
            p["taxa_mes"],
            int(parcelas),
            0,
            simulacao["valor_parcela"],
            HOJE.isoformat(),
            "ativo",
        ),
    )
    executar("UPDATE contas SET saldo = saldo + ? WHERE numero = ?", (round(float(valor), 2), numero))
    executar(
        "INSERT INTO transacoes (conta_numero, data, descricao, categoria, tipo, valor)"
        " VALUES (?,?,?,?,?,?)",
        (numero, HOJE.isoformat(), f"Crédito de empréstimo {novo_id}", "emprestimo", "credito",
         round(float(valor), 2)),
    )

    conta = dados_conta(numero)
    if tool_context is not None:
        # State do ADK não tem .pop(); para "limpar" a chave, gravamos None.
        tool_context.state["ultima_simulacao"] = None

    return ok(
        mensagem="Empréstimo contratado com sucesso.",
        contrato=novo_id,
        produto=p["nome"],
        valor=round(float(valor), 2),
        parcelas=int(parcelas),
        valor_parcela=simulacao["valor_parcela"],
        valor_parcela_formatado=simulacao["valor_parcela_formatado"],
        primeiro_vencimento="2026-08-27",
        novo_saldo=round(conta["saldo"], 2),
        novo_saldo_formatado=brl(conta["saldo"]),
    )
