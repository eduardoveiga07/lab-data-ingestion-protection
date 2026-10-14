"""Regra como código: impede que conjunto pessoal não tenha retenção definida."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ACORDO = RAIZ / "governanca" / "acordo.yaml"


def ler_acordo(caminho=ACORDO):
    conjuntos, atual = [], None
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- nome:"):
            atual = {"nome": s.split(":", 1)[1].strip()}
            conjuntos.append(atual)
        elif atual is not None and ":" in s:
            k, v = s.split(":", 1)
            atual[k.strip()] = v.strip()
    if not conjuntos:
        raise ValueError("acordo sem conjuntos")
    return conjuntos


def validar(caminho=ACORDO):
    erros = []
    for c in ler_acordo(caminho):
        if c.get("classe", "").lower() in ("pessoal", "pessoal sensível") and not c.get("retencao", "").strip():
            erros.append(f"conjunto pessoal '{c.get('nome', '?')}' sem retenção definida")
        for campo in ("dono", "classe", "acesso"):
            if not c.get(campo, "").strip():
                erros.append(f"conjunto '{c.get('nome', '?')}' sem '{campo}' definido")
    if erros:
        raise ValueError("Acordo de governança inválido:\n- " + "\n- ".join(erros))
    return len(ler_acordo(caminho))

if __name__ == "__main__":
    n = validar()
    print(f"Acordo válido: {n} conjuntos; retenção definida para todos os conjuntos pessoais.")
