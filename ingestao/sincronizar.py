"""Missão 2: aplica o log de mudanças da origem na camada bronze.

Uso:  python ingestao/sincronizar.py

- O único estado do consumidor é o OFFSET: a seq do último evento aplicado, guardado
  na tabela _estado da bronze (offset_mudancas).
- A cada execução aplica só os eventos com seq maior que o offset, em ordem de seq.
- INSERT e UPDATE gravam a linha inteira por mesclagem (upsert); DELETE apaga a linha.
  Os dois são idempotentes: reaplicar um trecho já aplicado não muda o resultado.
- Offset e dados avançam na mesma transação: ou tudo, ou nada.
"""
import json
import sqlite3
from datetime import datetime

import carga

ORIGEM, BRONZE, COLUNAS = carga.ORIGEM, carga.BRONZE, carga.COLUNAS
TABELAS_DO_LOG = ("clientes", "pedidos")  # lista fixa: o nome da tabela vem do log


def _aplicar(bronze, ev, execucao, agora):
    seq, tabela, operacao, chave, dados = ev
    if tabela not in TABELAS_DO_LOG:
        raise ValueError(f"evento {seq}: tabela desconhecida {tabela!r}")
    if operacao == "DELETE":
        bronze.execute(f"DELETE FROM {tabela} WHERE id = ?", (chave,))
        return
    linha = json.loads(dados)
    cols = COLUNAS[tabela]
    todas = cols + ["_carregado_em", "_execucao"]
    atualiza = ", ".join(f"{c} = excluded.{c}" for c in todas if c != "id")
    bronze.execute(
        f"INSERT INTO {tabela} ({', '.join(todas)}) VALUES ({', '.join('?' * len(todas))}) "
        f"ON CONFLICT(id) DO UPDATE SET {atualiza}",
        [linha[c] for c in cols] + [agora, execucao],
    )


def executar(desde=None):
    """Aplica os eventos novos. Com desde=N, reaplica tudo que tem seq > N
    (ensaio de idempotência) sem nunca recuar o offset salvo.

    Devolve {'execucao', 'aplicados', 'offset', 'por_operacao'}.
    """
    BRONZE.parent.mkdir(exist_ok=True)
    origem = sqlite3.connect(f"file:{ORIGEM}?mode=ro", uri=True)
    bronze = sqlite3.connect(BRONZE)
    try:
        if not origem.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'mudancas'"
        ).fetchone():
            raise SystemExit("A captura não está ligada: rode ingestao/captura.py primeiro.")
        bronze.executescript(carga.SCHEMA_BRONZE)
        salvo = int(carga._estado(bronze, "offset_mudancas", 0))
        inicio = salvo if desde is None else desde
        eventos = origem.execute(
            "SELECT seq, tabela, operacao, chave, dados FROM mudancas "
            "WHERE seq > ? ORDER BY seq",
            (inicio,),
        ).fetchall()
        execucao = int(carga._estado(bronze, "execucao", 0)) + 1
        agora = datetime.now().isoformat(timespec="seconds")
        por_operacao = {}
        for ev in eventos:
            _aplicar(bronze, ev, execucao, agora)
            por_operacao[ev[2]] = por_operacao.get(ev[2], 0) + 1
        offset = max([salvo] + [ev[0] for ev in eventos])
        carga._guardar(bronze, "offset_mudancas", offset)
        carga._guardar(bronze, "execucao", execucao)
        bronze.commit()
    except Exception:
        bronze.rollback()
        raise
    finally:
        origem.close()
        bronze.close()
    return {"execucao": execucao, "aplicados": len(eventos), "offset": offset,
            "por_operacao": por_operacao}


if __name__ == "__main__":
    r = executar()
    print(f"execução {r['execucao']}: {r['aplicados']} eventos aplicados {r['por_operacao']}, "
          f"offset agora em {r['offset']}")
