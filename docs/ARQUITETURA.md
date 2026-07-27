# Arquitetura e decisões técnicas

Registro do que foi construído, como e por quê. Serve de contexto para quem (ou qual IA)
pegar o projeto depois.

**Criado em:** 2026-07-27 · **google-adk:** 2.5.0 · **Python:** 3.13 (venv em `.venv/`)

---

## 1. Visão geral

Sistema de atendimento bancário multi-agent. O usuário conversa; um agente raiz entende a
intenção e delega para o especialista. As ferramentas consultam um SQLite fictício.

```
navegador (app/static/index.html)
        │  HTTP JSON
app/server.py  (FastAPI)
        │
app/nucleo.py  ── Runner ── SessionService(SQLite) ── MemoryService(RAM)
        │
mini_banco/agent.py  root_agent
   ├── agente_conta ─┐
   ├── agente_credito┤── tools ──> banco/db.py ──> data/banco.db
   ├── agente_suporte┘
   ├── [AgentTool] raio_x_financeiro (Sequential > Parallel)
   └── agente_credito também consome mcp_server/servidor_indicadores.py (stdio)
```

---

## 2. Árvore de agentes

| agente | tipo | tools |
|---|---|---|
| `atendente_mini_banco` | `LlmAgent` (root) | `AgentTool(raio_x_financeiro)`, `salvar_preferencia`, `listar_preferencias`, `load_memory` |
| `agente_conta` | `LlmAgent` | `consultar_saldo`, `consultar_extrato`, `consultar_dados_conta` + preferências |
| `agente_credito` | `LlmAgent` | `consultar_condicoes_credito`, `simular_emprestimo`, `consultar_emprestimos`, `contratar_emprestimo`* + 3 tools MCP + preferências |
| `agente_suporte` | `LlmAgent` | `consultar_cartoes`, `consultar_faq`, `bloquear_cartao`*, `desbloquear_cartao`* + preferências |
| `raio_x_financeiro` | `SequentialAgent` | — |
| ↳ `coleta_paralela` | `ParallelAgent` | — |
| ↳↳ `coletor_conta` | `LlmAgent` | `output_key="resumo_conta"` |
| ↳↳ `coletor_credito` | `LlmAgent` | `output_key="resumo_credito"` |
| ↳ `parecerista` | `LlmAgent` | lê `{resumo_conta}` e `{resumo_credito}` |

`*` exige confirmação do usuário.

---

## 3. Decisões técnicas

### 3.1 Modelo de LLM configurável — hoje roda em Gemini
`mini_banco/config.py` devolve **string** (Gemini nativo) ou objeto **`LiteLlm`** (demais
providers). Só o `.env` muda.

**Default atual: `gemini-3.5-flash-lite`** (`LLM_PROVIDER=gemini`).
Validado também em `openai/gpt-4o-mini` — a suíte passa 60/60 nos dois.

**Por que flash-lite e não `gemini-3.6-flash`:** limites do free tier do AI Studio medidos
em 2026-07-27 — `gemini-3.6-flash` dá **5 req/min**, `gemini-3.5-flash-lite` dá **15/min**.
Uma única mensagem num app multi-agent consome 3-4 chamadas. Com conta paga, troque para
`LLM_MODEL=gemini-3.6-flash` e `LLM_MAX_RPM=0` no `.env`.

Pegadinha: `gemini-2.5-flash` **aparece** em `GET /v1beta/models` mas responde
`404 "no longer available to new users"`. Listar modelos não garante acesso — só um
`generateContent` de teste confirma.

### 3.1b Rate limit tratado em duas camadas
- **`before_model_callback=limitar_rpm`** (`mini_banco/limitador.py`) — janela deslizante
  de 60s, teto em `LLM_MAX_RPM` (padrão 12). **Evita** o 429.
- **`retry_config=RETRY`** (`mini_banco/config.py`) — backoff exponencial em
  `_ResourceExhaustedError` e `ServerError`. **Remedia** o que escapar.

