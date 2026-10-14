"""Gera o catálogo a partir dos contratos e do acordo, sem duplicar metadados."""
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "qualidade"))
from validar_pedidos import ler_contrato
from validar_acordo import ler_acordo, validar

CONTRATOS = RAIZ / "contratos"
SAIDA = RAIZ / "governanca" / "catalogo.md"


def ler_metadados(caminho):
    dados = {"campos": []}
    campo = None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        if not linha.startswith(" ") and ":" in s:
            k, v = s.split(":", 1)
            dados[k.strip()] = ([] if k.strip() == "campos" else v.strip())
        elif s.startswith("- nome:"):
            campo = {"nome": s.split(":",1)[1].strip()}
            dados["campos"].append(campo)
        elif campo is not None and ":" in s:
            k,v=s.split(":",1); campo[k.strip()] = v.strip()
    return dados


def gerar():
    validar()
    acordo = {x["nome"]: x for x in ler_acordo()}
    linhas = ["# Catálogo de dados", "", "Gerado automaticamente por `python governanca/gerar_catalogo.py`. Não editar manualmente.", ""]
    for nome in ("clientes", "pedidos", "navegacao"):
        contrato = ler_metadados(CONTRATOS / f"{nome}.yaml")
        a = acordo.get(nome)
        if not a:
            raise ValueError(f"conjunto '{nome}' ausente do acordo de governança")
        linhas += [f"## {nome}", "", contrato.get("descricao", "Sem descrição no contrato."), "",
                   f"- **Versão do contrato:** {contrato.get('versao', 'não informada')}",
                   f"- **Dono:** {a.get('dono', 'não informado')}",
                   f"- **Classe do conjunto:** {a.get('classe', 'não informada')}",
                   f"- **Retenção:** {a.get('retencao', 'não informada')}",
                   f"- **Acesso:** {a.get('acesso', 'não informado')}",
                   f"- **Frescor:** {contrato.get('frescor', 'não informado')}", "",
                   "| Campo | Tipo | Classe | Obrigatório | Finalidade | Descrição |", "|---|---|---|---|---|---|"]
        for f in contrato["campos"]:
            obrig = f.get("obrigatorio", "false")
            if isinstance(obrig, bool): obrig = str(obrig).lower()
            linhas.append(f"| `{f['nome']}` | {f.get('tipo','texto')} | {f.get('classe','não classificado')} | {obrig} | {f.get('finalidade','—')} | {f.get('descricao','Sem descrição')} |")
        linhas.append("")
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    return SAIDA

if __name__ == "__main__":
    print(f"Catálogo gerado: {gerar().relative_to(RAIZ)}")
