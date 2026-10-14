"""Missão 0: cria o banco da origem e carrega os dados do dia 1.

Uso:  python ingestao/criar_origem.py
Recria origem/loja.db do zero (rodar de novo dá sempre o mesmo resultado).

Sem chave estrangeira entre as tabelas, de propósito: o pedido precisa
sobreviver à exclusão do cliente (Missão 2 e Missão 8).
"""
import csv
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "origem" / "loja.db"
DADOS = RAIZ / "dados"

SCHEMA = """
CREATE TABLE clientes (
    id            INTEGER PRIMARY KEY,
    nome          TEXT NOT NULL,
    email         TEXT NOT NULL,
    cpf           TEXT NOT NULL,
    nascimento    TEXT,
    cidade        TEXT,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE pedidos (
    id             INTEGER PRIMARY KEY,
    cliente_id     INTEGER,             -- sem FOREIGN KEY, de propósito
    valor_centavos INTEGER NOT NULL,
    status         TEXT NOT NULL,
    criado_em      TEXT NOT NULL,
    atualizado_em  TEXT NOT NULL,
    observacao     TEXT
);
CREATE TABLE navegacao (
    evento_id  INTEGER PRIMARY KEY,
    cliente_id INTEGER,                 -- vazio = visitante sem cadastro
    ip         TEXT,
    pagina     TEXT NOT NULL,
    quando     TEXT NOT NULL
);
"""

TIPOS = {
    "clientes": {"id": int},
    "pedidos": {"id": int, "cliente_id": int, "valor_centavos": int},
    "navegacao": {"evento_id": int, "cliente_id": int},
}


def ler_csv(tabela):
    with open(DADOS / f"{tabela}.csv", newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            for col, tipo in TIPOS[tabela].items():
                linha[col] = tipo(linha[col]) if linha[col] != "" else None
            # campo vazio no CSV vira NULL no banco
            yield {k: (v if v != "" else None) for k, v in linha.items()}


def main():
    DB.parent.mkdir(exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    for tabela in ("clientes", "pedidos", "navegacao"):
        linhas = list(ler_csv(tabela))
        cols = list(linhas[0].keys())
        con.executemany(
            f"INSERT INTO {tabela} ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + c for c in cols)})",
            linhas,
        )
        print(f"{tabela}: {len(linhas)} linhas carregadas")
    con.commit()
    con.close()
    print(f"origem pronta em {DB.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
