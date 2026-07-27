# Aprendendo Google ADK na prática

Guia curto do projeto **Mini Banco com IA**. Cada tópico mostra **o arquivo**, **o trecho
que importa** e **a explicação em português simples**.

Antes de tudo, a ideia em uma frase:

> Você escreve **funções Python** (Tools) e **textos de instrução** (prompts).
> O ADK monta o prompt, chama o LLM, executa as funções que o LLM pediu e guarda tudo.

---

## 1. Como criei o primeiro Agent

📄 `mini_banco/sub_agents/conta_agent.py`

```python
from google.adk.agents import LlmAgent

agente_conta = LlmAgent(
    name="agente_conta",
    model=MODELO,
    description="Especialista em conta: saldo, extrato, movimentações...",
    instruction=prompts.CONTA,
    tools=[consultar_saldo, consultar_extrato, consultar_dados_conta],
)
```

Um Agent é **um objeto**, não uma classe que você herda. Os 5 campos:

| campo | pra que serve |
|---|---|
| `name` | identidade única. Outros agentes usam esse nome para delegar. |
| `model` | qual LLM roda esse agente |
| `description` | **para os OUTROS agentes lerem** e decidirem se delegam para cá |
| `instruction` | o system prompt **deste** agente |
| `tools` | lista de funções que ele pode chamar |

> `Agent` e `LlmAgent` são **a mesma coisa** — `Agent` é só um apelido. Uso `LlmAgent`
> porque deixa explícito que é o agente que pensa com LLM (existem outros: `SequentialAgent`,
> `ParallelAgent`, `LoopAgent`).

---

## 2. Onde ficam as instruções do Agent

📄 `mini_banco/prompts.py` — juntei todas num arquivo só para ficar fácil de achar.

```python
CONTA = """
Você é o especialista em CONTA do Mini Banco.
- Use `consultar_saldo` para qualquer pergunta de "quanto tenho".
- Ao mostrar extrato, resuma: total de entradas, total de saídas...
""" + CONTEXTO_CLIENTE
```

E o `CONTEXTO_CLIENTE` tem o pulo do gato:

```python
CONTEXTO_CLIENTE = """
Cliente autenticado nesta conversa:
- Nome: {nome_cliente}
- Conta: {conta_numero}
"""
```

Aquele `{nome_cliente}` **não é f-string**. É o ADK que troca por o valor do **State**
antes de mandar pro LLM. Ou seja: a instrução é a mesma para todos os clientes, mas
chega personalizada.

---

## 3. Como o LLM recebe essas instruções

Você não faz nada. A cada mensagem, o ADK monta sozinho o pacote que vai pra API:

```
system  -> instruction (com {chaves} já trocadas pelo State)
tools   -> o JSON schema de cada tool (nome, descrição, parâmetros)
messages-> todo o histórico da Session
```

Para ver isso acontecendo de verdade:

```bash
adk web .          # abre a UI oficial em http://localhost:8000
```

Na aba **Events** você vê o request cru que saiu para o modelo.

---

## 4. Como criei uma Tool

📄 `mini_banco/tools/conta_tools.py`

```python
def consultar_saldo(tool_context: ToolContext) -> dict[str, Any]:
    """Consulta o saldo atual da conta do cliente autenticado nesta conversa.

    Use sempre que o cliente perguntar quanto tem na conta, quanto sobrou,
    se está no negativo, quanto pode gastar ou qual o limite do cheque especial.
    """
    numero = conta_da_sessao(tool_context)
    conta = dados_conta(numero)
    return ok(saldo=round(conta["saldo"], 2), ...)
```

**É só uma função Python.** Sem decorator, sem classe, sem registro. O que ela precisa ter:

- **nome bom** → vira o nome da tool
- **docstring boa** → vira a descrição (é o que o LLM lê pra decidir)
- **type hints** → viram o schema dos parâmetros
- **devolver `dict`** → o LLM lê melhor JSON do que texto solto

---

## 5. Como o Agent descobre que uma Tool existe

Você põe na lista `tools=[...]`. Só isso.

