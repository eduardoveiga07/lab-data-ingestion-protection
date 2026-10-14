"""Verificador reproduzível da Missão 4. Uso: python evidencias/conferir_missao4.py"""
import contextlib
import io
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ingestao"))
sys.path.insert(0, str(RAIZ / "qualidade"))
import aplicar_dia2
import captura
import carga
import criar_origem
import sincronizar
import validar_pedidos

saida, ok = [], True

def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists():
    carga.BRONZE.unlink()
carga.executar(["clientes", "pedidos"])
captura.ligar()
aplicar_dia2.aplicar()
sincronizar.executar()
r = validar_pedidos.executar()
con = sqlite3.connect(carga.BRONZE)
try:
    silver = con.execute("SELECT COUNT(*) FROM silver_pedidos").fetchone()[0]
    quarentena = con.execute("SELECT COUNT(*) FROM quarentena_pedidos WHERE execucao=?", (r["execucao"],)).fetchone()[0]
    motivos = [x[0] for x in con.execute("SELECT motivo FROM quarentena_pedidos WHERE execucao=? ORDER BY linha_lote", (r["execucao"],))]
    ids = [x[0] for x in con.execute("SELECT id FROM silver_pedidos ORDER BY id")]
    bruto = con.execute("SELECT COUNT(*) FROM pedidos_lote WHERE _execucao=?", (r["execucao"],)).fetchone()[0]
finally:
    con.close()

saida.append("1) Contrato e preservação do lote bruto")
checar("contrato lido do YAML", r["contrato"], "pedidos v1")
checar("lote bruto mantido na bronze", bruto, 7)
checar("linhas do lote", r["linhas_lote"], 7)
saida.append("2) Validação linha a linha")
checar("aceitas", r["aceitos"], 2)
checar("quarentena", quarentena, 5)
checar("um motivo por defeito", motivos, [
    "valor abaixo do mínimo: valor_centavos < 0",
    "campo obrigatório ausente: cliente_id",
    "valor fora do domínio: status=enviado",
    "chave repetida: id=110",
    "data no futuro: criado_em > momento da carga",
])
saida.append("3) Resultado na silver")
checar("pedidos na silver", silver, 11)
checar("ids da silver", ids, [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 115])
checar("receita paga validada (centavos)", r["receita_paga_centavos"], 84490)
checar("receita paga sem validação (centavos)", r["receita_sem_validacao_centavos"], 93290)
saida.append(f"Receita validada: {validar_pedidos.reais(r['receita_paga_centavos'])}")
saida.append(f"Receita sem validação: {validar_pedidos.reais(r['receita_sem_validacao_centavos'])}")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
print(texto)
(RAIZ / "evidencias" / "missao4.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