`ClientError` genérico foi deliberadamente **retirado** da lista de exceções: cobre
400/403, que nunca passam na segunda tentativa, e o nó repetido à toa criava pedido de
confirmação órfão.

### 3.2 A conta vem do State, nunca do LLM
`mini_banco/tools/comum.py::conta_da_sessao()` lê `state["conta_numero"]`. Nenhuma tool
aceita número de conta como parâmetro. É a defesa contra o modelo "escolher" a conta de
outra pessoa — coberto pelo teste 9.

### 3.3 Três estilos de confirmação (HITL), de propósito
Para o projeto servir de referência, cada estilo do ADK aparece uma vez:

| tool | estilo | onde |
|---|---|---|
| `bloquear_cartao` | **manual** — `tool_context.request_confirmation(hint=..., payload=...)`, hint em português | `tools/suporte_tools.py` |
| `desbloquear_cartao` | **automático** — `FunctionTool(..., require_confirmation=True)` | `sub_agents/suporte_agent.py` |
| `contratar_emprestimo` | **condicional** — `require_confirmation=<callable>` | `sub_agents/credito_agent.py` |

O app responde com um `FunctionResponse` de nome `adk_request_confirmation`, passando o
`invocation_id` original para retomar a mesma invocação (`app/nucleo.py::responder_confirmacao`).

### 3.4 `DatabaseSessionService` em vez de `InMemory`
`data/sessoes.db` (sqlite+aiosqlite). Sessão e State sobrevivem ao restart — é o que prova
o conceito de Session persistente. Exigiu o extra `google-adk[db]`.

### 3.5 Memória arquivada manualmente
`InMemoryMemoryService` + botão "Encerrar & memorizar" → `add_session_to_memory`.
Busca é por palavra-chave (é o que o serviço in-memory faz). Em produção:
`VertexAiMemoryBankService`.

### 3.6 MCP por stdio, subprocesso local
`mcp_server/servidor_indicadores.py` roda com `FastMCP` e **não importa nada do ADK** — de
propósito, para deixar claro onde termina o MCP e começa o ADK. Ligado/desligado por
`MCP_INDICADORES` no `.env`. `tool_filter` explícito.

### 3.6b Login demo via `before_agent_callback`
`mini_banco/autenticacao.py::login_demo` roda antes do agente raiz e, se o State estiver
sem `conta_numero`, autentica o `CLIENTE_DEMO` (padrão CLI001).

**Por que existe:** o `app/server.py` cria a Session já com o cliente logado, mas o
`adk web` cria sessões com State **vazio** — e a interpolação `{nome_cliente}` das
instruções estourava com `KeyError: Context variable not found`. Duas correções:
o callback (que faz o `adk web` funcionar de verdade) e a sintaxe **`{nome_cliente?}`**
do ADK, que marca o placeholder como opcional — cinto de segurança para qualquer outro
entrypoint que crie sessão sem State.

Num sistema real, este callback é o ponto natural para validar o token do usuário e
carregar o cadastro dele no State.

### 3.7 Interface própria em vez de só `adk web`
`adk web .` funciona (testado, descobre o app `mini_banco`), mas o painel lateral próprio
mostra **trilha de tools + State** lado a lado com o chat, que é o ponto didático.
As duas UIs coexistem.

---

## 4. Banco de dados fictício

`banco/schema.sql` + `banco/seed.py` (`random.seed(42)` → reproduzível).

- 3 clientes: **CLI001** Matheus (score 812, saldo positivo), **CLI002** Ana (score 640),
  **CLI003** Carlos (score 455, **saldo negativo** — bom para testar cheque especial).
- 4 cartões (um já bloqueado, do CLI003), 3 empréstimos (1 quitado), 4 produtos de crédito.
- 120 transações em 90 dias. **Salário (dia 5) e aluguel (dia 10) são fixos mensais** —
  sem isso o extrato de 30 dias saía sem nenhuma entrada e o cliente "parecia" sem renda.