```python
tools=[consultar_saldo, consultar_extrato, consultar_dados_conta],
```

O ADK olha cada função com `inspect`, gera o schema JSON e manda junto do prompt. Confira:

```python
from google.adk.tools import FunctionTool
print(FunctionTool(consultar_saldo)._get_declaration())
# name='consultar_saldo' description='Consulta o saldo atual...' parameters={...}
```

---

## 6. Como o Agent sabe QUANDO usar uma Tool

**Quem decide é o LLM, lendo a docstring.** Não existe `if` no seu código.

Por isso escrevo as docstrings assim — listando as frases reais do cliente:

```python
"""Lista as transações (extrato) da conta do cliente autenticado.

Use quando o cliente pedir extrato, últimas movimentações, "no que eu gastei",
"quanto gastei com comida", "quais foram meus últimos Pix" etc.
"""
```

> **Regra de ouro:** tool que o agente não usa quase sempre é **docstring ruim**,
> não é bug de código.

---

## 7. Como os parâmetros da Tool chegam ao código

O LLM devolve um JSON, o ADK converte e chama sua função.

```python
def consultar_extrato(dias: int = 30, categoria: str = "", tool_context: ToolContext = None):
    """...
    Args:
        dias: Quantos dias para trás buscar. Padrão 30. Use 7 para "esta semana"...
        categoria: Filtro opcional. Categorias válidas: alimentacao, transporte...
    """
```

O cliente escreve *"no que gastei com comida esse mês?"* e chega:

```json
{"dias": 30, "categoria": "alimentacao"}
```

Repare em duas coisas:

- O `Args:` da docstring vira a descrição de **cada parâmetro**. É ali que você ensina
  a tradução ("esta semana" → 7).
- `tool_context: ToolContext` **não vira parâmetro**. O ADK reconhece pelo tipo e injeta
  sozinho. O LLM nem enxerga esse campo.

---

## 8. Como o Runner funciona

📄 `app/nucleo.py`

```python
runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
    memory_service=memory_service,
)

async for evento in runner.run_async(user_id=..., session_id=..., new_message=conteudo):
    ...
```

O Runner é o **motor**. Cada mensagem faz isso:

```
1. carrega a Session (histórico + State)
2. monta o prompt e chama o LLM
3. LLM pediu tool?  -> executa a função, devolve o resultado, volta ao passo 2
   LLM pediu transfer? -> troca o agente ativo, volta ao passo 2
   LLM respondeu texto? -> acabou
4. salva os Events e o State de volta na Session
```

Ele devolve um **stream de Events**. Cada Event é um pedaço do que aconteceu: uma chamada
de tool, um resultado, um texto. É isso que eu leio para montar a coluna
"O que o ADK fez" da interface.

---

## 9. Como Session funciona

📄 `app/nucleo.py`

```python
session_service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{BANCO_SESSOES}")

sessao = await session_service.create_session(
    app_name=APP_NAME,
    user_id=linha["id"],          # CLI001 — agrupa as sessões do mesmo cliente
    state=estado_inicial,
)
```

Session = **uma conversa**. Ela guarda a lista de Events + o State.

Hierarquia: `app_name` → `user_id` → `session_id`.

Trocar de serviço é trocar uma linha:

| serviço | onde guarda |
|---|---|
| `InMemorySessionService()` | RAM, some ao reiniciar |
| `DatabaseSessionService(db_url=...)` | SQLite/Postgres — **é o que uso aqui** |
| `VertexAiSessionService(...)` | gerenciado no Google Cloud |

Prova de que persiste: `data/sessoes.db`. Derrube o servidor, suba de novo, a conversa
antiga ainda está lá.

---

## 10. Como State funciona

State é o **dicionário da conversa**. Nasce em `criar_sessao`:

📄 `app/nucleo.py`

```python
estado_inicial = {
    "cliente_id": linha["id"],
    "nome_cliente": linha["nome"],
    "conta_numero": linha["numero"],   # <- o "login"
}
```

As tools **leem** dele:

📄 `mini_banco/tools/comum.py`

