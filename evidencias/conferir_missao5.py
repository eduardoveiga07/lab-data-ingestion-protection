"""Verificador reproduzível da Missão 5: governança, catálogo e varredura."""
import contextlib, io, sqlite3, sys, tempfile
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "ingestao"), str(RAIZ / "governanca")]
import aplicar_dia2, captura, carga, criar_origem, sincronizar
import gerar_catalogo, validar_acordo, varrer_dados_pessoais

saida, ok = [], True
def checar(nome, obtido, esperado):
    global ok
    passou = obtido == esperado
    ok = ok and passou
    saida.append(f"[{'OK' if passou else 'ERRO'}] {nome}: obtido {obtido!r}; esperado {esperado!r}")

with contextlib.redirect_stdout(io.StringIO()):
    criar_origem.main()
if carga.BRONZE.exists(): carga.BRONZE.unlink()
carga.executar()
captura.ligar(); aplicar_dia2.aplicar(); sincronizar.executar()

saida.append("1) Acordo de governança e regra como código")
checar("conjuntos no acordo", validar_acordo.validar(), 3)
acordo = RAIZ / "governanca" / "acordo.yaml"
original = acordo.read_text(encoding="utf-8")
try:
    alterado = original.replace("retencao: 30 dias para análise operacional; depois agregar ou eliminar eventos identificáveis.", "retencao:")
    acordo.write_text(alterado, encoding="utf-8")
    try:
        validar_acordo.validar()
        falhou = False
    except ValueError as e:
        falhou = "navegacao" in str(e) and "retenção" in str(e)
    checar("pipeline barra conjunto pessoal sem retenção", falhou, True)
finally:
    acordo.write_text(original, encoding="utf-8")

saida.append("2) Catálogo gerado dos contratos e acordo")
catalogo = gerar_catalogo.gerar().read_text(encoding="utf-8")
checar("catálogo inclui os três conjuntos", all(f"## {n}" in catalogo for n in ("clientes", "pedidos", "navegacao")), True)
checar("catálogo inclui dono e frescor", "Time de Cadastro e Identidade" in catalogo and "até 24 horas" in catalogo, True)
contrato_clientes = RAIZ / "contratos" / "clientes.yaml"
texto_original = contrato_clientes.read_text(encoding="utf-8")
try:
    contrato_clientes.write_text(texto_original.replace("Cadastro e atributos dos clientes da loja online.", "Cadastro e atributos atualizados dos clientes da loja online."), encoding="utf-8")
    catalogo_mudado = gerar_catalogo.gerar().read_text(encoding="utf-8")
    checar("alteração no contrato aparece ao regenerar catálogo", "Cadastro e atributos atualizados dos clientes" in catalogo_mudado, True)
finally:
    contrato_clientes.write_text(texto_original, encoding="utf-8")
    gerar_catalogo.gerar()

saida.append("3) Varredura de padrões pessoais na Bronze")
achados = varrer_dados_pessoais.varrer()
obs = [a for a in achados if a["tabela"] == "pedidos" and a["coluna"] == "observacao" and a["tipo"] in ("e-mail", "telefone")]
ip = [a for a in achados if a["tabela"] == "navegacao" and a["coluna"] == "ip" and a["tipo"] == "IP"]
checar("observações com dado pessoal não estruturado", sorted(a["linha"] for a in obs), [104, 106])
checar("eventos de navegação com IP", len(ip), 8)
checar("varredura cobre e-mail, telefone, CPF e IP", {a["tipo"] for a in achados} >= {"e-mail", "telefone", "CPF", "IP"}, True)
saida.append("Localizações inesperadas identificadas: pedidos.observacao (pedidos 104 e 106) e navegacao.ip (8 eventos).")
saida.append("O varredor registra tabela, coluna, linha e tipo, sem despejar valores pessoais no relatório.")
texto = "\n".join(saida + ["RESULTADO: " + ("tudo certo" if ok else "há divergências")])
print(texto)
(RAIZ / "evidencias" / "missao5.txt").write_text(texto + "\n", encoding="utf-8")
sys.exit(0 if ok else 1)
