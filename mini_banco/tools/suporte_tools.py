"""Function Tools do Agente de Suporte.

`bloquear_cartao` e `desbloquear_cartao` alteram dados -> exigem confirmação.
`consultar_cartoes` é só leitura -> roda direto.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from banco.db import buscar_um, buscar_varios, executar
from mini_banco.tools.comum import SemContaError, brl, conta_da_sessao, erro, ok


def consultar_cartoes(tool_context: ToolContext) -> dict[str, Any]:
    """Lista os cartões do cliente com status, bandeira, limite e final do número.

    Use quando o cliente perguntar "quais cartões eu tenho", "meu cartão está
    bloqueado?", "qual meu limite", "quanto já usei do limite" ou antes de
    bloquear/desbloquear, para descobrir o final do cartão certo.

    Returns:
        dict com a lista de cartões (id, bandeira, tipo, final, status, limite).
    """
    try:
        numero = conta_da_sessao(tool_context)
    except SemContaError as e:
        return erro(str(e))

    linhas = buscar_varios(
        "SELECT * FROM cartoes WHERE conta_numero = ? ORDER BY tipo, final", (numero,)
    )
    return ok(
        conta=numero,
        quantidade=len(linhas),
        cartoes=[
            {
                "id": c["id"],
                "bandeira": c["bandeira"],
                "tipo": c["tipo"],
                "final": c["final"],
                "status": c["status"],
                "limite": round(c["limite"], 2),
                "limite_usado": round(c["limite_usado"], 2),
                "limite_disponivel": round(c["limite"] - c["limite_usado"], 2),
                "limite_disponivel_formatado": brl(c["limite"] - c["limite_usado"]),
                "validade": c["validade"],
                "motivo_bloqueio": c["motivo_bloqueio"],
            }
            for c in linhas
        ],
    )


# ------------------------------------------------------------------
#  OPERAÇÕES DE ESCRITA — exigem confirmação (ver suporte_agent.py)
# ------------------------------------------------------------------
def bloquear_cartao(
    final_do_cartao: str,
    motivo: str = "solicitacao do cliente",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """BLOQUEIA um cartão do cliente. Operação irreversível pelo chat.

    ATENÇÃO: altera dados. Use quando o cliente disser que perdeu o cartão,
    foi roubado, viu uma compra que não reconhece, ou pedir explicitamente
    para bloquear. Se o cliente não disser qual cartão, chame antes
    `consultar_cartoes` e pergunte qual dos finais ele quer bloquear.
    Chame esta tool direto: o próprio sistema pede a confirmação ao cliente.

    Args:
        final_do_cartao: Os 4 últimos dígitos do cartão (ex.: "4417").
        motivo: Por que está bloqueando. Ex.: "perda", "roubo", "fraude",
            "solicitacao do cliente".

    Returns:
        dict confirmando o bloqueio, ou erro se o cartão não existir.
    """
    try:
        numero = conta_da_sessao(tool_context)
    except SemContaError as e:
        return erro(str(e))

    final = str(final_do_cartao).strip()[-4:]
    cartao = buscar_um(
        "SELECT * FROM cartoes WHERE conta_numero = ? AND final = ?", (numero, final)
    )
    if not cartao:
        disponiveis = [c["final"] for c in buscar_varios(
            "SELECT final FROM cartoes WHERE conta_numero = ?", (numero,))]
        return erro(f"Nenhum cartão com final {final} nesta conta.", finais_disponiveis=disponiveis)

    if cartao["status"] == "bloqueado":
        return ok(
            mensagem=f"O cartão final {final} JÁ estava bloqueado.",
            cartao=cartao["id"],
            situacao="bloqueado",
            motivo_bloqueio=cartao["motivo_bloqueio"],
            alterado=False,
        )

    # ------------------------------------------------------------------
    # >>> CONFIRMAÇÃO MANUAL (estilo avançado do ADK) <<<
    # Na 1ª chamada `tool_context.tool_confirmation` é None: pedimos o OK com
    # uma mensagem nossa, em português, e paramos aqui. O ADK suspende a
    # execução. Quando o app responde o FunctionResponse de confirmação, o ADK
    # chama esta MESMA função de novo, agora com `tool_confirmation` preenchido.
    # ------------------------------------------------------------------
    confirmacao = tool_context.tool_confirmation if tool_context else None
    if confirmacao is None:
        tool_context.request_confirmation(
            hint=(
                f"Confirma o BLOQUEIO do cartão {cartao['bandeira']} "
                f"{cartao['tipo']} final {final}? Motivo: {motivo}. "
                "O cartão para de funcionar na hora e não dá para desfazer pelo chat."
            ),
            payload={"cartao_id": cartao["id"], "final": final, "motivo": motivo},
        )
        return {"status": "aguardando_confirmacao",
                "mensagem": "Esperando o cliente confirmar o bloqueio."}

    if not confirmacao.confirmed:
        return ok(
            mensagem="O cliente NÃO confirmou. Bloqueio cancelado, nada foi alterado.",
            alterado=False,
            situacao=cartao["status"],
        )

    executar(
        "UPDATE cartoes SET status = 'bloqueado', motivo_bloqueio = ? WHERE id = ?",
        (motivo, cartao["id"]),
    )
    return ok(
        mensagem=f"Cartão {cartao['bandeira']} {cartao['tipo']} final {final} bloqueado.",
        cartao=cartao["id"],
        final=final,
        situacao="bloqueado",
        motivo_bloqueio=motivo,
        alterado=True,
        proximo_passo="Um cartão novo será enviado ao endereço cadastrado em até 7 dias úteis.",
    )


def desbloquear_cartao(
    final_do_cartao: str,
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """DESBLOQUEIA um cartão que estava bloqueado. Operação que altera dados.

    Use quando o cliente achou o cartão que tinha dado como perdido ou pedir
    para reativar. O ADK vai pedir a confirmação explícita antes de executar.

    Args:
        final_do_cartao: Os 4 últimos dígitos do cartão (ex.: "4417").

    Returns:
        dict confirmando o desbloqueio, ou erro se o cartão não existir.
    """
    try:
        numero = conta_da_sessao(tool_context)
    except SemContaError as e:
        return erro(str(e))

    final = str(final_do_cartao).strip()[-4:]
    cartao = buscar_um(
        "SELECT * FROM cartoes WHERE conta_numero = ? AND final = ?", (numero, final)
    )
    if not cartao:
        return erro(f"Nenhum cartão com final {final} nesta conta.")
    if cartao["status"] == "cancelado":
        return erro(f"O cartão final {final} está CANCELADO e não pode ser reativado.")
    if cartao["status"] == "ativo":
        return ok(mensagem=f"O cartão final {final} já está ativo.", alterado=False, situacao="ativo")

    executar(
        "UPDATE cartoes SET status = 'ativo', motivo_bloqueio = NULL WHERE id = ?", (cartao["id"],)
    )
    return ok(
        mensagem=f"Cartão final {final} desbloqueado e pronto para uso.",
        cartao=cartao["id"],
        situacao="ativo",
        alterado=True,
    )


FAQ = {
    "horario": "Agências abrem de segunda a sexta, das 10h às 16h. O app e este chat funcionam 24h.",
    "pix": "O Pix é gratuito e ilimitado para pessoa física, 24h por dia. O limite noturno "
           "(20h às 6h) é de R$ 1.000 e pode ser alterado no app em Segurança > Limites.",
    "segunda_via": "A segunda via do cartão é gratuita em caso de defeito e custa R$ 25 em caso "
                   "de perda. Chega em até 7 dias úteis no endereço cadastrado.",
    "tarifas": "A conta corrente digital não tem tarifa de manutenção. Saque em caixa de outra "
               "rede custa R$ 6,50. TED é gratuita.",
    "senha": "Para trocar a senha do cartão: app > Cartões > escolher o cartão > Trocar senha. "
             "Precisa da biometria. Pelo chat não é possível trocar senha.",
    "fatura": "A fatura fecha todo dia 25 e vence dia 5. Dá para antecipar o pagamento no app.",
    "contestacao": "Compra que você não reconhece: bloqueie o cartão primeiro e depois abra a "
                   "contestação no app em Cartões > Fatura > Não reconheço esta compra. "
                   "O prazo de análise é de até 30 dias.",
}


def consultar_faq(assunto: str) -> dict[str, Any]:
    """Responde dúvidas gerais sobre o banco a partir da base oficial de FAQ.

    Use para perguntas que NÃO dependem dos dados do cliente: horário de
    atendimento, regras do Pix, tarifas, segunda via de cartão, troca de senha,
    fechamento de fatura e contestação de compra.

    Args:
        assunto: Palavra-chave do assunto. Valores aceitos: horario, pix,
            segunda_via, tarifas, senha, fatura, contestacao.

    Returns:
        dict com a resposta oficial, ou a lista de assuntos disponíveis.
    """
    chave = (assunto or "").strip().lower().replace(" ", "_")
    if chave in FAQ:
        return ok(assunto=chave, resposta=FAQ[chave])
    for k, v in FAQ.items():
        if chave and (chave in k or k in chave):
            return ok(assunto=k, resposta=v)
    return erro(
        f"Não tenho esse assunto no FAQ ('{assunto}').",
        assuntos_disponiveis=list(FAQ.keys()),
    )