```python
def conta_da_sessao(tool_context: ToolContext) -> str:
    return str(tool_context.state["conta_numero"])
```

E **escrevem** nele:

📄 `mini_banco/tools/credito_tools.py`

```python
tool_context.state["ultima_simulacao"] = {"produto": ..., "valor": ..., "parcelas": ...}
```

Isso é o que faz o cliente poder simular e depois dizer só *"quero contratar essa"*.

### Os prefixos (o detalhe que cai em entrevista)

```python
tool_context.state["ultima_simulacao"] = ...          # só esta conversa
tool_context.state["user:pref_apelido"] = "Carlinhos" # TODAS as conversas deste user_id
tool_context.state["app:banner"] = ...                # todos os usuários do app
tool_context.state["temp:rascunho"] = ...             # some no fim da invocação
```

📄 `mini_banco/tools/memoria_tools.py` usa `user:` de propósito — abra uma sessão nova
e o apelido ainda está lá.

> ⚠️ `State` **não tem `.pop()`**. Para limpar, grave `None`. (Descobri levando o erro
> `AttributeError: 'State' object has no attribute 'pop'` na cara.)

---

## 11. Como memória funciona

**State ≠ Memória.**

- **State** = variáveis da conversa **atual**
- **Memória** = busca dentro de conversas **antigas e já encerradas**

📄 `app/nucleo.py`

```python
memory_service = InMemoryMemoryService()

async def encerrar_sessao(user_id, session_id):
    sessao = await session_service.get_session(...)
    await memory_service.add_session_to_memory(sessao)   # arquiva a conversa
```

📄 `mini_banco/agent.py` — para o agente conseguir buscar, dou a tool nativa:

```python
from google.adk.tools import load_memory

root_agent = LlmAgent(..., tools=[..., load_memory])
```

Fluxo na prática (é o teste 8 da suíte):

1. sessão A: *"meu objetivo é comprar um Cobalt 2015 GNV"*
2. clico em **Encerrar & memorizar**
3. sessão B (nova): *"qual carro eu falei que quero comprar?"*
4. o agente chama `load_memory("carro que quero comprar")` e responde certo

Opções: `InMemoryMemoryService` (busca por palavra-chave, bom pra aprender) e
`VertexAiMemoryBankService` (busca semântica, produção).

---

## 12. Como criamos os subagentes

São LlmAgents normais, em `mini_banco/sub_agents/`. O que os torna "sub" é entrar na
lista do pai:

📄 `mini_banco/agent.py`

```python
root_agent = LlmAgent(
    name="atendente_mini_banco",
    instruction=prompts.ROOT,
    sub_agents=[agente_conta, agente_credito, agente_suporte],
    ...
)
```

Árvore final do projeto:

```
atendente_mini_banco            (LlmAgent — porta de entrada)
├── agente_conta                (LlmAgent) 3 tools + 2 de preferência
├── agente_credito              (LlmAgent) 4 tools + 3 tools via MCP
├── agente_suporte              (LlmAgent) 4 tools
└── [tool] raio_x_financeiro    (SequentialAgent — workflow)
     ├── coleta_paralela        (ParallelAgent)
     │    ├── coletor_conta     (LlmAgent) -> state["resumo_conta"]
     │    └── coletor_credito   (LlmAgent) -> state["resumo_credito"]
     └── parecerista            (LlmAgent) lê os dois do State
```

---

## 13. Como o Agent principal escolhe outro agente

Quando você preenche `sub_agents`, o ADK **automaticamente**:

1. cria a tool `transfer_to_agent(agent_name)`
2. injeta no prompt do pai a `description` de cada filho

Então o LLM escolhe lendo as descriptions. Elas são o "cardápio":

```python
agente_credito = LlmAgent(
    description=(
        "Especialista em crédito: simulação de empréstimo, taxas e condições, "
        "empréstimos contratados, saldo devedor, contratação de crédito novo e "
        "indicadores de mercado (Selic, CDI, IPCA, poupança...)."
    ),
)
```

E eu reforço a regra na instrução do root (📄 `mini_banco/prompts.py`):

