"""Teste reproduzível da Missão 3. Uso: python evidencias/conferir_missao3.py"""
import contextlib
import csv
import io
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ingestao"))
import aplicar_dia2
import captura
import carga
import criar_origem
import leitores_navegacao as leitores
import publicar_navegacao as produtor
import sincronizar

saida, ok = [], True


def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")


def db_origem(sql):
    o = sqlite3.connect(carga.ORIGEM)
    try:
        return o.execute(sql).fetchone()[0]
    finally:
        o.close()


def csv_parcial(n):
    origem = RAIZ / "dados" / "navegacao.csv"
    with open(origem, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tmp = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False)
    with tmp:
        w = csv.DictWriter(tmp, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows[:n])
    return Path(tmp.name)


def db(sql, params=()):
    b = sqlite3.connect(carga.BRONZE)
    try:
        return b.execute(sql, params).fetchall()
    finally:
        b.close()


# Base reproduzível: Missões 0-2, depois log de navegação vazio.
with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists(): carga.BRONZE.unlink()
carga.executar(["clientes", "pedidos"])
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()
# Limpa log de navegação de uma eventual execução anterior, sem tocar no log CDC.
o = sqlite3.connect(carga.ORIGEM)
o.execute("DROP TABLE IF EXISTS log_navegacao"); o.execute("DELETE FROM sqlite_sequence WHERE name = 'log_navegacao'"); o.commit(); o.close()
produtor.preparar()
saida.append("1) Produtor e log append-only")
parte4 = csv_parcial(4)
try:
    checar("publicar primeiros quatro", produtor.publicar_todos(0, arquivo=parte4), 4)
finally:
    parte4.unlink(missing_ok=True)
checar("log após quatro eventos", db_origem("SELECT COUNT(*) FROM log_navegacao"), 4)

saida.append("2) Leitor rápido interrompido após o quarto evento")
r = leitores.ler_visitas()
checar("visitas lê os quatro eventos", r["lidos"], 4)
checar("offset visitas salvo", r["offset"], 4)
checar("/carrinho parcial", db("SELECT total FROM visitas WHERE pagina='/carrinho'"), [(1,)])

saida.append("3) Bronze acompanha em rajadas de até cinco")
r = leitores.ler_bronze(limite=5)
checar("bronze lê primeira rajada", r["lidos"], 4)
checar("bronze contém quatro eventos", db("SELECT COUNT(*) FROM navegacao"), [(4,)])
# Produtor retoma/publica o CSV completo; os quatro já publicados são ignorados.
checar("publicar restante sem duplicar", produtor.publicar_todos(0), 4)
checar("log mantém oito eventos", db_origem("SELECT COUNT(*) FROM log_navegacao"), 8)
# Enquanto visitas está parado, bronze consome o que falta em rajada.
r = leitores.ler_bronze(limite=5)
checar("bronze lê restante", r["lidos"], 4)
checar("bronze tem oito eventos sem duplicata", db("SELECT COUNT(*) FROM navegacao"), [(8,)])
checar("atraso máximo nesta etapa", 8 - r["offset"], 0)

saida.append("4) Retomada do leitor rápido")
r = leitores.ler_visitas()
checar("visitas retoma só os quatro pendentes", r["lidos"], 4)
checar("offset visitas chega a oito", r["offset"], 8)
visitas = dict(db("SELECT pagina,total FROM visitas"))
checar("contagem por página", visitas, {
    "/produto/tenis": 1, "/carrinho": 2, "/produto/mochila": 1,
    "/produto/relogio": 1, "/produto/fone": 1,
    "/home": 1, "/produto/camiseta": 1,
})
# Novo leitor, ligado após a publicação, lê a história inteira do offset 0.
r = leitores.ler_por_cliente(desde_zero=True)
checar("leitor novo encontra todos", r["lidos"], 8)
por_cliente = dict(db("SELECT cliente,total FROM eventos_por_cliente"))
checar("contagem por cliente", por_cliente, {
    "1": 2, "2": 1, "3": 1, "5": 2, "6": 1, "visitante sem cadastro": 1,
})
checar("log preservado após consumo", db_origem("SELECT COUNT(*) FROM log_navegacao"), 8)
checar("offsets finais independentes", db("SELECT chave,valor FROM _estado WHERE chave IN ('offset_visitas','offset_bronze_navegacao','offset_por_cliente') ORDER BY chave"), [
    ("offset_bronze_navegacao", "8"), ("offset_por_cliente", "8"), ("offset_visitas", "8")
])

texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
print(texto)
(RAIZ / "evidencias" / "missao3.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)