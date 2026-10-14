"""Verificador da Missão 10: completude do README, diagrama e evidências."""
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent.parent
saida = []
ok = True

def checar(nome, condicao, detalhe=""):
    global ok
    ok = ok and bool(condicao)
    saida.append(f"[{'OK' if condicao else 'ERRO'}] {nome}" + (f": {detalhe}" if detalhe else ""))

readme = (RAIZ / "README.md").read_text(encoding="utf-8")
for rel in (
    "arquitetura/pipeline.dot", "arquitetura/pipeline.svg", "arquitetura/pipeline.png",
    "arquitetura/vida-do-dado.dot", "arquitetura/vida-do-dado.svg", "arquitetura/vida-do-dado.png",
):
    p = RAIZ / rel
    checar(f"artefato de arquitetura presente: {rel}", p.is_file() and p.stat().st_size > 100)
checar("README aponta para as duas visões", all(x in readme for x in (
    "arquitetura/pipeline.png", "arquitetura/pipeline.svg", "arquitetura/vida-do-dado.png", "arquitetura/vida-do-dado.svg"
)))
estrutura = (RAIZ / "arquitetura/pipeline.dot").read_text(encoding="utf-8")
checar("diagrama estrutural registra chave, acesso, classe e cópias", all(x in estrutura for x in (
    "CHAVE_PSEUDONIMO", "Acesso por função", "Classificação das camadas", "Cópias e retenção"
)))
fluxo = (RAIZ / "arquitetura/vida-do-dado.dot").read_text(encoding="utf-8")
checar("diagrama de vida cobre cadastro, eliminação e restauração", all(x in fluxo for x in (
    "cadastro", "Solicitação de eliminação", "Lista de eliminação", "Restauração", "não ressuscitar dados"
)))
checar("README registra todas as missões como concluídas", all(f"| {n} |" in readme and "feita" in readme[readme.find(f"| {n} |"):readme.find(f"| {n} |") + 220] for n in range(1, 11)))
checar("README documenta execução, números finais e RTO", all(t in readme for t in ("Como validar a entrega", "Números finais", "RTO observado no ensaio")))
for n in range(10):
    evid = RAIZ / "evidencias" / f"missao{n}.txt"
    checar(f"evidência da Missão {n}", evid.is_file() and "RESULTADO: tudo certo" in evid.read_text(encoding="utf-8"))
missao9 = (RAIZ / "evidencias" / "missao9.txt").read_text(encoding="utf-8")
checar("evidência de resiliência registra RTO observado", "RTO observado no ensaio" in missao9)
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
(RAIZ / "evidencias" / "missao10.txt").write_text(texto + "\n", encoding="utf-8")
print(texto)
sys.exit(0 if ok else 1)