```
- `agente_conta`   -> saldo, extrato, movimentações, gastos, dados cadastrais...
- `agente_credito` -> empréstimo, simulação, parcela, juros, Selic, CDI...
- `agente_suporte` -> cartão, perda, roubo, fraude, dúvidas gerais...

1. Se a mensagem cabe em um dos times acima, TRANSFIRA IMEDIATAMENTE.
```

> **Bug real que tomei:** perguntei *"qual a taxa Selic?"* e ninguém atendeu — eu tinha
> esquecido de citar "Selic" tanto na `description` do agente de crédito quanto na regra
> do root. Description ruim = delegação errada.

---

## 14. Como ocorre a comunicação entre agentes

Existem **dois jeitos**, e a diferença é quem fica com o controle:

### A) Transferência (`sub_agents`) — "assume a conversa por mim"

O controle **passa** para o filho e fica lá. As próximas mensagens do cliente vão direto
pro filho. Foi por isso que, num teste, pedir "panorama geral" dentro do agente de
suporte não acionou o workflow: quem estava no comando era o suporte, não o root.
Corrigi mandando os filhos devolverem a bola:

```
- Se ele pedir um PANORAMA GERAL, isso NÃO é seu: transfira para `atendente_mini_banco`.
```

### B) AgentTool — "faz isso e me devolve o resultado"

📄 `mini_banco/agent.py`

```python
from google.adk.tools import AgentTool

tools=[AgentTool(agent=raio_x_financeiro), ...]
```

O agente vira uma **ferramenta**. Ele roda, devolve o texto e o controle **volta** pro pai.

### C) Via State (dentro de um workflow)

📄 `mini_banco/workflows/raio_x.py`

```python
coletor_conta = LlmAgent(..., output_key="resumo_conta")     # grava no State

parecerista = LlmAgent(instruction="""
Relatório de conta:
{resumo_conta}
Relatório de crédito:
{resumo_credito}
""")                                                          # lê do State
```

`output_key` grava a resposta do agente no State; o seguinte lê pela chave. É o
"cano" entre etapas de um workflow.

---

## 15. Como adicionar um novo Agent

Exemplo: **agente de investimentos**.

**1)** instrução em `mini_banco/prompts.py`:
```python
INVESTIMENTOS = """
Você é o especialista em INVESTIMENTOS do Mini Banco.
- Use `consultar_carteira` para mostrar o que o cliente tem aplicado.
""" + CONTEXTO_CLIENTE
```

**2)** arquivo `mini_banco/sub_agents/investimentos_agent.py`:
```python
agente_investimentos = LlmAgent(
    name="agente_investimentos",
    model=MODELO,
    description="Especialista em investimentos: CDB, tesouro, fundos, rentabilidade.",
    instruction=prompts.INVESTIMENTOS,
    tools=[consultar_carteira],
)
```

**3)** pendura no root (`mini_banco/agent.py`):
```python
sub_agents=[agente_conta, agente_credito, agente_suporte, agente_investimentos],
```

**4)** cita ele na regra de roteamento do `prompts.ROOT`. **Não pule este passo** — foi
exatamente ele que me deu o bug do Selic.

---

## 16. Como adicionar uma nova Tool

**1)** escreve a função em `mini_banco/tools/`:
```python
def consultar_carteira(tool_context: ToolContext) -> dict[str, Any]:
    """Lista os investimentos do cliente com valor aplicado e rentabilidade.

    Use quando o cliente perguntar "quanto eu tenho investido", "como está meu CDB",
    "qual o rendimento da minha aplicação".
    """
    numero = conta_da_sessao(tool_context)
    return ok(aplicacoes=buscar_varios("SELECT ... WHERE conta_numero = ?", (numero,)))
```

**2)** põe na lista `tools=[...]` do agente. Pronto.

**Se a tool ALTERA dados**, escolha um dos 3 estilos de confirmação (todos usados aqui):

