"""Roda o cenário completo da Missão 1 e confere os números esperados.

Uso:  python evidencias/conferir_missao1.py
Recria a origem e a bronze do zero. Grava o resultado em evidencias/missao1.txt.
"""
import contextlib
import io
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ingestao"))
import aplicar_dia2  # noqa: E402
import carga  # noqa: E402
import criar_origem  # noqa: E402

saida, ok = [], True


def reais(c):
    return f"R$ {c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok &= passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido}, esperado {esperado}")


def totais():
    b = sqlite3.connect(carga.BRONZE)
    um = lambda sql: b.execute(sql).fetchone()[0]
    r = (um("SELECT COUNT(*) FROM clientes"), um("SELECT COUNT(*) FROM pedidos"),
         um("SELECT COUNT(*) FROM navegacao"),
         um("SELECT SUM(valor_centavos) FROM pedidos WHERE status = 'pago'"))
    b.close()
    return r


# estado limpo: dia 1 na origem, bronze vazia
with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists():
    carga.BRONZE.unlink()

saida.append("1) Primeira execução")
r1 = carga.executar()
c, p, n, _ = totais()
checar("bronze (clientes, pedidos, eventos)", (c, p, n), (6, 8, 8))

saida.append("2) Segunda execução, sem mudança na origem")
r2 = carga.executar()
c, p, n, _ = totais()
checar("linhas lidas", r2["total_lidas"], 0)
checar("bronze (clientes, pedidos, eventos)", (c, p, n), (6, 8, 8))

saida.append("3) Depois das mudanças do dia 2")
aplicar_dia2.aplicar()
r3 = carga.executar()
checar("linhas lidas", r3["total_lidas"], 4)
checar("lidas por tabela", r3["lidas"], {"clientes": 2, "pedidos": 2, "navegacao": 0})

saida.append("4) Estado da camada bronze")
c, p, n, receita = totais()
checar("clientes", c, 7)
checar("pedidos", p, 9)
checar("receita paga", reais(receita), "R$ 750,90")

saida.append("5) A cliente 5 foi excluída na origem")
o = sqlite3.connect(carga.ORIGEM)
b = sqlite3.connect(carga.BRONZE)
checar("cliente 5 na origem", o.execute("SELECT COUNT(*) FROM clientes WHERE id = 5").fetchone()[0], 0)
checar("cliente 5 na bronze", b.execute("SELECT COUNT(*) FROM clientes WHERE id = 5").fetchone()[0], 1)
o.close()
b.close()
saida.append("    (anotem: é o ponto de partida da Missão 2: a marca-d'água não vê exclusão)")

saida.append("Extra) Idempotência: apagar as marcas-d'água e reprocessar tudo")
b = sqlite3.connect(carga.BRONZE)
b.execute("DELETE FROM _estado WHERE chave LIKE 'marca_%'")
b.commit()
b.close()
antes = totais()
carga.executar()
checar("totais iguais depois de reprocessar tudo", totais(), antes)

saida.append("RESULTADO: " + ("tudo certo" if ok else "há divergências"))
texto = "\n".join(saida)
print(texto)
(RAIZ / "evidencias" / "missao1.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
