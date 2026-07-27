# Cola de entrevista — Google ADK

Respostas curtas, para decorar. Exemplos tirados do projeto **Mini Banco com IA**.

---

## O que é o Google ADK

Framework open-source do Google (Python e Java/Go) para construir **sistemas de agentes de IA**.
Ele cuida do ciclo LLM ↔ ferramentas ↔ histórico; você cuida da regra de negócio.

**Frase pronta:** *"É o Spring dos agentes: você escreve funções e prompts, ele orquestra
o resto — chamada de tool, memória, delegação e estado."*

- Funciona com Gemini nativo e, via LiteLLM, com OpenAI/Anthropic/Ollama/Bedrock.
- Model-agnostic e deploy-agnostic (local, Cloud Run, Vertex AI Agent Engine).
- Traz CLI própria: `adk web` (UI de debug), `adk run`, `adk eval`.
- Versão atual: **2.x**, cuja mudança grande foi passar a execução hierárquica para um
  **motor de grafo**, com retry e human-in-the-loop nativos.

---

## Agent

Um LLM + instrução + descrição + lista de tools.

```python
LlmAgent(name=..., model=..., description=..., instruction=..., tools=[...])
```

- `instruction` = system prompt **dele**.
- `description` = o que os **outros** agentes leem para decidir se delegam pra ele.
- `Agent` é apelido de `LlmAgent`.

---

## Tool

Uma função Python. Sem decorator.

O ADK extrai automaticamente: **nome** da função, **descrição** da docstring, **schema**
dos type hints.

```python
def consultar_saldo(tool_context: ToolContext) -> dict:
    """Consulta o saldo atual da conta do cliente autenticado."""
```

Tipos de tool no ADK: **Function Tools**, **Agent-as-a-Tool**, **Built-in** (`google_search`,
`load_memory`, code executor), **MCP** e **OpenAPI/API Hub**.

---

## Runner

O motor de execução. Recebe a mensagem, carrega a Session, roda o loop
`LLM → tool → LLM` até sair a resposta, e persiste tudo.

Devolve um **stream de Events** — cada Event é uma chamada de tool, um resultado ou um texto.

```python
Runner(app_name=..., agent=root_agent, session_service=..., memory_service=...)
```

---

## Session

**Uma conversa.** Guarda a lista de Events + o State.
Hierarquia: `app_name` → `user_id` → `session_id`.

Implementações: `InMemorySessionService` (dev), `DatabaseSessionService` (SQL),
`VertexAiSessionService` (gerenciado).

---

## State

O **dicionário** daquela conversa. Onde o agente guarda variável de trabalho.

Prefixos (pergunta clássica de entrevista):

| prefixo | escopo |
|---|---|
| *(sem prefixo)* | só esta sessão |
| `user:` | todas as sessões daquele `user_id` |
| `app:` | todos os usuários do app |
| `temp:` | só a invocação atual, não persiste |

Três formas de escrever: `tool_context.state[...]`, `output_key=` num agente, ou
`state_delta` no Runner.

---

## Memory

Busca em conversas **antigas**, já encerradas. Diferente de State:

> **State = a conversa de agora. Memory = as conversas de antes.**

```python
await memory_service.add_session_to_memory(sessao)   # arquiva
tools=[load_memory]                                  # agente pesquisa
```

`InMemoryMemoryService` (keyword, dev) · `VertexAiMemoryBankService` (semântico, prod).

---

## Multi-Agent

Árvore de agentes. Cada um com escopo e tools próprias.

**Por que dividir:** prompt menor e mais preciso, menos tools por chamada (menos erro de
escolha), times diferentes mantêm agentes diferentes, e dá para usar modelo caro só onde
precisa.

No projeto: 1 root + 3 especialistas (conta, crédito, suporte) + 1 workflow.

---

## Workflow

Agentes de orquestração **determinística** — a ordem está no código, não na cabeça do modelo.

| agente | o que faz |
|---|---|
| `SequentialAgent` | um depois do outro |
| `ParallelAgent` | todos ao mesmo tempo |
| `LoopAgent` | repete até um critério |

**Quando usar:** processo com etapas fixas (KYC, análise de risco, onboarding), onde você
**não quer** que o LLM decida a ordem. Etapas conversam pelo State via `output_key`.

---

## Callbacks

Ganchos que o ADK chama em volta de cada etapa. Todo agente aceita:

`before/after_model_callback` · `before/after_tool_callback` ·
`before/after_agent_callback` · `on_tool_error_callback`

**Contrato (o que costuma ser perguntado):** devolver `None` = segue normal;
devolver um objeto = o ADK **usa o seu** e pula a etapa. É assim que se faz cache,
mock, guardrail e rate limit.

No projeto, `before_model_callback` segura as chamadas para não estourar a cota do
free tier — sem isso o 429 derrubava a conversa no meio.

Irmão dele: **`retry_config`** (backoff exponencial em erro transitório).
Regra: *callback evita, retry remedia.*

