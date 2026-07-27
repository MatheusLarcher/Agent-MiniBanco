"""Function Tools do Agente de Conta.

>>> ISTO É "TOOL". <<<

No ADK, uma Tool pode ser simplesmente uma função Python. O ADK lê
automaticamente:
  - o NOME da função      -> vira o nome da tool que o LLM enxerga
  - a DOCSTRING           -> vira a descrição (é assim que o LLM decide quando usar)
  - os TYPE HINTS         -> viram o schema JSON dos parâmetros

Por isso a docstring precisa ser boa: ela é literalmente o "manual" que o
modelo lê antes de escolher a tool.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from banco.db import buscar_varios
from mini_banco.tools.comum import SemContaError, brl, dados_conta, erro, ok


def consultar_saldo(tool_context: ToolContext) -> dict[str, Any]:
    """Consulta o saldo atual da conta do cliente autenticado nesta conversa.

    Use sempre que o cliente perguntar quanto tem na conta, quanto sobrou,
    se está no negativo, quanto pode gastar ou qual o limite do cheque especial.
    Não recebe parâmetros: a conta vem da sessão, nunca do texto do cliente.

    Returns:
        dict com saldo, limite do cheque especial e saldo disponível total.
    """
    try:
        numero = _conta(tool_context)
    except SemContaError as e:
        return erro(str(e))

    conta = dados_conta(numero)
    if not conta:
        return erro(f"Conta {numero} não encontrada.")

    disponivel = conta["saldo"] + conta["limite_especial"]
    return ok(
        conta=numero,
        titular=conta["nome"],
        saldo=round(conta["saldo"], 2),
        saldo_formatado=brl(conta["saldo"]),
        limite_cheque_especial=round(conta["limite_especial"], 2),
        saldo_disponivel=round(disponivel, 2),
        saldo_disponivel_formatado=brl(disponivel),
        negativado=conta["saldo"] < 0,
    )


def consultar_extrato(
    dias: int = 30,
    categoria: str = "",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Lista as transações (extrato) da conta do cliente autenticado.

    Use quando o cliente pedir extrato, últimas movimentações, "no que eu gastei",
    "quanto gastei com comida", "quais foram meus últimos Pix" etc.

    Args:
        dias: Quantos dias para trás buscar. Padrão 30. Use 7 para "esta semana"
            e 90 para "últimos três meses". Máximo aceito: 90.
        categoria: Filtro opcional de categoria. Deixe vazio para trazer tudo.
            Categorias válidas: alimentacao, transporte, assinatura, saude,
            transferencia, salario, moradia, compras.

    Returns:
        dict com a lista de transações, total de entradas e total de saídas.
    """
    try:
        numero = _conta(tool_context)
    except SemContaError as e:
        return erro(str(e))

    dias = max(1, min(int(dias or 30), 90))
    sql = (
        "SELECT data, descricao, categoria, tipo, valor FROM transacoes "
        "WHERE conta_numero = ? AND data >= date('2026-07-27', ?)"
    )
    params: list[Any] = [numero, f"-{dias} days"]
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria.strip().lower())
    sql += " ORDER BY data DESC, id DESC"

    linhas = buscar_varios(sql, tuple(params))
    entradas = sum(l["valor"] for l in linhas if l["tipo"] == "credito")
    saidas = sum(l["valor"] for l in linhas if l["tipo"] == "debito")

    # Gastos agrupados por categoria (o LLM resume muito melhor com isto pronto
    # do que tendo que somar 40 linhas na cabeça).
    por_categoria: dict[str, float] = {}
    for l in linhas:
        if l["tipo"] == "debito":
            por_categoria[l["categoria"]] = por_categoria.get(l["categoria"], 0) + l["valor"]
    ranking = sorted(por_categoria.items(), key=lambda x: -x[1])

    LIMITE = 15  # devolvemos só as mais recentes; o resumo cobre o resto

    return ok(
        conta=numero,
        periodo_dias=dias,
        categoria=categoria or "todas",
        quantidade_total=len(linhas),
        total_entradas=round(entradas, 2),
        total_entradas_formatado=brl(entradas),
        total_saidas=round(saidas, 2),
        total_saidas_formatado=brl(saidas),
        saldo_periodo=round(entradas - saidas, 2),
        gastos_por_categoria=[
            {"categoria": c, "total": round(v, 2), "total_formatado": brl(v)} for c, v in ranking
        ],
        mostrando=f"as {min(LIMITE, len(linhas))} transações mais recentes de {len(linhas)}",
        transacoes=[
            {
                "data": l["data"],
                "descricao": l["descricao"],
                "categoria": l["categoria"],
                "tipo": l["tipo"],
                "valor": round(l["valor"], 2),
                "valor_formatado": ("+" if l["tipo"] == "credito" else "-") + brl(l["valor"]),
            }
            for l in linhas[:LIMITE]
        ],
    )


def consultar_dados_conta(tool_context: ToolContext) -> dict[str, Any]:
    """Consulta os dados cadastrais da conta e do titular.

    Use quando o cliente perguntar qual a agência, o número da conta, o tipo
    de conta, desde quando é cliente, o e-mail/telefone cadastrado ou o
    score de crédito dele.

    Returns:
        dict com agência, número, tipo, data de abertura, status e dados do titular.
    """
    try:
        numero = _conta(tool_context)
    except SemContaError as e:
        return erro(str(e))

    conta = dados_conta(numero)
    if not conta:
        return erro(f"Conta {numero} não encontrada.")

    return ok(
        agencia=conta["agencia"],
        conta=conta["numero"],
        tipo_conta=conta["tipo"],
        status=conta["status"],
        cliente_desde=conta["aberta_em"],
        titular={
            "nome": conta["nome"],
            "cpf": conta["cpf"],
            "email": conta["email"],
            "telefone": conta["telefone"],
            "score_credito": conta["score"],
        },
    )


def _conta(tool_context: ToolContext | None) -> str:
    from mini_banco.tools.comum import conta_da_sessao

    if tool_context is None:
        raise SemContaError("ToolContext ausente.")
    return conta_da_sessao(tool_context)