```python
# 1. automático — ADK monta o pedido sozinho (hint em inglês)
FunctionTool(desbloquear_cartao, require_confirmation=True)

# 2. condicional — uma função decide na hora
FunctionTool(contratar_emprestimo, require_confirmation=lambda valor, **_: valor >= 1000)

# 3. manual — texto seu, em português, com payload  (📄 suporte_tools.py)
if tool_context.tool_confirmation is None:
    tool_context.request_confirmation(
        hint=f"Confirma o BLOQUEIO do cartão final {final}?",
        payload={"cartao_id": cartao["id"]},
    )
    return {"status": "aguardando_confirmacao"}
if not tool_context.tool_confirmation.confirmed:
    return ok(mensagem="Cliente não confirmou. Nada foi alterado.", alterado=False)
# ... só aqui o UPDATE acontece
```

Do lado do app, responder é mandar um `FunctionResponse` em vez de texto
(📄 `app/nucleo.py`):

```python
types.Part(function_response=types.FunctionResponse(
    id=function_call_id,              # o id que veio no pedido
    name="adk_request_confirmation",  # nome fixo do ADK
    response={"confirmed": True},
))
```

---

## 17. Como conectar um MCP

MCP = tools que moram **fora** do seu código, em outro processo ou outro servidor.

**Servidor** (📄 `mcp_server/servidor_indicadores.py`) — não importa nada do ADK:

```python
from mcp.server.fastmcp import FastMCP

servidor = FastMCP("indicadores-mercado")

@servidor.tool()
def taxa_selic_atual() -> dict:
    """Retorna a taxa Selic e o CDI atuais, em % ao ano."""
    return {"selic_ano_percentual": 10.75, "cdi_ano_percentual": 10.65}

servidor.run(transport="stdio")
```

**Cliente** (📄 `mini_banco/sub_agents/credito_agent.py`):

```python
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.servidor_indicadores"],
            cwd=str(RAIZ),
        ),
        timeout=30.0,
    ),
    tool_filter=["taxa_selic_atual", "media_mercado_credito", "inflacao_e_poupanca"],
)
```

E joga no `tools=[...]`. **O agente não sabe a diferença** entre tool local e tool MCP.

Para servidor remoto, troque a conexão por `SseConnectionParams` ou
`StreamableHTTPConnectionParams`. Use `tool_filter` sempre: servidor MCP de terceiro
costuma expor 30 tools e você quer 3.

---

## 18. Como trocar o modelo de LLM

📄 `mini_banco/config.py` — o único lugar.

```python
def get_model():
    if PROVIDER == "gemini":
        return NOME_MODELO                              # string = Gemini nativo
    from google.adk.models.lite_llm import LiteLlm
    if PROVIDER == "deepseek":
        return LiteLlm(model=f"deepseek/{NOME_MODELO}")
    return LiteLlm(model=f"openai/{NOME_MODELO}")       # objeto = qualquer outro
```

Na prática você mexe só no `.env`:

```bash
LLM_PROVIDER=gemini        # LLM_MODEL=gemini-3.5-flash-lite  + GOOGLE_API_KEY
LLM_PROVIDER=openai        # LLM_MODEL=gpt-4o-mini            + OPENAI_API_KEY
LLM_PROVIDER=deepseek      # LLM_MODEL=deepseek-chat          + DEEPSEEK_API_KEY
```

**A regra:** `model=` aceita **string** (Gemini, nativo) ou **objeto** (`LiteLlm`, que
cobre OpenAI, Anthropic, Ollama, Bedrock...). Nada mais no projeto muda.

Dá até para misturar: um modelo caro no agente principal (que decide o roteamento) e
um barato nos coletores do workflow — é só passar `model=` diferente em cada `LlmAgent`.

---

## 19. Callbacks e retry (o que fez o free tier do Gemini funcionar)

Dois recursos do ADK que só entraram no projeto **porque a realidade obrigou** — e que
por isso valem mais que teoria.

O problema: o free tier do AI Studio dá **15 requisições por minuto** no
`gemini-3.5-flash-lite` (e só **5** no `gemini-3.6-flash`). Num app multi-agent, **uma**
mensagem do cliente gasta 3 ou 4 chamadas: o root decide, o especialista pensa, chama a
tool, e pensa de novo com o resultado. A cota estoura fácil.

