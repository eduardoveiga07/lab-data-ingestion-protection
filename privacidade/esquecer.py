"""Missão 8: executa eliminação idempotente para um cliente.

Uso: python privacidade/esquecer.py 5
A lista de eliminação registra somente uma chave derivada, data e moradas tratadas.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "origem" / "loja.db"
BRONZE = RAIZ / "camadas" / "bronze.db"
SILVER = RAIZ / "camadas" / "silver.db"
GOLD = RAIZ / "camadas" / "gold.db"
LISTA_JSONL = RAIZ / "privacidade" / "lista_eliminacao.jsonl"
MORADAS = [
    "origem.clientes", "origem.pedidos:106", "origem.navegacao",
    "origem.log_navegacao", "origem.mudancas:tombstone_minimo",
    "bronze.clientes", "bronze.pedidos:106", "bronze.navegacao",
    "bronze.visitas", "bronze.eventos_por_cliente", "bronze.pedidos_lote",
    "bronze.quarentena_pedidos", "bronze.silver_pedidos",
    "silver.clientes", "silver.pedidos:106", "silver.navegacao",
    "gold.agregados_preservados", "backups:expiracao_e_reaplicacao_da_lista",
]


def _con(path):
    if not path.exists():
        return None
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def _tem_tabela(c, tabela):
    return c is not None and c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
    ).fetchone() is not None


def _tem_coluna(c, tabela, coluna):
    return _tem_tabela(c, tabela) and coluna in {
        r[1] for r in c.execute(f'PRAGMA table_info("{tabela}")')
    }


def _limpar_pedido(c, tabela, cliente_id):
    if not _tem_tabela(c, tabela):
        return
    cols = {r[1] for r in c.execute(f'PRAGMA table_info("{tabela}")')}
    if "id" not in cols or "cliente_id" not in cols:
        return
    sets = []
    if "cliente_id" in cols:
        sets.append("cliente_id = NULL")
    if "observacao" in cols:
        sets.append("observacao = NULL")
    if sets:
        c.execute(f'UPDATE "{tabela}" SET {", ".join(sets)} WHERE id=106 AND cliente_id=?', (cliente_id,))


def _hash_chave(cliente_id):
    return hashlib.sha256(f"pedido-de-eliminacao:cliente:{int(cliente_id)}".encode()).hexdigest()[:24]


def esquecer(cliente_id):
    cliente_id = int(cliente_id)
    if cliente_id < 1:
        raise ValueError("id do cliente deve ser positivo")
    if not ORIGEM.exists() or not BRONZE.exists():
        raise FileNotFoundError("origem e Bronze precisam existir; execute as missões anteriores primeiro")

    # A lista de eliminação é guardada na Bronze, sem ID original nem dado pessoal.
    b = sqlite3.connect(BRONZE)
    b.execute("""CREATE TABLE IF NOT EXISTS lista_eliminacao (
        chave_pedido TEXT PRIMARY KEY, executado_em TEXT NOT NULL, moradas_json TEXT NOT NULL
    )""")
    chave = _hash_chave(cliente_id)
    existente = b.execute("SELECT executado_em, moradas_json FROM lista_eliminacao WHERE chave_pedido=?", (chave,)).fetchone()
    if existente:
        # Repetição idempotente: reexecuta as limpezas, sem criar novo registro de evidência.
        data_execucao = existente[0]
    else:
        data_execucao = datetime.now(timezone.utc).isoformat(timespec="seconds")

    o = sqlite3.connect(ORIGEM)
    s = _con(SILVER)
    try:
        # Origem operacional: limpar texto livre e desvincular pedido financeiro.
        _limpar_pedido(o, "pedidos", cliente_id)
        # O cadastro pode já ter sido apagado pelo CDC na Missão 2.
        o.execute("DELETE FROM clientes WHERE id=?", (cliente_id,))
        # Remove eventos identificáveis de navegação, inclusive seus IPs.
        if _tem_tabela(o, "navegacao"):
            o.execute("DELETE FROM navegacao WHERE cliente_id=?", (cliente_id,))
        if _tem_tabela(o, "log_navegacao"):
            o.execute("DELETE FROM log_navegacao WHERE cliente_id=?", (cliente_id,))
        # Mantém o tombstone CDC mínimo; não remove nem reescreve histórico de eventos.
        # Se houver payload que contenha a chave do titular em tabelas de evento, removemos payloads
        # de cliente e navegação, preservando apenas o evento DELETE de chave.
        if _tem_tabela(o, "mudancas"):
            o.execute("DELETE FROM mudancas WHERE tabela='clientes' AND chave=? AND operacao!='DELETE'", (cliente_id,))
        o.commit()

        # Bronze: todos os destinos brutos ativos e as tabelas auxiliares do leitor/validador.
        b.execute("DELETE FROM clientes WHERE id=?", (cliente_id,))
        _limpar_pedido(b, "pedidos", cliente_id)
        if _tem_tabela(b, "navegacao"):
            b.execute("DELETE FROM navegacao WHERE cliente_id=?", (cliente_id,))
        if _tem_tabela(b, "pedidos_lote"):
            _limpar_pedido(b, "pedidos_lote", cliente_id)
        if _tem_tabela(b, "quarentena_pedidos"):
            _limpar_pedido(b, "quarentena_pedidos", cliente_id)
        if _tem_tabela(b, "silver_pedidos"):
            _limpar_pedido(b, "silver_pedidos", cliente_id)
        # A observação do pedido 106 pode estar em quarentena/bronze e o cliente_id pode
        # ser NULL em uma execução anterior; limpa a observação do pedido por sua chave de negócio.
        for tab in ("pedidos", "pedidos_lote", "quarentena_pedidos", "silver_pedidos"):
            if _tem_tabela(b, tab):
                cols = {r[1] for r in b.execute(f'PRAGMA table_info("{tab}")')}
                if "observacao" in cols and "id" in cols:
                    b.execute(f'UPDATE "{tab}" SET observacao=NULL WHERE id=106')
                elif "observacao" in cols and "linha_lote" in cols:
                    b.execute(f'UPDATE "{tab}" SET observacao=NULL WHERE cliente_id=?', (cliente_id,))

        # Recalcula os agregados dos leitores a partir do log remanescente. Offset avança até
        # o maior seq existente para que leitores antigos não tentem reler eventos apagados.
        if _tem_tabela(b, "visitas"):
            b.execute("DELETE FROM visitas")
        if _tem_tabela(b, "eventos_por_cliente"):
            b.execute("DELETE FROM eventos_por_cliente")
        max_seq = 0
        if _tem_tabela(o, "log_navegacao"):
            max_seq = o.execute("SELECT COALESCE(MAX(seq),0) FROM log_navegacao").fetchone()[0]
            rows = o.execute("SELECT cliente_id,pagina FROM log_navegacao ORDER BY seq").fetchall()
            if _tem_tabela(b, "visitas"):
                for r in rows:
                    b.execute("INSERT INTO visitas(pagina,total) VALUES (?,1) ON CONFLICT(pagina) DO UPDATE SET total=total+1", (r[1],))
            if _tem_tabela(b, "eventos_por_cliente"):
                for r in rows:
                    k = str(r[0]) if r[0] is not None else "visitante sem cadastro"
                    b.execute("INSERT INTO eventos_por_cliente(cliente,total) VALUES (?,1) ON CONFLICT(cliente) DO UPDATE SET total=total+1", (k,))
        if _tem_tabela(b, "_estado"):
            for k in ("offset_visitas", "offset_por_cliente"):
                b.execute("INSERT INTO _estado(chave,valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, str(max_seq)))
        b.commit()

        # Silver: captura o pseudônimo a partir do pedido 106 antes de remover a relação.
        # Não precisamos nem armazenamos a chave HMAC para apagar a referência existente.
        if s is not None:
            ps_row = s.execute("SELECT cliente_ps FROM pedidos WHERE id=106").fetchone()
            ps = ps_row[0] if ps_row else None
            if ps:
                s.execute("DELETE FROM navegacao WHERE cliente_ps=?", (ps,))
                s.execute("DELETE FROM clientes WHERE cliente_ps=?", (ps,))
            s.execute("UPDATE pedidos SET cliente_ps=NULL WHERE id=106")
            s.commit()
            s.close()

        # Gold não contém identificadores diretos. O pedido 106 continua no total pago.
        if not existente:
            b.execute("INSERT INTO lista_eliminacao VALUES (?,?,?)", (chave, data_execucao, json.dumps(MORADAS, ensure_ascii=False)))
            b.commit()
        b.close()
        # Arquivo de lista espelha apenas a chave derivada e a evidência de moradas.
        LISTA_JSONL.parent.mkdir(parents=True, exist_ok=True)
        linhas = []
        if LISTA_JSONL.exists():
            linhas = [x for x in LISTA_JSONL.read_text(encoding="utf-8").splitlines() if x.strip()]
        if not any(json.loads(x).get("chave_pedido") == chave for x in linhas):
            linhas.append(json.dumps({"chave_pedido": chave, "executado_em": data_execucao, "moradas": MORADAS}, ensure_ascii=False))
            LISTA_JSONL.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return {"chave_pedido": chave, "executado_em": data_execucao, "moradas_tratadas": len(MORADAS), "repetido": bool(existente)}
    finally:
        o.close()
        if s is not None and s: 
            try: s.close()
            except Exception: pass
        try: b.close()
        except Exception: pass


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Executa o direito de eliminação para um cliente.")
    p.add_argument("cliente_id", type=int, help="ID do cliente a esquecer")
    a = p.parse_args()
    r = esquecer(a.cliente_id)
    print(f"Pedido processado: chave={r['chave_pedido']}; moradas={r['moradas_tratadas']}; repetido={r['repetido']}")
