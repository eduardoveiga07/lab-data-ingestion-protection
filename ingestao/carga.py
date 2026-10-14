"""Missão 1: carga incremental da origem para a camada bronze.

Uso:  python ingestao/carga.py [tabela ...]

- clientes e pedidos: lê só o que tem atualizado_em MAIOR que a marca-d'água
  e grava por mesclagem pela chave id (linha nova entra, existente é substituída).
- navegacao: dado de atividade, só acrescenta. Lê só os eventos com evento_id
  maior que o último carregado e ainda usa a chave evento_id como trava contra
  duplicata (INSERT OR IGNORE). Não dá para usar o horário como marca: o evento 8
  aconteceu antes do evento 7.
- A bronze guarda o dado como chegou, mais duas colunas de controle:
  _carregado_em (quando chegou) e _execucao (em qual execução).
- A marca-d'água fica na tabela _estado da própria bronze, fora do código, e só
  avança junto com a gravação (tudo na mesma transação).
"""
import sqlite3
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "origem" / "loja.db"
BRONZE = RAIZ / "camadas" / "bronze.db"

COLUNAS = {
    "clientes": ["id", "nome", "email", "cpf", "nascimento", "cidade", "atualizado_em"],
    "pedidos": ["id", "cliente_id", "valor_centavos", "status", "criado_em",
                "atualizado_em", "observacao"],
    "navegacao": ["evento_id", "cliente_id", "ip", "pagina", "quando"],
}
CHAVE = {"clientes": "id", "pedidos": "id", "navegacao": "evento_id"}

SCHEMA_BRONZE = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY, nome TEXT, email TEXT, cpf TEXT, nascimento TEXT,
    cidade TEXT, atualizado_em TEXT,
    _carregado_em TEXT, _execucao INTEGER
);
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY, cliente_id INTEGER, valor_centavos INTEGER, status TEXT,
    criado_em TEXT, atualizado_em TEXT, observacao TEXT,
    _carregado_em TEXT, _execucao INTEGER
);
CREATE TABLE IF NOT EXISTS navegacao (
    evento_id INTEGER PRIMARY KEY, cliente_id INTEGER, ip TEXT, pagina TEXT, quando TEXT,
    _carregado_em TEXT, _execucao INTEGER
);
CREATE TABLE IF NOT EXISTS _estado (chave TEXT PRIMARY KEY, valor TEXT);
"""


def _estado(bronze, chave, padrao):
    linha = bronze.execute("SELECT valor FROM _estado WHERE chave = ?", (chave,)).fetchone()
    return linha[0] if linha else padrao


def _guardar(bronze, chave, valor):
    bronze.execute(
        "INSERT INTO _estado (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, str(valor)),
    )


def _mesclar(origem, bronze, tabela, execucao, agora):
    """Carga incremental com mesclagem pela chave."""
    cols = COLUNAS[tabela]
    marca = _estado(bronze, f"marca_{tabela}", "")
    linhas = origem.execute(
        f"SELECT {', '.join(cols)} FROM {tabela} "
        f"WHERE atualizado_em > ? ORDER BY atualizado_em, id",
        (marca,),
    ).fetchall()
    if not linhas:
        return 0
    todas = cols + ["_carregado_em", "_execucao"]
    atualiza = ", ".join(f"{c} = excluded.{c}" for c in todas if c != "id")
    bronze.executemany(
        f"INSERT INTO {tabela} ({', '.join(todas)}) VALUES ({', '.join('?' * len(todas))}) "
        f"ON CONFLICT(id) DO UPDATE SET {atualiza}",
        [tuple(l) + (agora, execucao) for l in linhas],
    )
    _guardar(bronze, f"marca_{tabela}", max(l[cols.index("atualizado_em")] for l in linhas))
    return len(linhas)


def _anexar(origem, bronze, tabela, execucao, agora):
    """Carga por anexação: só eventos novos, com a chave como trava de duplicata."""
    cols = COLUNAS[tabela]
    marca = int(_estado(bronze, f"marca_{tabela}", 0))
    linhas = origem.execute(
        f"SELECT {', '.join(cols)} FROM {tabela} WHERE evento_id > ? ORDER BY evento_id",
        (marca,),
    ).fetchall()
    if not linhas:
        return 0
    todas = cols + ["_carregado_em", "_execucao"]
    bronze.executemany(
        f"INSERT OR IGNORE INTO {tabela} ({', '.join(todas)}) "
        f"VALUES ({', '.join('?' * len(todas))})",
        [tuple(l) + (agora, execucao) for l in linhas],
    )
    _guardar(bronze, f"marca_{tabela}", max(l[0] for l in linhas))
    return len(linhas)


def executar(tabelas=None):
    """Roda uma execução da carga. Devolve {'execucao': n, 'lidas': {...}, 'total_lidas': n}.

    tabelas: quais tabelas carregar (padrão: as três). A partir da Missão 2,
    clientes e pedidos passam a vir do log (sincronizar.py).
    """
    BRONZE.parent.mkdir(exist_ok=True)
    origem = sqlite3.connect(f"file:{ORIGEM}?mode=ro", uri=True)  # a carga só lê a origem
    bronze = sqlite3.connect(BRONZE)
    try:
        bronze.executescript(SCHEMA_BRONZE)
        execucao = int(_estado(bronze, "execucao", 0)) + 1
        agora = datetime.now().isoformat(timespec="seconds")
        lidas = {}
        for t in tabelas or ("clientes", "pedidos", "navegacao"):
            carregar = _anexar if t == "navegacao" else _mesclar
            lidas[t] = carregar(origem, bronze, t, execucao, agora)
        _guardar(bronze, "execucao", execucao)
        bronze.commit()  # marca-d'água e dados avançam juntos, ou nada avança
    except Exception:
        bronze.rollback()
        raise
    finally:
        origem.close()
        bronze.close()
    return {"execucao": execucao, "lidas": lidas, "total_lidas": sum(lidas.values())}


if __name__ == "__main__":
    import sys
    r = executar(sys.argv[1:] or None)
    print(f"execução {r['execucao']}: linhas lidas = {r['lidas']} (total {r['total_lidas']})")