### `retry_config` — remediar depois

📄 `mini_banco/config.py`

```python
from google.adk.workflow._retry_config import RetryConfig

RETRY = RetryConfig(
    max_attempts=5,
    initial_delay=8.0,
    max_delay=70.0,
    backoff_factor=2.0,
    exceptions=["_ResourceExhaustedError", "ServerError"],
)
```

E em todo agente: `retry_config=RETRY`. O ADK espera e tenta de novo sozinho.

> ⚠️ **Não** ponha `ClientError` genérico na lista: ele cobre 400/403, que nunca vão
> passar na segunda tentativa — só faz o nó rodar à toa.

### `before_model_callback` — evitar antes

📄 `mini_banco/limitador.py`

```python
async def limitar_rpm(callback_context, llm_request) -> None:
    """Roda IMEDIATAMENTE ANTES de cada chamada ao LLM."""
    ...
    if len(_marcas) < MAX_RPM:
        _marcas.append(agora)
        return None          # None = "pode seguir e chamar o LLM"
    await asyncio.sleep(espera)
```

E em todo agente: `before_model_callback=limitar_rpm`.

O contrato do callback é a parte importante:

| o que você devolve | o que o ADK faz |
|---|---|
| `None` | segue normal e chama o LLM |
| um `LlmResponse` | **usa o seu** e NÃO chama o LLM (dá pra fazer cache, mock, bloqueio) |

Existe uma família inteira: `before/after_model_callback`, `before/after_tool_callback`,
`before/after_agent_callback`, `on_tool_error_callback`. É onde entra observabilidade,
guardrail, cache e — como aqui — rate limit.

### `before_agent_callback` — o "login" da conversa

📄 `mini_banco/autenticacao.py`

```python
def login_demo(callback_context) -> None:
    estado = callback_context.state
    if estado.get("conta_numero"):
        return None                      # já tem alguém logado
    estado["cliente_id"] = linha["id"]
    estado["nome_cliente"] = linha["nome"]
    estado["conta_numero"] = linha["numero"]
```

Roda **uma vez**, antes do agente raiz começar. Como recebe o Context, dá para preparar
o State antes de qualquer prompt ser montado.

Por que precisou: o `app/server.py` cria a Session já com o cliente logado, mas o
`adk web` cria sessões com State **vazio** — e a interpolação `{nome_cliente}` estourava
com `KeyError: Context variable not found`. Num sistema real, é aqui que você validaria
o token do usuário.

> Detalhe útil: o ADK aceita **`{nome_cliente?}`** — a interrogação marca o placeholder
> como opcional, e a instrução não quebra se a chave não existir no State.

**Por que evitar é melhor que remediar:** com só o retry, o nó falhava e era repetido; o nó
repetido emitia um **segundo** pedido de confirmação, e o primeiro virava órfão
(`ValueError: Tool 'bloquear_cartao' does not require confirmation`). Com o limitador, o
429 simplesmente não acontece — nos testes, de 2 a 56 ocorrências caíram para **zero**.

---

## 20. Qual parte é Google ADK e qual parte é nossa

### É Google ADK (a gente só usou)

| o que | onde aparece |
|---|---|
| `LlmAgent`, `SequentialAgent`, `ParallelAgent` | `mini_banco/agent.py`, `workflows/raio_x.py` |
| `Runner` | `app/nucleo.py` |
| `DatabaseSessionService`, `Session`, `State` | `app/nucleo.py` |
| `InMemoryMemoryService` | `app/nucleo.py` |
| `FunctionTool` (embrulha função → schema) | `sub_agents/*.py` |
| `transfer_to_agent` (gerado sozinho) | ninguém escreveu — vem do `sub_agents` |
| `AgentTool` (agente virando ferramenta) | `mini_banco/agent.py` |
| `load_memory` (tool nativa) | `mini_banco/agent.py` |
| `require_confirmation` / `request_confirmation` (HITL) | `sub_agents/*.py`, `tools/suporte_tools.py` |
| `McpToolset` | `sub_agents/credito_agent.py` |
| `retry_config` / `RetryConfig` | `mini_banco/config.py` |
| `before_model_callback` | `mini_banco/limitador.py` |
| `before_agent_callback` | `mini_banco/autenticacao.py` |
| interpolação `{chave}` e `{chave?}` na instruction | `mini_banco/prompts.py` |
| `LiteLlm` (ponte pra outros LLMs) | `mini_banco/config.py` |
| `Event` (o stream de tudo) | consumido em `app/nucleo.py` |
| `adk web`, `adk run` (CLI) | terminal |

