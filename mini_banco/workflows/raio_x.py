"""WORKFLOW: Raio-X Financeiro.

>>> ISTO É "WORKFLOW AGENT". <<<

Além do LlmAgent (que decide sozinho o que fazer), o ADK tem agentes de
orquestração DETERMINÍSTICA — a ordem é fixa, escrita em código, não depende
do humor do modelo:

  SequentialAgent -> roda os filhos em ordem, um depois do outro
  ParallelAgent   -> roda os filhos ao mesmo tempo
  LoopAgent       -> repete até um critério

Aqui montamos:

    SequentialAgent "raio_x_financeiro"
      ├── ParallelAgent "coleta_paralela"      (roda os dois juntos)
      │     ├── LlmAgent coletor_conta    -> output_key="resumo_conta"
      │     └── LlmAgent coletor_credito  -> output_key="resumo_credito"
      └── LlmAgent parecerista            -> lê {resumo_conta} e {resumo_credito}

`output_key` grava a resposta do agente no STATE. O agente seguinte lê esse
valor pela interpolação `{resumo_conta}` na instruction. É assim que agentes
"conversam" dentro de um workflow: via State.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from mini_banco import prompts
from mini_banco.config import MODELO, RETRY
from mini_banco.limitador import limitar_rpm
from mini_banco.tools.conta_tools import consultar_extrato, consultar_saldo
from mini_banco.tools.credito_tools import consultar_emprestimos

coletor_conta = LlmAgent(
    name="coletor_conta",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    description="Coleta saldo e resumo do extrato do mês.",
    instruction=prompts.WF_CONTA,
    tools=[consultar_saldo, consultar_extrato],
    output_key="resumo_conta",  # <- grava a resposta em state["resumo_conta"]
)

coletor_credito = LlmAgent(
    name="coletor_credito",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    description="Coleta a situação dos empréstimos do cliente.",
    instruction=prompts.WF_CREDITO,
    tools=[consultar_emprestimos],
    output_key="resumo_credito",  # <- grava em state["resumo_credito"]
)

coleta_paralela = ParallelAgent(
    name="coleta_paralela",
    description="Coleta dados de conta e de crédito ao mesmo tempo.",
    sub_agents=[coletor_conta, coletor_credito],
)

parecerista = LlmAgent(
    name="parecerista",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    description="Escreve o parecer final juntando os dois resumos.",
    instruction=prompts.WF_PARECER,  # usa {resumo_conta} e {resumo_credito} do State
)

raio_x_financeiro = SequentialAgent(
    name="raio_x_financeiro",
    description=(
        "Workflow que gera o Raio-X Financeiro completo do cliente: coleta saldo, "
        "extrato e empréstimos em paralelo e devolve um parecer com recomendação."
    ),
    sub_agents=[coleta_paralela, parecerista],
)
