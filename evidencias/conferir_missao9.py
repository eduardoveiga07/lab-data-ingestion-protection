"""Verificador reproduzível da Missão 9: backup, restore e replay de eliminação."""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "ingestao"), str(RAIZ / "qualidade"), str(RAIZ / "seguranca"), str(RAIZ / "privacidade"), str(RAIZ / "resiliencia")]
import aplicar_dia2, captura, carga, criar_origem, sincronizar, validar_pedidos
import publicar_navegacao, leitores_navegacao, gerar_silver, gerar_consumo, esquecer
import backup, restaurar

saida, ok = [], True

def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

def valor(db, sql, args=()):
    con = sqlite3.connect(db)
    try: return con.execute(sql, args).fetchone()[0]
    finally: con.close()

def dados_banco(path):
    vals=[]
    con=sqlite3.connect(path)
    try:
        tabs=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for tab in tabs:
            for row in con.execute(f'SELECT * FROM "{tab}"'):
                vals.extend(str(v) for v in row if v is not None)
    finally: con.close()
    return vals

# Preparar um cenário sintético pré-eliminação e remover evidência antiga do teste.
lista = RAIZ / "privacidade" / "lista_eliminacao.jsonl"
lista_backup = lista.read_bytes() if lista.exists() else None
if lista.exists(): lista.unlink()
with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
for db in (carga.BRONZE, gerar_silver.SILVER, gerar_consumo.GOLD):
    if db.exists(): db.unlink()
carga.executar(["clientes", "pedidos", "navegacao"])
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()
validar_pedidos.executar()
gerar_silver.gerar(chave="chave-sintetica-teste-missao9")
gerar_consumo.gerar()
publicar_navegacao.publicar_todos(intervalo=0)
while leitores_navegacao.ler_visitas()["lidos"]: pass
while leitores_navegacao.ler_bronze(limite=5)["lidos"]: pass
while leitores_navegacao.ler_por_cliente()["lidos"]: pass

# O snapshot é anterior à eliminação: é o cenário que pode ressuscitar dados pessoais.
temp_root = Path(tempfile.mkdtemp(prefix="teste_missao9_", dir=RAIZ / "resiliencia"))
snapshot = temp_root / "snapshot_pre_eliminacao"
try:
    cri = backup.criar(snapshot)
    checar("snapshot inclui os quatro bancos", cri["bancos"], 4)
    checar("manifesto registra os quatro bancos", len(json.loads((snapshot / "manifesto.json").read_text(encoding="utf-8"))["bancos"]), 4)
    hashes_validos = restaurar.validar(snapshot)["formato"] == 1
    checar("integridade SHA-256 antes da restauração", hashes_validos, True)

    # Eliminar depois do snapshot, deixando o registro externo de supressão sobreviver.
    esquecer.esquecer(5)
    checar("eliminação remove dados de navegação na origem", valor(carga.ORIGEM, "SELECT COUNT(*) FROM navegacao WHERE cliente_id=5"), 0)
    checar("lista de eliminação existe fora do snapshot", lista.exists(), True)

    # Restaura snapshot antigo. A restauração deve reconhecer e reaplicar a lista externa.
    os.environ["CHAVE_PSEUDONIMO"] = "chave-sintetica-teste-missao9"
    inicio_rto = time.perf_counter()
    resultado = restaurar.restaurar(snapshot, reconstruir=True)
    rto_segundos = time.perf_counter() - inicio_rto
    checar("uma eliminação foi reaplicada após restore", resultado["pedidos_reaplicados"], 1)
    checar("Silver e Gold reconstruídas", resultado["silver_gold_reconstruidas"], True)

    termos = ["Elisa", "555.555.555-55", "(13) 90000-0005", "203.0.113.55", "elisa.moura@example.com"]
    for rel in ("origem/loja.db", "camadas/bronze.db", "camadas/silver.db"):
        achados = [x for x in termos if any(x in v for v in dados_banco(RAIZ / rel))]
        checar(f"sem dados identificáveis após restore em {rel}", achados, [])
    checar("pedido 106 permanece pago e desvinculado", tuple(sqlite3.connect(carga.ORIGEM).execute("SELECT cliente_id,valor_centavos,status,observacao FROM pedidos WHERE id=106").fetchone()), (None, 15900, "pago", None))
    checar("total Gold preserva R$ 844,90", valor(gerar_consumo.GOLD, "SELECT valor_centavos FROM resumo_consumo WHERE indicador='receita_paga_total_centavos'"), 84490)
    checar("cliente eliminado não reaparece na Silver", valor(gerar_silver.SILVER, "SELECT COUNT(*) FROM clientes WHERE cliente_ps=?", (gerar_silver.pseudonimo(b"chave-sintetica-teste-missao9", 5),)), 0)
    checar("ledger de eliminação foi reconstruído na Bronze", valor(carga.BRONZE, "SELECT COUNT(*) FROM lista_eliminacao"), 1)

    # Teste negativo: um arquivo adulterado precisa ser recusado antes da restauração.
    alterado = temp_root / "snapshot_adulterado"
    shutil.copytree(snapshot, alterado)
    with (alterado / "gold.db").open("ab") as f: f.write(b"alteracao")
    bloqueado = False
    try: restaurar.validar(alterado)
    except ValueError: bloqueado = True
    checar("snapshot com hash divergente é bloqueado", bloqueado, True)
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
    # Preservar a lista que existia antes do teste; em uso normal ela é persistente.
    if lista_backup is None:
        if lista.exists(): lista.unlink()
    else:
        lista.write_bytes(lista_backup)

saida.append(f"RTO observado no ensaio (restauração + replay + reconstrução): {rto_segundos:.3f} s; medição local, não SLA de produção.")
saida.append("Decisão: a lista de eliminação fica fora do snapshot e é reaplicada antes de reconstruir Silver/Gold.")
saida.append("Limite: o script valida integridade e restauração local; off-site, WORM/imutabilidade e cofre da chave exigem serviços externos.")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
(RAIZ / "evidencias" / "missao9.txt").write_text(texto + "\n", encoding="utf-8")
print(texto)
sys.exit(0 if ok else 1)
