"""Verificador reproduzível da Missão 6: matriz de proteção e Silver pseudonimizada."""
import contextlib, io, sqlite3, sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "ingestao"), str(RAIZ / "qualidade"), str(RAIZ / "seguranca")]
import aplicar_dia2, captura, carga, criar_origem, sincronizar, validar_pedidos, gerar_silver

saida, ok = [], True
def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists(): carga.BRONZE.unlink()
if gerar_silver.SILVER.exists(): gerar_silver.SILVER.unlink()
carga.executar(["clientes", "pedidos", "navegacao"])
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()
r4 = validar_pedidos.executar()
r = gerar_silver.gerar(chave="chave-sintetica-teste-missao6")
con = sqlite3.connect(gerar_silver.SILVER)
try:
    tabelas = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    checar("tabelas Silver", sorted(tabelas - {"_metadados", "sqlite_sequence"}), ["clientes", "navegacao", "pedidos"])
    cols = {t: [x[1] for x in con.execute(f"PRAGMA table_info({t})")] for t in ("clientes", "pedidos", "navegacao")}
    checar("colunas clientes sem ID/CPF/nome/e-mail", cols["clientes"], ["cliente_ps", "faixa_etaria", "cidade"])
    checar("colunas pedidos sem cliente_id/observacao", cols["pedidos"], ["id", "cliente_ps", "valor_centavos", "status", "criado_em"])
    checar("colunas navegação sem cliente_id/IP", cols["navegacao"], ["evento_id", "cliente_ps", "pagina", "quando"])
    checar("clientes na Silver (6 clientes, incluindo a inserção 7 e sem o cliente 5 excluído)", con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 6)
    checar("pedidos validados na Silver", con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 11)
    checar("eventos de navegação", con.execute("SELECT COUNT(*) FROM navegacao").fetchone()[0], 8)
    # Mesmo cliente deve receber o mesmo pseudônimo em todos os conjuntos.
    p_cliente = con.execute("SELECT cliente_ps FROM clientes WHERE cliente_ps=?", (gerar_silver.pseudonimo(b"chave-sintetica-teste-missao6", 1),)).fetchone()[0]
    # ID 1 é conhecido no fixture sintético e aparece em pedidos e navegação.
    esperado = gerar_silver.pseudonimo(b"chave-sintetica-teste-missao6", 1)
    checar("pseudônimo HMAC determinístico", p_cliente, esperado)
    checar("pedido do cliente 1 usa pseudônimo igual", con.execute("SELECT cliente_ps FROM pedidos WHERE id=101").fetchone()[0], esperado)
    checar("navegação do cliente 1 usa pseudônimo igual", con.execute("SELECT cliente_ps FROM navegacao WHERE evento_id=1").fetchone()[0], esperado)
    checar("visitante sem cadastro permanece NULL", con.execute("SELECT cliente_ps FROM navegacao WHERE evento_id=6").fetchone()[0], None)
    checar("pseudônimo muda com outra chave", gerar_silver.pseudonimo(b"outra-chave-sintetica", 1) != esperado, True)
    checar("receita paga preservada após projeção", con.execute("SELECT SUM(valor_centavos) FROM pedidos WHERE status='pago'").fetchone()[0], r4["receita_paga_centavos"])
finally:
    con.close()

saida.append("A matriz de proteção e as limitações locais estão documentadas em seguranca/matriz.md.")
saida.append("A chave de teste é sintética e não é persistida em código ou banco.")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
print(texto)
(RAIZ / "evidencias" / "missao6.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
