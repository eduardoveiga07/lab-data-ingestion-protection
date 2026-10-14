"""Missão 6: projeta dados para a Silver com pseudonimização consistente.

Uso (Linux/macOS): CHAVE_PSEUDONIMO='segredo-local' python seguranca/gerar_silver.py
PowerShell: $env:CHAVE_PSEUDONIMO='segredo-local'; python seguranca/gerar_silver.py
A chave deve vir do ambiente/gerenciador de segredos; nunca é gravada no banco.
"""
import hashlib
import hmac
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BRONZE = RAIZ / "camadas" / "bronze.db"
SILVER = RAIZ / "camadas" / "silver.db"


def pseudonimo(chave: bytes, cliente_id):
    if cliente_id is None or cliente_id == "":
        return None
    mensagem = ("cliente:" + str(int(cliente_id))).encode("utf-8")
    return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()


def faixa_etaria(nascimento, referencia=None):
    """Generaliza a data de nascimento em faixas exigidas pelo laboratório."""
    if not nascimento:
        return None
    ref = referencia or date.today()
    nasc = date.fromisoformat(str(nascimento)[:10])
    idade = ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))
    if 25 <= idade <= 34:
        return "25-34"
    if 35 <= idade <= 44:
        return "35-44"
    if 45 <= idade <= 54:
        return "45-54"
    return "fora-das-faixas"


def gerar(chave=None):
    segredo = chave if chave is not None else os.environ.get("CHAVE_PSEUDONIMO", "")
    if isinstance(segredo, str):
        segredo = segredo.encode("utf-8")
    if not segredo or len(segredo) < 16:
        raise ValueError("defina CHAVE_PSEUDONIMO com pelo menos 16 bytes; não use uma chave real no código")
    if not BRONZE.exists():
        raise FileNotFoundError(f"Bronze não encontrada: {BRONZE}")

    src = sqlite3.connect(f"file:{BRONZE}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    SILVER.parent.mkdir(exist_ok=True)
    dst = sqlite3.connect(SILVER)
    try:
        clientes = src.execute("SELECT id,nascimento,cidade FROM clientes ORDER BY id").fetchall()
        # Missão 4 produz a tabela validada. Se ela ainda não existir, usar pedidos Bronze.
        tem_silver_pedidos = src.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='silver_pedidos'"
        ).fetchone() is not None
        if tem_silver_pedidos:
            pedidos = src.execute(
                "SELECT id,cliente_id,valor_centavos,status,criado_em FROM silver_pedidos ORDER BY id"
            ).fetchall()
        else:
            pedidos = src.execute(
                "SELECT id,cliente_id,valor_centavos,status,criado_em FROM pedidos ORDER BY id"
            ).fetchall()
        navegacao = src.execute(
            "SELECT evento_id,cliente_id,pagina,quando FROM navegacao ORDER BY evento_id"
        ).fetchall()

        dst.execute("PRAGMA foreign_keys = ON")
        dst.executescript("""
        DROP TABLE IF EXISTS clientes;
        DROP TABLE IF EXISTS pedidos;
        DROP TABLE IF EXISTS navegacao;
        DROP TABLE IF EXISTS _metadados;
        CREATE TABLE clientes (
            cliente_ps TEXT PRIMARY KEY, faixa_etaria TEXT, cidade TEXT
        );
        CREATE TABLE pedidos (
            id INTEGER PRIMARY KEY, cliente_ps TEXT, valor_centavos INTEGER NOT NULL,
            status TEXT NOT NULL, criado_em TEXT NOT NULL
        );
        CREATE TABLE navegacao (
            evento_id INTEGER PRIMARY KEY, cliente_ps TEXT, pagina TEXT NOT NULL, quando TEXT NOT NULL
        );
        CREATE TABLE _metadados (
            chave TEXT PRIMARY KEY, valor TEXT NOT NULL
        );
        """)
        with dst:
            dst.execute("DELETE FROM clientes")
            dst.execute("DELETE FROM pedidos")
            dst.execute("DELETE FROM navegacao")
            dst.executemany(
                "INSERT INTO clientes VALUES (?,?,?)",
                [(pseudonimo(segredo, r["id"]), faixa_etaria(r["nascimento"]), r["cidade"]) for r in clientes],
            )
            dst.executemany(
                "INSERT INTO pedidos VALUES (?,?,?,?,?)",
                [(r["id"], pseudonimo(segredo, r["cliente_id"]), r["valor_centavos"], r["status"], r["criado_em"]) for r in pedidos],
            )
            dst.executemany(
                "INSERT INTO navegacao VALUES (?,?,?,?)",
                [(r["evento_id"], pseudonimo(segredo, r["cliente_id"]), r["pagina"], r["quando"]) for r in navegacao],
            )
            dst.execute(
                "INSERT INTO _metadados VALUES ('algoritmo','HMAC-SHA-256') "
                "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor"
            )
            dst.execute(
                "INSERT INTO _metadados VALUES ('fonte_pedidos',?) "
                "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                ("silver_pedidos validada" if tem_silver_pedidos else "pedidos Bronze (missão 4 ainda não executada)",),
            )
        return {"clientes": len(clientes), "pedidos": len(pedidos), "navegacao": len(navegacao), "arquivo": SILVER}
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    r = gerar()
    print(f"Silver reconstruída: clientes={r['clientes']}, pedidos={r['pedidos']}, navegação={r['navegacao']}")
    print(f"arquivo: {r['arquivo'].relative_to(RAIZ)}")
    print("chave não persistida; CPF, nome, e-mail, nascimento exato, observação e IP não são projetados")
