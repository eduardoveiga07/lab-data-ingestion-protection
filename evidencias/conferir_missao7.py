"""Verificador reproduzível da Missão 7: generalização, K e Gold."""
import contextlib, io, sqlite3, sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "ingestao"), str(RAIZ / "qualidade"), str(RAIZ / "seguranca"), str(RAIZ / "privacidade")]
import aplicar_dia2, captura, carga, criar_origem, sincronizar, validar_pedidos, gerar_silver, gerar_consumo

saida, ok = [], True
def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
for db in (carga.BRONZE, gerar_silver.SILVER, gerar_consumo.GOLD):
    if db.exists(): db.unlink()
carga.executar(["clientes", "pedidos", "navegacao"])
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()
r4 = validar_pedidos.executar()
r6 = gerar_silver.gerar(chave="chave-sintetica-teste-missao7")
r7 = gerar_consumo.gerar()
con = sqlite3.connect(gerar_silver.SILVER)
try:
    cols = [x[1] for x in con.execute("PRAGMA table_info(clientes)")]
    checar("Silver generaliza nascimento e não guarda data exata", cols, ["cliente_ps", "faixa_etaria", "cidade"])
    distribuicao = dict(con.execute("SELECT faixa_etaria, COUNT(*) FROM clientes GROUP BY faixa_etaria"))
    checar("distribuição das faixas etárias", distribuicao, {"25-34": 3, "35-44": 2, "45-54": 1})
    checar("clientes na Silver", con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 6)
    checar("pedidos validados na Silver", con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 11)
    checar("receita paga na Silver (centavos)", con.execute("SELECT SUM(valor_centavos) FROM pedidos WHERE status='pago'").fetchone()[0], 84490)
finally: con.close()
con = sqlite3.connect(gerar_consumo.GOLD)
try:
    perfis = con.execute("SELECT cidade,faixa_etaria,quantidade_pessoas FROM k_anonimato ORDER BY cidade,faixa_etaria").fetchall()
    checar("quatro combinações cidade + faixa etária têm uma pessoa", sum(1 for _,_,n in perfis if n == 1), 4)
    cidade = {r[0]: r[1:] for r in con.execute("SELECT cidade,numero_clientes,receita_paga_centavos,suprimida FROM receita_por_cidade")}
    checar("Santos: 3 clientes e R$ 545,00", cidade.get("Santos"), (3, 54500, 0))
    checar("Sorocaba: 2 clientes e R$ 95,90", cidade.get("Sorocaba"), (2, 9590, 0))
    checar("Campinas suprimida", cidade.get("Campinas"), (None, None, 1))
    checar("total geral mantém receita da cidade suprimida e pedido 106", con.execute("SELECT valor_centavos FROM resumo_consumo WHERE indicador='receita_paga_total_centavos'").fetchone()[0], 84490)
    con_silver = sqlite3.connect(gerar_silver.SILVER)
    try:
        n_cidades_k3 = con_silver.execute("SELECT COUNT(*) FROM (SELECT cidade FROM clientes GROUP BY cidade HAVING COUNT(DISTINCT cliente_ps) < 3)").fetchone()[0]
    finally: con_silver.close()
    checar("com K=3, Sorocaba e Campinas seriam suprimidas", n_cidades_k3, 2)
finally: con.close()
saida.append("Nota: pedido 106 continua no total geral, mas não é atribuído a uma cidade porque o cadastro do cliente 5 foi excluído.")
saida.append("A visão de consumo expõe cidade, número de clientes e receita apenas quando o grupo atende K=2; nos grupos suprimidos, contagem e receita ficam NULL.")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
print(texto)
(RAIZ / "evidencias" / "missao7.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
