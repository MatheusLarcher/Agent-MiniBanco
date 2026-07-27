"""AGENTE PRINCIPAL (root agent) do Mini Banco.

>>> ISTO É "MULTI-AGENT". <<<

O agente principal:
  - tem `sub_agents=[...]` -> o ADK gera automaticamente a tool
    `transfer_to_agent` e coloca a `description` de cada filho no prompt.
    É lendo essas descriptions que o modelo escolhe para quem delegar.
  - tem `tools=[AgentTool(...)]` -> jeito diferente de usar outro agente:
    aqui o filho vira uma FERRAMENTA (o controle volta para o pai no fim),
    em vez de uma TRANSFERÊNCIA (o controle fica com o filho).

Regra prática:
  transfer_to_agent -> "assume a conversa por mim"
  AgentTool         -> "faz esse trabalho e me devolve o resultado"

O nome `root_agent` é convenção do ADK: é o que o `adk web` / `adk run`
procuram dentro do pacote.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, load_memory

from mini_banco import prompts
from mini_banco.autenticacao import login_demo
from mini_banco.config import MODELO, RETRY
from mini_banco.limitador import limitar_rpm
from mini_banco.sub_agents.conta_agent import agente_conta
from mini_banco.sub_agents.credito_agent import agente_credito
from mini_banco.sub_agents.suporte_agent import agente_suporte
from mini_banco.tools.memoria_tools import listar_preferencias, salvar_preferencia
from mini_banco.workflows.raio_x import raio_x_financeiro

root_agent = LlmAgent(
    name="atendente_mini_banco",
    model=MODELO,
    retry_config=RETRY,               # ADK repete sozinho em 429/5xx
    before_model_callback=limitar_rpm,  # segura antes de estourar a cota
    before_agent_callback=login_demo,   # garante cliente no State (usado pelo `adk web`)
    description="Atendente principal do Mini Banco. Entende a intenção e delega ao especialista.",
    instruction=prompts.ROOT,
    # --- DELEGAÇÃO: o controle passa para o filho ---
    sub_agents=[agente_conta, agente_credito, agente_suporte],
    # --- FERRAMENTAS do próprio root ---
    tools=[
        AgentTool(agent=raio_x_financeiro),  # workflow usado como ferramenta
        salvar_preferencia,
        listar_preferencias,
        load_memory,  # tool NATIVA do ADK: busca em conversas antigas (MemoryService)
    ],
)
