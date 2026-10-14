"""Confere a origem contra os números esperados da Missão 0.
Uso:  python evidencias/conferir_missao0.py
Grava o resultado em evidencias/missao0.txt.
"""
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "origem" / "loja.db"

con = sqlite3.connect(DB)
um = lambda sql: con.execute(sql).fetchone()[0]

verificacoes = [
    ("clientes", um("SELECT COUNT(*) FROM clientes"), 6),
    ("pedidos", um("SELECT COUNT(*) FROM pedidos"), 8),
    ("eventos de navegação", um("SELECT COUNT(*) FROM navegacao"), 8),
    ("receita paga (centavos)",
     um("SELECT SUM(valor_centavos) FROM pedidos WHERE status='pago'"), 65500),
]

linhas, ok = [], True
for nome, obtido, esperado in verificacoes:
    passou = obtido == esperado
    ok &= passou
    linhas.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido}, esperado {esperado}")
linhas.append(f"Receita paga: R$ {verificacoes[3][1] / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
linhas.append("RESULTADO: " + ("tudo certo" if ok else "há divergências"))

saida = "\n".join(linhas)
print(saida)
(RAIZ / "evidencias" / "missao0.txt").write_text(saida + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