`data/` é gitignored; recrie com `python -m banco.seed`.

---

## 5. Bugs encontrados e corrigidos durante o desenvolvimento

| # | sintoma | causa | correção |
|---|---|---|---|
| 1 | `AttributeError: 'State' object has no attribute 'pop'` | `State` não é `dict`; só tem `get/setdefault/update/to_dict` | gravar `None` na chave |
| 2 | `LoadMemoryResponse is not JSON serializable` — quebraria `/api/mensagem` | `load_memory` devolve objeto Pydantic, não `dict` | `_json_seguro()` em `app/nucleo.py` |
| 3 | "qual a taxa Selic?" não chegava ao MCP | "Selic" não estava na `description` do `agente_credito` nem na regra do root | citar nos dois lugares |
| 4 | agente perguntava "você confirma?" sozinho, gastando um turno | prompt ambíguo | instrução explícita: *"CHAME A TOOL DIRETO"* |
| 5 | "panorama geral" dentro do sub-agente não acionava o workflow | após `transfer`, o controle **fica** com o filho | sub-agentes instruídos a devolver ao root |
| 6 | extrato despejava 40 transações no contexto | tool devolvia tudo | 15 mais recentes + `gastos_por_categoria` já somado |
| 7 | `pip install litellm` falhava pedindo Rust (Py 3.13) | pip escolhia sdist | `--only-binary :all:` (documentado no `requirements.txt`) |
| 8 | `ValueError: Tool 'bloquear_cartao' does not require confirmation` (só no Gemini) | retry por 429 repetia o nó; o nó repetido emitia um 2º pedido de confirmação e o 1º virava órfão | ler o pedido pendente da **Session persistida** (`_confirmacao_pendente`, igual ao `adk run`) em vez do stream + rate limiter para o 429 não acontecer |
| 9 | `PermissionError: arquivo já está sendo usado` ao rodar `banco.seed` com o servidor no ar | `with sqlite3.connect(...)` faz commit mas **não fecha** a conexão | `contextlib.closing` em `banco/db.py::conectar()` |
| 10 | 429 constante no Gemini free tier | 15 req/min e cada mensagem gasta 3-4 chamadas | `before_model_callback` limitando RPM (ver 3.1b) — de até 56 ocorrências por execução para **zero** |
| 11 | `adk web` quebrava com `KeyError: Context variable not found: nome_cliente` | a UI oficial cria sessão com State vazio; as instruções interpolam `{nome_cliente}` | `before_agent_callback` de login demo + placeholders opcionais `{nome_cliente?}` (ver 3.6b) |

---

## 6. Testes

`testes/teste_completo.py` — 60 asserções, chama o LLM de verdade.

| modelo | resultado |
|---|---|
| `openai/gpt-4o-mini` | **60/60**, 4 execuções, ~80s cada |
| `gemini-3.5-flash-lite` | **60/60**, 3 execuções, ~255s cada (mais lento por causa do limitador de RPM) |

Cobre: 3 tools de conta · 4 de crédito · 2 de suporte · delegação para os 3 especialistas ·
confirmação aceita (banco muda) · confirmação recusada (banco **não** muda) · confirmação
condicional com saldo creditado · State inicial, escrita, contexto entre mensagens,
prefixo `user:` vazando para sessão nova, persistência no SQLite · workflow com
`output_key` no State · MCP · memória entre sessões · isolamento entre clientes.

Validação manual no navegador: card de confirmação, botão Cancelar (banco intacto),
workflow renderizado, painel de State.

---

## 7. O que ficou de fora (ideias para continuar)

- `LoopAgent` (nenhum caso natural apareceu)
- `adk eval` com casos gravados
- Autenticação real (hoje o "login" é escolher o cliente num `<select>`)
- MCP remoto (SSE/HTTP) — só stdio foi implementado
- Streaming token a token na UI (hoje a resposta chega inteira)
