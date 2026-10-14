"""Varre colunas da Bronze em busca de padrões pessoais declarados e texto livre."""
from pathlib import Path
import re, sqlite3

RAIZ = Path(__file__).resolve().parent.parent
BRONZE = RAIZ / "camadas" / "bronze.db"
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TELEFONE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[- .]?\d{4}(?!\d)")
PADROES = (("e-mail", EMAIL), ("CPF", CPF), ("IP", IP), ("telefone", TELEFONE))


def varrer():
    if not BRONZE.exists():
        raise SystemExit("Bronze não encontrada. Rode a carga das Missões 0–2 antes da varredura.")
    con = sqlite3.connect(BRONZE)
    achados=[]
    try:
        tabelas=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for tabela in tabelas:
            colunas=[r[1] for r in con.execute(f'PRAGMA table_info("{tabela}")')]
            for coluna in colunas:
                # A inspeção percorre todas as colunas, não apenas as marcadas como pessoais.
                for rowid, valor in con.execute(f'SELECT rowid, "{coluna}" FROM "{tabela}"'):
                    if not isinstance(valor, str) or not valor:
                        continue
                    for tipo, padrao in PADROES:
                        if padrao.search(valor):
                            achados.append({"tabela":tabela,"coluna":coluna,"linha":rowid,"tipo":tipo,"valor":valor})
                            break
    finally:
        con.close()
    return achados

if __name__ == "__main__":
    achados=varrer()
    print("Varredura da Bronze — padrões pessoais detectados")
    for a in achados:
        # Não imprimir valores completos no relatório: registrar apenas localização e tipo.
        print(f"- {a['tabela']}.{a['coluna']} | linha {a['linha']} | {a['tipo']}")
    print(f"Total de ocorrências/colunas: {len(achados)}")
