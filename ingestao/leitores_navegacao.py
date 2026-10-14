"""Missão 3: leitores independentes do log de navegação.

Cada leitor mantém seu offset em bronze._estado. Offset e efeito são gravados
na mesma transação; uma queda retoma do último evento confirmado.
"""
import sqlite3
from collections import Counter
from datetime import datetime

import carga
from publicar_navegacao import LOG, preparar

BRONZE = carga.BRONZE


def _abrir():
    BRONZE.parent.mkdir(exist_ok=True)
    b = sqlite3.connect(BRONZE)
    b.executescript(carga.SCHEMA_BRONZE)
    b.execute("CREATE TABLE IF NOT EXISTS visitas (pagina TEXT PRIMARY KEY, total INTEGER NOT NULL)")
    b.execute("CREATE TABLE IF NOT EXISTS eventos_por_cliente (cliente TEXT PRIMARY KEY, total INTEGER NOT NULL)")
    return b


def _offset(b, leitor):
    return int(carga._estado(b, f"offset_{leitor}", 0))


def _eventos(offset, limite=None, caminho=LOG):
    preparar(caminho)
    o = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    sql = "SELECT seq, evento_id, cliente_id, ip, pagina, quando FROM log_navegacao WHERE seq > ? ORDER BY seq"
    args = [offset]
    if limite is not None:
        sql += " LIMIT ?"
        args.append(limite)
    rows = o.execute(sql, args).fetchall()
    o.close()
    return rows


def ler_visitas(limite=None):
    """Leitor rápido; limite permite simular interrupção após N eventos."""
    b = _abrir()
    try:
        off = _offset(b, "visitas")
        eventos = _eventos(off, limite)
        for ev in eventos:
            seq, _, _, _, pagina, _ = ev
            b.execute("INSERT INTO visitas(pagina,total) VALUES (?,1) "
                      "ON CONFLICT(pagina) DO UPDATE SET total=total+1", (pagina,))
            carga._guardar(b, "offset_visitas", seq)
        b.commit()
        return {"lidos": len(eventos), "offset": _offset(b, "visitas")}
    except Exception:
        b.rollback()
        raise
    finally:
        b.close()


def ler_bronze(limite=5):
    """Leitor de rajada: consome no máximo `limite` eventos por chamada."""
    b = _abrir()
    try:
        off = _offset(b, "bronze_navegacao")
        eventos = _eventos(off, limite)
        execucao = int(carga._estado(b, "execucao_navegacao", 0)) + 1
        agora = datetime.now().isoformat(timespec="seconds")
        for seq, evento_id, cliente_id, ip, pagina, quando in eventos:
            b.execute(
                "INSERT OR IGNORE INTO navegacao "
                "(evento_id, cliente_id, ip, pagina, quando, _carregado_em, _execucao) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (evento_id, cliente_id, ip, pagina, quando, agora, execucao),
            )
            carga._guardar(b, "offset_bronze_navegacao", seq)
        carga._guardar(b, "execucao_navegacao", execucao)
        b.commit()
        return {"lidos": len(eventos), "offset": _offset(b, "bronze_navegacao")}
    except Exception:
        b.rollback()
        raise
    finally:
        b.close()


def ler_por_cliente(desde_zero=False):
    """Leitor de replay. Começa no offset 0 quando ainda não tem offset salvo."""
    b = _abrir()
    try:
        off = 0 if desde_zero else _offset(b, "por_cliente")
        eventos = _eventos(off)
        for seq, _, cliente_id, _, _, _ in eventos:
            chave = str(cliente_id) if cliente_id is not None else "visitante sem cadastro"
            b.execute("INSERT INTO eventos_por_cliente(cliente,total) VALUES (?,1) "
                      "ON CONFLICT(cliente) DO UPDATE SET total=total+1", (chave,))
            carga._guardar(b, "offset_por_cliente", seq)
        b.commit()
        return {"lidos": len(eventos), "offset": _offset(b, "por_cliente")}
    except Exception:
        b.rollback()
        raise
    finally:
        b.close()


def relatorio():
    b = sqlite3.connect(BRONZE)
    visitas = b.execute("SELECT pagina,total FROM visitas ORDER BY pagina").fetchall()
    por_cliente = b.execute("SELECT cliente,total FROM eventos_por_cliente ORDER BY cliente").fetchall()
    bronze_n = b.execute("SELECT COUNT(*) FROM navegacao").fetchone()[0]
    offsets = dict(b.execute("SELECT chave,valor FROM _estado WHERE chave LIKE 'offset_%'").fetchall())
    b.close()
    return {"visitas": visitas, "por_cliente": por_cliente, "bronze_eventos": bronze_n, "offsets": offsets}


if __name__ == "__main__":
    # Consome tudo que já foi publicado; a execução é idempotente e pode ser repetida.
    while ler_visitas()["lidos"]:
        pass
    while ler_bronze(limite=5)["lidos"]:
        pass
    while ler_por_cliente()["lidos"]:
        pass
    r = relatorio()
    print("visitas por página:")
    for pagina, total in r["visitas"]:
        print(f"  {pagina}: {total}")
    print("eventos por cliente:")
    for cliente, total in r["por_cliente"]:
        print(f"  {cliente}: {total}")
    print(f"eventos na bronze: {r['bronze_eventos']}")
    print(f"offsets: {r['offsets']}")
