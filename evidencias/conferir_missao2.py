"""Roda o cenário completo da Missão 2 e confere os números esperados.

Uso:  python evidencias/conferir_missao2.py
Recria a origem e a bronze do zero. Grava o resultado em evidencias/missao2.txt.
"""
import contextlib
import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ingestao"))
import aplicar_dia2  # noqa: E402
import captura  # noqa: E402
import carga  # noqa: E402
import criar_origem  # noqa: E402
import sincronizar  # noqa: E402

saida, ok = [], True


def reais(c):
    return f"R$ {c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok &= passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido}, esperado {esperado}")


def bronze_q(sql):
    b = sqlite3.connect(carga.BRONZE)
    r = b.execute(sql).fetchall()
    b.close()
    return r


def totais():
    um = lambda sql: bronze_q(sql)[0][0]
    return (um("SELECT COUNT(*) FROM clientes"), um("SELECT COUNT(*) FROM pedidos"),
            um("SELECT SUM(valor_centavos) FROM pedidos WHERE status = 'pago'"))


def impressao():
    """Resumo do conteúdo de clientes e pedidos, sem as colunas de controle."""
    partes = []
    for t in ("clientes", "pedidos"):
        cols = ", ".join(carga.COLUNAS[t])
        partes.append(bronze_q(f"SELECT {cols} FROM {t} ORDER BY id"))
    return hashlib.sha256(json.dumps(partes).encode()).hexdigest()[:12]


# 0) estado do dia 1: origem e bronze do dia 1 (a carga da Missão 1 serve de foto inicial)
with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists():
    carga.BRONZE.unlink()
carga.executar()
saida.append("0) Ponto de partida: origem e bronze no estado do dia 1")
checar("bronze (clientes, pedidos, receita paga)", totais(), (6, 8, 65500))

# 1) liga a captura e aplica o dia 2
captura.ligar()
o = sqlite3.connect(carga.ORIGEM)
checar("log vazio depois de ligar a captura", o.execute("SELECT COUNT(*) FROM mudancas").fetchone()[0], 0)
o.close()
aplicar_dia2.aplicar()

saida.append("1) O log da origem")
o = sqlite3.connect(carga.ORIGEM)
log = o.execute("SELECT seq, tabela, operacao, chave, dados FROM mudancas ORDER BY seq").fetchall()
o.close()
checar("eventos registrados", len(log), 5)
checar("ordem (tabela, operação, chave)", [(t, op, ch) for _, t, op, ch, _ in log], [
    ("pedidos", "UPDATE", 105), ("clientes", "UPDATE", 3), ("clientes", "INSERT", 7),
    ("pedidos", "INSERT", 109), ("clientes", "DELETE", 5)])
checar("sequências crescentes sem buraco", [s for s, *_ in log], [1, 2, 3, 4, 5])
saida.append("    conteúdo do log:")
for seq, t, op, ch, dados in log:
    saida.append(f"    {seq} | {t:<8} | {op:<6} | chave {ch:<3} | {dados}")

# 2) sincroniza
saida.append("2) Sincronizar a bronze com o log")
r = sincronizar.executar()
checar("eventos aplicados", r["aplicados"], 5)
checar("offset salvo", r["offset"], 5)
c, p, receita = totais()
checar("clientes na bronze (sem a cliente 5)", c, 6)
checar("cliente 5 na bronze", bronze_q("SELECT COUNT(*) FROM clientes WHERE id = 5")[0][0], 0)
checar("pedidos na bronze", p, 9)
checar("e-mail do cliente 3", bronze_q("SELECT email FROM clientes WHERE id = 3")[0][0], "carla.n@example.com")
checar("pedido 106 continua lá", bronze_q("SELECT COUNT(*) FROM pedidos WHERE id = 106")[0][0], 1)
checar("receita paga", reais(receita), "R$ 750,90")

# 3) retomar do offset e reaplicar
saida.append("3) Retomada e reaplicação")
r2 = sincronizar.executar()
checar("segunda sincronização aplica", r2["aplicados"], 0)
antes = (totais(), impressao())
r3 = sincronizar.executar(desde=0)
checar("reaplicando desde o primeiro evento, eventos reaplicados", r3["aplicados"], 5)
checar("mesmos números", totais(), antes[0])
checar("mesmo conteúdo (impressão das tabelas)", impressao(), antes[1])
checar("offset não recuou", r3["offset"], 5)

saida.append("RESULTADO: " + ("tudo certo" if ok else "há divergências"))
texto = "\n".join(saida)
print(texto)
(RAIZ / "evidencias" / "missao2.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
