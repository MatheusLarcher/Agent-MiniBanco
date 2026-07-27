-- ============================================================
--  Mini Banco com IA — schema SQLite (dados 100% fictícios)
-- ============================================================
-- NADA aqui é Google ADK. É só o "banco de verdade" que as
-- Tools vão consultar. O ADK nunca fala com o SQLite direto:
-- ele chama a Tool, e a Tool fala com o banco.

DROP TABLE IF EXISTS transacoes;
DROP TABLE IF EXISTS emprestimos;
DROP TABLE IF EXISTS cartoes;
DROP TABLE IF EXISTS contas;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS produtos_credito;

CREATE TABLE clientes (
    id          TEXT PRIMARY KEY,          -- CLI001
    nome        TEXT NOT NULL,
    cpf         TEXT NOT NULL,
    email       TEXT NOT NULL,
    telefone    TEXT NOT NULL,
    nascimento  TEXT NOT NULL,
    score       INTEGER NOT NULL           -- score de crédito 0..1000
);

CREATE TABLE contas (
    numero            TEXT PRIMARY KEY,    -- 12345-6
    cliente_id        TEXT NOT NULL REFERENCES clientes(id),
    agencia           TEXT NOT NULL,
    tipo              TEXT NOT NULL,       -- corrente | poupanca
    saldo             REAL NOT NULL,
    limite_especial   REAL NOT NULL,
    aberta_em         TEXT NOT NULL,
    status            TEXT NOT NULL        -- ativa | bloqueada
);

CREATE TABLE cartoes (
    id            TEXT PRIMARY KEY,        -- CAR001
    conta_numero  TEXT NOT NULL REFERENCES contas(numero),
    bandeira      TEXT NOT NULL,
    tipo          TEXT NOT NULL,           -- credito | debito
    final         TEXT NOT NULL,           -- 4 últimos dígitos
    status        TEXT NOT NULL,           -- ativo | bloqueado | cancelado
    limite        REAL NOT NULL,
    limite_usado  REAL NOT NULL,
    validade      TEXT NOT NULL,
    motivo_bloqueio TEXT
);

CREATE TABLE transacoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_numero  TEXT NOT NULL REFERENCES contas(numero),
    data          TEXT NOT NULL,           -- YYYY-MM-DD
    descricao     TEXT NOT NULL,
    categoria     TEXT NOT NULL,
    tipo          TEXT NOT NULL,           -- credito (entrada) | debito (saída)
    valor         REAL NOT NULL            -- sempre positivo; o sinal vem do tipo
);

CREATE TABLE emprestimos (
    id              TEXT PRIMARY KEY,      -- EMP001
    conta_numero    TEXT NOT NULL REFERENCES contas(numero),
    produto         TEXT NOT NULL,
    valor_contratado REAL NOT NULL,
    taxa_mes        REAL NOT NULL,         -- 0.0189 = 1,89% a.m.
    parcelas        INTEGER NOT NULL,
    parcelas_pagas  INTEGER NOT NULL,
    valor_parcela   REAL NOT NULL,
    contratado_em   TEXT NOT NULL,
    status          TEXT NOT NULL          -- ativo | quitado
);

CREATE TABLE produtos_credito (
    codigo      TEXT PRIMARY KEY,          -- PESSOAL
    nome        TEXT NOT NULL,
    taxa_mes    REAL NOT NULL,
    prazo_min   INTEGER NOT NULL,
    prazo_max   INTEGER NOT NULL,
    valor_min   REAL NOT NULL,
    valor_max   REAL NOT NULL,
    score_minimo INTEGER NOT NULL,
    descricao   TEXT NOT NULL
);