### É nosso (regra de negócio)

| o que | onde |
|---|---|
| banco SQLite e o seed fictício | `banco/` |
| o corpo das tools (SQL, tabela Price, FAQ) | `mini_banco/tools/` |
| todos os textos de instrução | `mini_banco/prompts.py` |
| a decisão de quais agentes existem | `mini_banco/sub_agents/` |
| a regra "conta vem do State, nunca do LLM" | `mini_banco/tools/comum.py` |
| a interface de chat + API HTTP | `app/server.py`, `app/static/index.html` |
| o servidor MCP de indicadores | `mcp_server/` |
| a suíte de testes | `testes/teste_completo.py` |

### Colando os rótulos no código

```
"Essa parte é Agent."       -> mini_banco/agent.py e mini_banco/sub_agents/
"Essa parte é Tool."        -> mini_banco/tools/
"Essa parte é Session."     -> app/nucleo.py, criar_sessao()
"Essa parte é State."       -> estado_inicial{} e todo tool_context.state[...]
"Essa parte é Memory."      -> memory_service + load_memory
"Essa parte faz multi-agent"-> sub_agents=[...] no agent.py
"Essa parte é Workflow."    -> mini_banco/workflows/raio_x.py
"Essa parte é MCP."         -> mcp_server/ + McpToolset no credito_agent.py
"Essa parte é o Runner."    -> app/nucleo.py, _rodar()
"Essa parte é Callback."    -> mini_banco/limitador.py
```

---

## Bônus: os erros que eu tomei construindo isso

Vale mais que a teoria.

1. **`State' object has no attribute 'pop'`** — `State` não é `dict`. Para limpar, grave `None`.
2. **A tool do MCP nunca era chamada** — faltava "Selic" na `description` do agente e na
   regra do root. *Description ruim = delegação errada.*
3. **O agente perguntava "você confirma?" sozinho**, gastando um turno extra antes de
   chamar a tool. Resolvi com uma linha na instrução: *"NÃO pergunte 'você confirma?'
   por conta própria: CHAME A TOOL DIRETO."*
4. **`LoadMemoryResponse is not JSON serializable`** — nem toda tool devolve `dict`; a
   `load_memory` devolve objeto Pydantic. Precisei de um conversor (`_json_seguro`).
5. **O sub-agente não devolvia a bola** — depois de transferir, o controle **fica** com o
   filho. Se o assunto muda, é preciso mandar ele transferir de volta.
6. **Extrato despejando 40 transações** no contexto — passei a devolver 15 + um resumo
   por categoria já somado. O LLM resume muito melhor com a conta pronta.
7. **`ValueError: Tool 'bloquear_cartao' does not require confirmation`** — o retry por
   429 repetia o nó, e o nó repetido emitia um segundo pedido de confirmação. Duas
   correções: ler o pedido pendente da **Session persistida** (não do stream, que pode
   conter tentativa abortada) e um rate limiter para o 429 nem acontecer. Ver tópico 19.
8. **`PermissionError: o arquivo já está sendo usado por outro processo`** ao rodar
   `banco.seed` com o servidor no ar — `with sqlite3.connect(...)` faz commit mas
   **não fecha** a conexão. Corrigido com `contextlib.closing` em `banco/db.py`.
9. **`gemini-2.5-flash` aparece no `/models` mas devolve 404** "no longer available to
   new users". A lista de modelos não garante acesso — só um `generateContent` de teste
   confirma.
