"""Missão 9: cria snapshot consistente dos bancos SQLite e manifesto SHA-256.

Uso: python resiliencia/backup.py [--destino resiliencia/backups/manual]
O diretório de destino deve ser novo ou vazio. Esta cópia local não é, por si só,
uma cópia off-site ou imutável real.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = {
    "loja.db": RAIZ / "origem" / "loja.db",
    "bronze.db": RAIZ / "camadas" / "bronze.db",
    "silver.db": RAIZ / "camadas" / "silver.db",
    "gold.db": RAIZ / "camadas" / "gold.db",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def criar(destino=None):
    instante = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = Path(destino) if destino else RAIZ / "resiliencia" / "backups" / f"snapshot_{instante}"
    if not destino.is_absolute():
        destino = RAIZ / destino
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError(f"destino deve ser novo ou vazio: {destino}")
    destino.mkdir(parents=True, exist_ok=True)
    bancos = {}
    for nome, origem in FONTES.items():
        if not origem.exists():
            raise FileNotFoundError(f"banco necessário não encontrado: {origem.relative_to(RAIZ)}")
        alvo = destino / nome
        # API backup do SQLite gera snapshot consistente mesmo com WAL habilitado.
        with sqlite3.connect(origem) as src, sqlite3.connect(alvo) as dst:
            src.backup(dst)
        bancos[nome] = {"sha256": sha256(alvo), "bytes": alvo.stat().st_size}
    manifesto = {
        "formato": 1,
        "criado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bancos": bancos,
        "observacao": "snapshot local de laboratório; off-site/imutabilidade física exigem destino externo independente",
    }
    (destino / "manifesto.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"destino": destino, "bancos": len(bancos), "manifesto": destino / "manifesto.json"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cria snapshot consistente e manifesto de integridade.")
    p.add_argument("--destino", help="diretório de destino; relativo à raiz do projeto ou absoluto")
    a = p.parse_args()
    r = criar(a.destino)
    print(f"Backup criado: {r['destino']}; bancos={r['bancos']}; manifesto=manifesto.json")
