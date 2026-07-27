"""Cria e popula o banco fictício.

Rode com:  python -m banco.seed
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from banco.db import CAMINHO_BANCO, SCHEMA, conectar

# Semente fixa: o banco sai sempre igual, então os testes são reproduzíveis.
random.seed(42)

HOJE = date(2026, 7, 27)

CLIENTES = [
    # id,      nome,               cpf,              email,                  telefone,          nascimento,   score
    ("CLI001", "Matheus Larcher", "123.456.789-00", "matheus@exemplo.com", "(21) 99999-1111", "1995-03-14", 812),
    ("CLI002", "Ana Ribeiro", "987.654.321-00", "ana@exemplo.com", "(11) 98888-2222", "1988-11-02", 640),
    ("CLI003", "Carlos Nunes", "456.123.789-00", "carlos@exemplo.com", "(31) 97777-3333", "1979-06-23", 455),
]

CONTAS = [
    # numero,    cliente, agencia, tipo,       saldo,   limite_especial, aberta_em,   status
    ("12345-6", "CLI001", "0001", "corrente", 8420.75, 3000.0, "2019-04-10", "ativa"),
    ("54321-0", "CLI002", "0001", "corrente", 1250.30, 1500.0, "2021-09-01", "ativa"),
    ("99887-1", "CLI003", "0042", "corrente", -320.15, 800.0, "2015-01-20", "ativa"),
]

CARTOES = [
    # id,      conta,     bandeira,     tipo,      final, status,      limite,  usado,   validade, motivo
    ("CAR001", "12345-6", "Visa", "credito", "4417", "ativo", 12000.0, 3180.40, "11/2029", None),
    ("CAR002", "12345-6", "Elo", "debito", "8802", "ativo", 0.0, 0.0, "05/2028", None),
    ("CAR003", "54321-0", "Mastercard", "credito", "1290", "ativo", 4000.0, 3890.00, "02/2027", None),
    ("CAR004", "99887-1", "Visa", "credito", "7734", "bloqueado", 1500.0, 1500.00, "08/2026", "Bloqueado por atraso de fatura"),
]

EMPRESTIMOS = [
    # id,      conta,     produto,             valor,    taxa,   parcelas, pagas, parcela, data,        status
    ("EMP001", "12345-6", "Crédito Pessoal", 15000.0, 0.0189, 24, 9, 782.41, "2025-10-05", "ativo"),
    ("EMP002", "12345-6", "Crédito Consignado", 8000.0, 0.0135, 36, 36, 279.52, "2022-02-10", "quitado"),
    ("EMP003", "54321-0", "Crédito Pessoal", 5000.0, 0.0239, 18, 4, 336.11, "2026-03-18", "ativo"),
]

PRODUTOS = [
    # codigo,      nome,                 taxa,   min, max, valor_min, valor_max, score_min, descricao
    ("PESSOAL", "Crédito Pessoal", 0.0189, 6, 48, 500.0, 50000.0, 500,
     "Empréstimo livre, sem garantia. Dinheiro cai na conta em até 1 dia útil."),
    ("CONSIGNADO", "Crédito Consignado", 0.0135, 12, 72, 1000.0, 100000.0, 400,
     "Parcela descontada direto da folha/benefício. Juros menores, exige vínculo."),
    ("GARANTIA_VEICULO", "Crédito com Garantia de Veículo", 0.0149, 12, 60, 5000.0, 150000.0, 550,
     "Usa o carro como garantia. Juro baixo, mas o veículo fica alienado."),
    ("CARTAO_PARCELADO", "Parcelamento de Fatura", 0.0899, 2, 12, 200.0, 20000.0, 300,
     "Parcela a fatura do cartão. É o crédito mais caro; use só como último recurso."),
]

DESCRICOES = [
    ("Supermercado Extra", "alimentacao", "debito", (80, 620)),
    ("iFood", "alimentacao", "debito", (25, 180)),
    ("Posto Ipiranga", "transporte", "debito", (100, 350)),
    ("Uber", "transporte", "debito", (12, 90)),
    ("Netflix", "assinatura", "debito", (39, 60)),
    ("Spotify", "assinatura", "debito", (21, 35)),
    ("Farmácia Pacheco", "saude", "debito", (30, 240)),
    ("Pix recebido", "transferencia", "credito", (50, 900)),
    ("Pix enviado", "transferencia", "debito", (50, 900)),
    ("Amazon", "compras", "debito", (45, 780)),
]

# Salário e aluguel de cada conta: entram todo mês em dia fixo, senão o extrato
# de 30 dias sai sem nenhuma entrada e o cliente "parece" não ter renda.
FIXAS = {
    "12345-6": (8719.92, 2439.63),
    "54321-0": (4180.55, 1450.00),
    "99887-1": (2310.40, 980.00),
}


def gerar_transacoes(conta: str, quantidade: int) -> list[tuple]:
    linhas = []

    # 1) fixas mensais dos últimos 3 meses (salário dia 5, aluguel dia 10)
    salario, aluguel = FIXAS[conta]
    for mes in range(3):
        base = HOJE - timedelta(days=30 * mes)
        linhas.append((conta, base.replace(day=5).isoformat(), "Salário", "salario",
                       "credito", round(salario * random.uniform(0.97, 1.03), 2)))
        linhas.append((conta, base.replace(day=10).isoformat(), "Aluguel", "moradia",
                       "debito", aluguel))

    # 2) o resto, aleatório nos últimos 90 dias
    for _ in range(quantidade - len(linhas)):
        desc, cat, tipo, (lo, hi) = random.choice(DESCRICOES)
        dias = random.randint(0, 89)
        data = (HOJE - timedelta(days=dias)).isoformat()
        valor = round(random.uniform(lo, hi), 2)
        linhas.append((conta, data, desc, cat, tipo, valor))
    return linhas


def criar_banco() -> None:
    if CAMINHO_BANCO.exists():
        CAMINHO_BANCO.unlink()

    with conectar() as con:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.executemany("INSERT INTO clientes VALUES (?,?,?,?,?,?,?)", CLIENTES)
        con.executemany("INSERT INTO contas VALUES (?,?,?,?,?,?,?,?)", CONTAS)
        con.executemany("INSERT INTO cartoes VALUES (?,?,?,?,?,?,?,?,?,?)", CARTOES)
        con.executemany("INSERT INTO emprestimos VALUES (?,?,?,?,?,?,?,?,?,?)", EMPRESTIMOS)
        con.executemany("INSERT INTO produtos_credito VALUES (?,?,?,?,?,?,?,?,?)", PRODUTOS)

        transacoes = []
        for numero, *_ in CONTAS:
            transacoes += gerar_transacoes(numero, 40)
        con.executemany(
            "INSERT INTO transacoes (conta_numero, data, descricao, categoria, tipo, valor)"
            " VALUES (?,?,?,?,?,?)",
            transacoes,
        )
        con.commit()

    print(f"Banco criado em {CAMINHO_BANCO}")
    print(f"  {len(CLIENTES)} clientes | {len(CONTAS)} contas | {len(CARTOES)} cartões"
          f" | {len(EMPRESTIMOS)} empréstimos | {len(transacoes)} transações")


if __name__ == "__main__":
    criar_banco()
