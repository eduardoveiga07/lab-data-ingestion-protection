"""Verificador reproduzível da Missão 8: direito de eliminação e evidência sem PII."""
import contextlib
import io
import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "ingestao"), str(RAIZ / "qualidade"), str(RAIZ / "seguranca"), str(RAIZ / "privacidade")]
import aplicar_dia2, captura, carga, criar_origem, sincronizar, validar_pedidos, gerar_silver, gerar_consumo
import publicar_navegacao, leitores_navegacao, esquecer

saida, ok = [], True

def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

def db_values(path):
    if not path.exists(): return []
    con = sqlite3.connect(path)
    values = []
    for (tab,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in con.execute(f'SELECT * FROM "{tab}"'):
            values.extend(str(v) for v in row if v is not None)
    con.close()
    return values

with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
for db in (carga.BRONZE, gerar_silver.SILVER, gerar_consumo.GOLD):
    if db.exists(): db.unlink()
carga.executar(["clientes", "pedidos", "navegacao"])
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()
validar_pedidos.executar()
gerar_silver.gerar(chave="chave-sintetica-teste-missao8")
gerar_consumo.gerar()
# Publica e consome todos os oito eventos para testar as duas moradas de log e os agregados dos leitores.
publicar_navegacao.publicar_todos(intervalo=0)
while leitores_navegacao.ler_visitas()["lidos"]: pass
while leitores_navegacao.ler_bronze(limite=5)["lidos"]: pass
while leitores_navegacao.ler_por_cliente()["lidos"]: pass
# Silver/Gold são geradas antes de apagar, como em um pipeline ativo.
res_antes = sqlite3.connect(gerar_consumo.GOLD).execute(
    "SELECT valor_centavos FROM resumo_consumo WHERE indicador='receita_paga_total_centavos'"
).fetchone()[0]

r1 = esquecer.esquecer(5)
r2 = esquecer.esquecer(5)
checar("segunda execução é reconhecida como repetição", r2["repetido"], True)

# Contagens e valores em cada morada ativa.
for rel, tab, esperado in [
    ("origem/loja.db", "clientes", 6), ("origem/loja.db", "pedidos", 9),
    ("origem/loja.db", "navegacao", 6), ("origem/loja.db", "log_navegacao", 6),
    ("camadas/bronze.db", "clientes", 6), ("camadas/bronze.db", "pedidos", 9),
    ("camadas/bronze.db", "navegacao", 6), ("camadas/silver.db", "clientes", 6),
    ("camadas/silver.db", "pedidos", 11), ("camadas/silver.db", "navegacao", 6),
]:
    path = RAIZ / rel
    con = sqlite3.connect(path)
    n = con.execute(f'SELECT COUNT(*) FROM "{tab}"').fetchone()[0]
    con.close()
    checar(f"{rel}:{tab} contém {esperado} linhas", n, esperado)

con = sqlite3.connect(carga.ORIGEM)
checar("pedido 106 continua pago e sem cliente/observação", con.execute(
    "SELECT cliente_id,valor_centavos,status,observacao FROM pedidos WHERE id=106"
).fetchone(), (None, 15900, "pago", None))
checar("CDC conserva tombstone mínimo de cliente 5", con.execute(
    "SELECT operacao,dados FROM mudancas WHERE tabela='clientes' AND chave=5 ORDER BY seq DESC LIMIT 1"
).fetchone(), ("DELETE", None))
checar("nenhum evento de navegação do cliente 5 no log", con.execute(
    "SELECT COUNT(*) FROM log_navegacao WHERE cliente_id=5"
).fetchone()[0], 0)
con.close()

con = sqlite3.connect(carga.BRONZE)
checar("agregado por cliente não guarda chave 5", con.execute(
    "SELECT COUNT(*) FROM eventos_por_cliente WHERE cliente='5'"
).fetchone()[0], 0)
checar("agregado de visitas soma seis eventos", con.execute("SELECT COALESCE(SUM(total),0) FROM visitas").fetchone()[0], 6)
checar("lista de eliminação contém um registro", con.execute("SELECT COUNT(*) FROM lista_eliminacao").fetchone()[0], 1)
con.close()

con = sqlite3.connect(gerar_consumo.GOLD)
res_depois = con.execute("SELECT valor_centavos FROM resumo_consumo WHERE indicador='receita_paga_total_centavos'").fetchone()[0]
checar("receita Gold não muda", res_depois, res_antes)
checar("receita paga permanece R$ 844,90", res_depois, 84490)
checar("visão por cidade permanece igual ao baseline", dict(con.execute(
    "SELECT cidade, (numero_clientes, receita_paga_centavos, suprimida) FROM receita_por_cidade"
)) if False else con.execute("SELECT cidade,numero_clientes,receita_paga_centavos,suprimida FROM receita_por_cidade ORDER BY cidade").fetchall(),
    [("Campinas", None, None, 1), ("Santos", 3, 54500, 0), ("Sorocaba", 2, 9590, 0)])
con.close()

# Busca exata nos bancos ativos; a evidência deliberadamente não repete os valores pesquisados.
termos = ["Elisa", "555.555.555-55", "(13) 90000-0005", "203.0.113.55", "elisa.moura@example.com"]
for rel in ("origem/loja.db", "camadas/bronze.db", "camadas/silver.db"):
    vals = db_values(RAIZ / rel)
    achados = [term for term in termos if any(term in v for v in vals)]
    checar(f"busca de dados do titular em {rel} sem achados", achados, [])

# Evidência estruturada contém só hash de solicitação, timestamp e moradas.
lista = (RAIZ / "privacidade" / "lista_eliminacao.jsonl").read_text(encoding="utf-8").splitlines()
obj = [json.loads(x) for x in lista if x.strip()]
checar("arquivo de evidência tem um pedido", len(obj), 1)
checar("evidência não inclui identificadores diretos", any(term in json.dumps(obj, ensure_ascii=False) for term in termos), False)
checar("inventário cobre pelo menos seis moradas", r1["moradas_tratadas"] >= 6, True)

saida.append("Decisão: o pedido 106 permanece na receita geral, mas foi desvinculado do titular e teve o texto livre limpo.")
saida.append("Limite documentado: cópias imutáveis expiram conforme retenção e recebem a lista de eliminação antes de voltar ao serviço.")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
(RAIZ / "evidencias" / "missao8.txt").write_text(texto + "\n", encoding="utf-8")
print(texto)
sys.exit(0 if ok else 1)
