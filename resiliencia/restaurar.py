"""Missão 9: valida integridade, restaura bancos e reaplica eliminações pendentes.

Uso: python resiliencia/restaurar.py resiliencia/backups/snapshot_... 
A lista privacidade/lista_eliminacao.jsonl é deliberadamente mantida fora do snapshot:
é o registro de supressão que precisa sobreviver à restauração.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINOS = {
    "loja.db": RAIZ / "origem" / "loja.db",
    "bronze.db": RAIZ / "camadas" / "bronze.db",
    "silver.db": RAIZ / "camadas" / "silver.db",
    "gold.db": RAIZ / "camadas" / "gold.db",
}
LISTA = RAIZ / "privacidade" / "lista_eliminacao.jsonl"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def validar(snapshot):
    manifesto_path = snapshot / "manifesto.json"
    if not manifesto_path.exists():
        raise FileNotFoundError("manifesto.json não encontrado no snapshot")
    manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    for nome in DESTINOS:
        item = manifesto.get("bancos", {}).get(nome)
        arquivo = snapshot / nome
        if not item or not arquivo.is_file():
            raise ValueError(f"snapshot incompleto: {nome}")
        atual = sha256(arquivo)
        if atual != item["sha256"]:
            raise ValueError(f"falha de integridade SHA-256: {nome}")
    return manifesto


def ids_candidatos():
    """Coleta IDs em memória para comparar hashes; nunca os grava no relatório."""
    ids = set()
    for path in DESTINOS.values():
        if not path.exists():
            continue
        con = sqlite3.connect(path)
        try:
            tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for tab in tabelas:
                cols = {r[1] for r in con.execute(f'PRAGMA table_info("{tab}")')}
                for col in ("id", "cliente_id", "cliente", "chave"):
                    if col not in cols:
                        continue
                    # IDs apenas numéricos são candidatos; texto livre nunca é registrado.
                    for (v,) in con.execute(f'SELECT "{col}" FROM "{tab}" WHERE "{col}" IS NOT NULL'):
                        try:
                            n = int(v)
                            if n > 0 and str(n) == str(v).strip():
                                ids.add(n)
                        except (ValueError, TypeError):
                            continue
        finally:
            con.close()
    return ids


def reaplicar_lista():
    if not LISTA.exists():
        return {"pedidos_reaplicados": 0}
    registros = [json.loads(l) for l in LISTA.read_text(encoding="utf-8").splitlines() if l.strip()]
    hashes = {r.get("chave_pedido") for r in registros if r.get("chave_pedido")}
    encontrados = []
    for cliente_id in sorted(ids_candidatos()):
        chave = hashlib.sha256(f"pedido-de-eliminacao:cliente:{cliente_id}".encode()).hexdigest()[:24]
        if chave in hashes:
            encontrados.append(cliente_id)
    if encontrados:
        sys.path.insert(0, str(RAIZ / "privacidade"))
        import esquecer
        for cliente_id in encontrados:
            esquecer.esquecer(cliente_id)
    return {"pedidos_reaplicados": len(encontrados)}


def restaurar(snapshot, reconstruir=True):
    snapshot = Path(snapshot)
    if not snapshot.is_absolute():
        snapshot = RAIZ / snapshot
    snapshot = snapshot.resolve()
    validar(snapshot)  # validar todos os arquivos antes de substituir qualquer banco ativo
    for nome, destino in DESTINOS.items():
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".restore.tmp")
        shutil.copy2(snapshot / nome, temporario)
        temporario.replace(destino)
    eliminacoes = reaplicar_lista()
    if reconstruir:
        # Chave vem do ambiente. A restauração falha de forma explícita se ela não estiver disponível.
        sys.path.insert(0, str(RAIZ / "seguranca"))
        sys.path.insert(0, str(RAIZ / "privacidade"))
        import gerar_silver, gerar_consumo
        gerar_silver.gerar()
        gerar_consumo.gerar()
    return {"snapshot": snapshot, **eliminacoes, "silver_gold_reconstruidas": bool(reconstruir)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Restaura snapshot íntegro e reaplica a lista de eliminação.")
    p.add_argument("snapshot", help="diretório contendo manifesto.json e os quatro bancos")
    p.add_argument("--sem-reconstruir", action="store_true", help="não reconstruir Silver/Gold")
    a = p.parse_args()
    r = restaurar(a.snapshot, reconstruir=not a.sem_reconstruir)
    print(f"Restauração concluída: bancos validados; eliminações reaplicadas={r['pedidos_reaplicados']}; Silver/Gold reconstruídas={r['silver_gold_reconstruidas']}")
