"""Missão 2, Trilha A: liga a captura de mudanças na origem.

Uso:  python ingestao/captura.py

Cria a tabela `mudancas` (o log) e gatilhos em `clientes` e `pedidos`: cada
INSERT, UPDATE e DELETE vira um evento, na ordem em que aconteceu.

    seq          sequência crescente, nunca reaproveitada (AUTOINCREMENT)
    tabela       clientes ou pedidos
    operacao     INSERT, UPDATE ou DELETE
    chave        id da linha afetada
    dados        a linha inteira DEPOIS da mudança, em JSON
                 (no DELETE fica NULL: ver "Decisões de projeto" no README)

O log só recebe anexações: nenhum código do projeto edita ou apaga um evento.
Ligar a captura de novo não duplica nada (IF NOT EXISTS).
"""
import sqlite3
from pathlib import Path

import carga

ORIGEM = carga.ORIGEM
TABELAS = {t: carga.COLUNAS[t] for t in ("clientes", "pedidos")}

DDL_LOG = """
CREATE TABLE IF NOT EXISTS mudancas (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela        TEXT NOT NULL,
    operacao      TEXT NOT NULL CHECK (operacao IN ('INSERT', 'UPDATE', 'DELETE')),
    chave         INTEGER NOT NULL,
    dados         TEXT,
    registrado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _json(cols):
    return "json_object(" + ", ".join(f"'{c}', NEW.{c}" for c in cols) + ")"


def ligar(caminho=ORIGEM):
    con = sqlite3.connect(caminho)
    con.executescript(DDL_LOG)
    for tabela, cols in TABELAS.items():
        for op, ref in (("INSERT", "NEW"), ("UPDATE", "NEW"), ("DELETE", "OLD")):
            dados = "NULL" if op == "DELETE" else _json(cols)
            con.execute(
                f"CREATE TRIGGER IF NOT EXISTS trg_{tabela}_{op.lower()} "
                f"AFTER {op} ON {tabela} BEGIN "
                f"INSERT INTO mudancas (tabela, operacao, chave, dados) "
                f"VALUES ('{tabela}', '{op}', {ref}.id, {dados}); END;"
            )
    con.commit()
    con.close()


if __name__ == "__main__":
    ligar()
    print("captura ligada: gatilhos em clientes e pedidos, log em mudancas")