---

## MCP

**Model Context Protocol** — padrão aberto para expor tools por fora do seu código
(outro processo, outro time, outra empresa).

```python
McpToolset(connection_params=StdioConnectionParams(...), tool_filter=[...])
```

**Vantagem empresarial:** o time de risco publica **um** servidor MCP e todos os agentes
do banco consomem, sem copiar código. Suporta stdio, SSE e HTTP streamable.

---

## Como agentes escolhem Tools

**O LLM escolhe**, lendo o schema que o ADK gerou — principalmente a **docstring**.
Não existe `if` no seu código.

Fluxo: ADK manda a lista de tools no request → LLM devolve um `function_call` com os
argumentos em JSON → ADK executa a função → devolve o resultado ao LLM → LLM responde.

**Frase pronta:** *"Tool que o agente não usa quase sempre é docstring ruim, não é bug."*

---

## Como agentes delegam para outros agentes

Dois mecanismos — a diferença é **quem fica com o controle**:

| | como | controle |
|---|---|---|
| **Transferência** | `sub_agents=[...]` → ADK cria `transfer_to_agent` sozinho | **passa** para o filho e fica lá |
| **AgentTool** | `tools=[AgentTool(agent=x)]` | filho executa e **devolve** ao pai |

O LLM escolhe o destino lendo a **`description`** de cada filho.

Regra prática: `transfer` = *"assume a conversa"*; `AgentTool` = *"faz e me devolve"*.

---

## Vantagens do ADK em sistemas empresariais

1. **Auditoria** — tudo vira Event persistido: dá para provar o que o agente fez e por quê.
2. **Segurança / HITL** — confirmação nativa em operação sensível
   (`require_confirmation`), e o dado sensível vem do State (servidor), nunca do texto do LLM.
3. **Modularidade** — cada área do banco mantém o seu agente sem quebrar os outros.
4. **Determinismo onde importa** — Workflow Agents para processo regulado;
   LLM só onde precisa de julgamento.
5. **Sem lock-in de modelo** — troca de LLM é uma linha (`LiteLlm`).
6. **Testabilidade** — `adk eval` + suíte própria; dá para testar tool por tool.
7. **Deploy gerenciado** — Vertex AI Agent Engine, ou Cloud Run/Docker se preferir.
8. **Integração** — MCP e OpenAPI reaproveitam as APIs que a empresa já tem.

---

## Exemplo em um banco real

**Hoje:** o cliente liga na URA, navega por menu, cai numa fila e repete o CPF três vezes.

**Com ADK:**

```
Agente Atendimento (root)
├── Agente Conta          -> Core Banking (OpenAPI)
├── Agente Crédito        -> motor de risco (MCP do time de risco)
├── Agente Cartões        -> bloqueio/desbloqueio (exige confirmação)
├── Agente Cobrança       -> Workflow: consulta dívida → simula acordo → gera boleto
└── Agente Investimentos  -> posição e suitability
```

Ganhos concretos:

- **Autenticação fora do LLM** — o `conta_numero` entra no **State** na hora do login.
  O modelo nunca escolhe de quem é a conta. *(É literalmente o teste 9 deste projeto:
  peço o saldo de outra pessoa e a tool devolve o meu.)*
- **Operação sensível trava** — bloqueio de cartão, transferência e contratação passam por
  `require_confirmation`. Sem o "sim", o `UPDATE` não roda.
- **Trilha para o regulador** — cada Event tem agente, tool, argumentos e resultado.
- **Escala organizacional** — o time de crédito publica o MCP de risco; os outros consomem.
- **Custo controlado** — modelo grande no roteador, modelo barato nos coletores.

**Frase de fechamento:** *"O ADK não substitui o core banking. Ele vira a camada de
conversa por cima dele — com autenticação no State, confirmação humana na escrita e
trilha de auditoria em cada passo."*

---

## Perguntas capciosas — respostas de 1 linha

| pergunta | resposta |
|---|---|
| State x Memory? | State = conversa atual; Memory = conversas antigas. |
| `transfer_to_agent` x `AgentTool`? | transfer passa o controle; AgentTool devolve. |
| Como o agente sabe usar a tool? | Lendo a docstring — o LLM decide, não o seu código. |
| Como troco de LLM? | Uma linha: string = Gemini, `LiteLlm(...)` = o resto. |
| Como impedir alucinação de dado sensível? | O dado vem do State (servidor), não de parâmetro do LLM. |
| Quando NÃO usar LlmAgent? | Quando a ordem é fixa/regulada — aí é Workflow Agent. |
| O que é um Event? | A unidade do histórico: tool call, tool result ou texto. É o que fica auditável. |
| Session x Runner? | Session guarda; Runner executa. |
| Callback x retry? | Callback evita o erro antes; retry remedia depois. |
| Como faço cache/guardrail? | `before_model_callback` devolvendo um `LlmResponse` — o ADK usa o seu e não chama o LLM. |
