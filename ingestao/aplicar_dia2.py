"""Aplica na origem as mudanças do dia 2, na ordem (ver dados/mudancas_dia2.txt).

Uso:  python ingestao/aplicar_dia2.py
Para voltar ao dia 1:  python ingestao/criar_origem.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "origem" / "loja.db"


def aplicar():
    con = sqlite3.connect(DB)
    if con.execute("SELECT 1 FROM clientes WHERE id = 7").fetchone():
        con.close()
        raise SystemExit("O dia 2 já foi aplicado. Rode criar_origem.py para voltar ao dia 1.")
    # 1 ALTERAÇÃO pedidos 105: pendente -> pago
    con.execute("UPDATE pedidos SET status = 'pago', atualizado_em = '2026-10-02T08:10:00' WHERE id = 105")
    # 2 ALTERAÇÃO clientes 3: e-mail novo
    con.execute("UPDATE clientes SET email = 'carla.n@example.com', atualizado_em = '2026-10-02T08:20:00' WHERE id = 3")
    # 3 INSERÇÃO clientes 7
    con.execute(
        "INSERT INTO clientes (id, nome, email, cpf, nascimento, cidade, atualizado_em) "
        "VALUES (7, 'Gabi Rocha', 'gabi.rocha@example.com', '777.777.777-77', '1996-02-25', "
        "'Sorocaba', '2026-10-02T08:30:00')"
    )
    # 4 INSERÇÃO pedidos 109 (sem observação)
    con.execute(
        "INSERT INTO pedidos (id, cliente_id, valor_centavos, status, criado_em, atualizado_em, observacao) "
        "VALUES (109, 7, 5600, 'pago', '2026-10-02T08:40:00', '2026-10-02T08:40:00', NULL)"
    )
    # 5 EXCLUSÃO clientes 5 (o pedido 106 permanece)
    con.execute("DELETE FROM clientes WHERE id = 5")
    con.commit()
    con.close()
    print("dia 2 aplicado: 2 alterações, 2 inserções, 1 exclusão")


if __name__ == "__main__":
    aplicar()
