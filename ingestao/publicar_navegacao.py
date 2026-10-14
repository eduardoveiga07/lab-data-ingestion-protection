"""Missão 3, Trilha A: publica navegação num log append-only local.

Uso: python ingestao/publicar_navegacao.py [--intervalo 1]
O produtor conhece apenas o arquivo de entrada e o log; não conhece os leitores.
"""
import argparse
import csv
import sqlite3
import time
from pathlib import Path

import carga

LOG = carga.ORIGEM
CSV_NAVEGACAO = carga.RAIZ / "dados" / "navegacao.csv"
DDL = """
CREATE TABLE IF NOT EXISTS log_navegacao (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id INTEGER NOT NULL UNIQUE,
    cliente_id INTEGER,
    ip TEXT NOT NULL,
    pagina TEXT NOT NULL,
    quando TEXT NOT NULL,
    publicado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def preparar(caminho=LOG):
    con = sqlite3.connect(caminho)
    con.executescript(DDL)
    con.commit()
    con.close()


def publicar_todos(intervalo=1.0, caminho=LOG, arquivo=CSV_NAVEGACAO):
    preparar(caminho)
    publicados = 0
    with open(arquivo, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            con = sqlite3.connect(caminho)
            evento_id = int(row["evento_id"])
            existe = con.execute("SELECT 1 FROM log_navegacao WHERE evento_id = ?", (evento_id,)).fetchone()
            if not existe:
                con.execute(
                    "INSERT INTO log_navegacao "
                    "(evento_id, cliente_id, ip, pagina, quando) VALUES (?, ?, ?, ?, ?)",
                    (evento_id, int(row["cliente_id"]) if row["cliente_id"] else None,
                     row["ip"], row["pagina"], row["quando"]),
                )
                publicados += 1
            con.commit()
            con.close()
            if intervalo and intervalo > 0:
                time.sleep(intervalo)
    return publicados


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--intervalo", type=float, default=1.0, help="segundos entre eventos (0 acelera o teste)")
    args = p.parse_args()
    n = publicar_todos(args.intervalo)
    print(f"produtor concluído: {n} novos eventos; log persistente em {LOG}")
