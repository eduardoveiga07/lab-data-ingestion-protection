"""Missão 7: generalização, medição de K-anonimato e visão Gold de consumo.

Uso: python privacidade/gerar_consumo.py
Pré-requisito: gerar a Silver com CHAVE_PSEUDONIMO definida no ambiente.
"""
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SILVER = RAIZ / "camadas" / "silver.db"
GOLD = RAIZ / "camadas" / "gold.db"
LIMIAR_K = 2


def gerar():
    if not SILVER.exists():
        raise FileNotFoundError("Silver não encontrada; rode seguranca/gerar_silver.py primeiro")
    src = sqlite3.connect(f"file:{SILVER}?mode=ro", uri=True)
    dst = sqlite3.connect(GOLD)
    try:
        clientes = src.execute(
            "SELECT cliente_ps, faixa_etaria, cidade FROM clientes ORDER BY cidade, faixa_etaria"
        ).fetchall()
        pedidos = src.execute(
            "SELECT cliente_ps, valor_centavos, status FROM pedidos"
        ).fetchall()
        dst.executescript("""
        DROP TABLE IF EXISTS receita_por_cidade;
        DROP TABLE IF EXISTS k_anonimato;
        DROP TABLE IF EXISTS resumo_consumo;
        CREATE TABLE k_anonimato (
            cidade TEXT NOT NULL, faixa_etaria TEXT NOT NULL,
            quantidade_pessoas INTEGER NOT NULL, abaixo_do_k INTEGER NOT NULL,
            PRIMARY KEY (cidade, faixa_etaria)
        );
        CREATE TABLE receita_por_cidade (
            cidade TEXT PRIMARY KEY, numero_clientes INTEGER,
            receita_paga_centavos INTEGER, suprimida INTEGER NOT NULL
        );
        CREATE TABLE resumo_consumo (
            indicador TEXT PRIMARY KEY, valor_centavos INTEGER NOT NULL
        );
        """)
        # Conta perfis distintos por combinação cidade + faixa etária.
        perfis = {}
        cidade_clientes = {}
        for cliente_ps, faixa, cidade in clientes:
            perfis[(cidade or "desconhecida", faixa or "não informada")] = perfis.get((cidade or "desconhecida", faixa or "não informada"), 0) + 1
            cidade_clientes.setdefault(cidade or "desconhecida", set()).add(cliente_ps)
        with dst:
            dst.executemany(
                "INSERT INTO k_anonimato VALUES (?,?,?,?)",
                [(cidade, faixa, n, int(n < LIMIAR_K)) for (cidade, faixa), n in sorted(perfis.items())]
            )
            # Receita por cliente pseudonimizado. Pedido 106 sobreviveu à exclusão
            # do cadastro 5: sua receita entra no total, mas não pode ser atribuída à cidade.
            receita_cliente = {}
            total_pago = 0
            for cliente_ps, valor, status in pedidos:
                if status == "pago":
                    total_pago += int(valor)
                    if cliente_ps is not None:
                        receita_cliente[cliente_ps] = receita_cliente.get(cliente_ps, 0) + int(valor)
            cidade_receita = {}
            for cliente_ps, faixa, cidade in clientes:
                cidade = cidade or "desconhecida"
                cidade_receita[cidade] = cidade_receita.get(cidade, 0) + receita_cliente.get(cliente_ps, 0)
            for cidade, ps_set in sorted(cidade_clientes.items()):
                n = len(ps_set)
                if n < LIMIAR_K:
                    # Suprime contagem e receita por cidade; não remove o valor do total geral.
                    dst.execute("INSERT INTO receita_por_cidade VALUES (?,?,?,1)", (cidade, None, None))
                else:
                    dst.execute("INSERT INTO receita_por_cidade VALUES (?,?,?,0)", (cidade, n, cidade_receita.get(cidade, 0)))
            dst.execute("INSERT INTO resumo_consumo VALUES ('receita_paga_total_centavos',?)", (total_pago,))
        return {"clientes": len(clientes), "combinacoes_unicas": sum(1 for n in perfis.values() if n == 1),
                "receita_total_centavos": total_pago, "arquivo": GOLD}
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    r = gerar()
    print(f"Gold reconstruída: clientes={r['clientes']}; combinações cidade+faixa com uma pessoa={r['combinacoes_unicas']}")
    print(f"receita paga total (inclui grupos suprimidos e pedidos sem cadastro): R$ {r['receita_total_centavos']/100:.2f}")
    print(f"arquivo: {r['arquivo'].relative_to(RAIZ)}")
