"""Missão 4: aplica o contrato de pedidos, promove válidos para silver e isola inválidos.

Uso: python qualidade/validar_pedidos.py
Só usa a biblioteca padrão: lê o subconjunto YAML usado nos contratos do laboratório.
"""
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BRONZE = RAIZ / "camadas" / "bronze.db"
CONTRATO = RAIZ / "contratos" / "pedidos.yaml"
LOTE = RAIZ / "dados" / "pedidos_dia3.csv"


def ler_contrato(caminho=CONTRATO):
    """Leitor pequeno para a estrutura simples de campos usada nos YAMLs do projeto."""
    contrato = {"conjunto": None, "versao": None, "campos": []}
    campo = None
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        if not linha.startswith(" ") and ":" in s:
            chave, valor = s.split(":", 1)
            if chave in ("conjunto", "versao"):
                contrato[chave] = int(valor.strip()) if chave == "versao" else valor.strip()
        elif s.startswith("- nome:"):
            campo = {"nome": s.split(":", 1)[1].strip()}
            contrato["campos"].append(campo)
        elif campo is not None and ":" in s:
            chave, valor = s.split(":", 1)
            valor = valor.strip()
            if valor in ("true", "false"):
                valor = valor == "true"
            elif valor.startswith("[") and valor.endswith("]"):
                valor = [x.strip() for x in valor[1:-1].split(",") if x.strip()]
            elif valor.lstrip("-").isdigit():
                valor = int(valor)
            campo[chave] = valor
    if not contrato["campos"]:
        raise ValueError(f"contrato sem campos: {caminho}")
    return contrato


def converter(valor, tipo):
    if valor is None or valor == "":
        return None
    if tipo == "inteiro":
        if isinstance(valor, bool) or str(valor).strip() == "":
            raise ValueError("não é inteiro")
        convertido = int(valor)
        if str(convertido) != str(valor).strip() and not isinstance(valor, int):
            raise ValueError("não é inteiro")
        return convertido
    if tipo == "texto":
        if not isinstance(valor, str):
            raise ValueError("não é texto")
        return valor
    if tipo == "data_hora":
        return datetime.fromisoformat(str(valor))
    if tipo == "data":
        return datetime.strptime(str(valor), "%Y-%m-%d").date()
    raise ValueError(f"tipo não suportado no contrato: {tipo}")


def validar_linha(linha, contrato, vistos, momento_carga):
    """Retorna (motivo, linha_convertida); regras lidas do contrato, sem regras de campo fixas."""
    normalizada = dict(linha)
    for campo in contrato["campos"]:
        nome = campo["nome"]
        valor = normalizada.get(nome)
        if campo.get("obrigatorio") and (valor is None or valor == ""):
            return f"campo obrigatório ausente: {nome}", None
        if valor is None or valor == "":
            normalizada[nome] = None
            continue
        try:
            normalizada[nome] = converter(valor, campo.get("tipo", "texto"))
        except (ValueError, TypeError, OverflowError):
            return f"tipo inválido: {nome} (esperado {campo.get('tipo')})", None
        convertido = normalizada[nome]
        if "minimo" in campo and convertido < campo["minimo"]:
            return f"valor abaixo do mínimo: {nome} < {campo['minimo']}", None
        if "dominio" in campo and str(valor) not in campo["dominio"]:
            return f"valor fora do domínio: {nome}={valor}", None
        if campo.get("maximo") == "momento da carga" and convertido > momento_carga:
            return f"data no futuro: {nome} > momento da carga", None
        if campo.get("unico"):
            if convertido in vistos.setdefault(nome, set()):
                return f"chave repetida: {nome}={convertido}", None
    for campo in contrato["campos"]:
        if campo.get("unico"):
            vistos.setdefault(campo["nome"], set()).add(normalizada.get(campo["nome"]))
    return None, normalizada


def executar():
    if not BRONZE.exists():
        raise SystemExit("Bronze não encontrada. Rode as Missões 0–2 antes desta missão.")
    contrato = ler_contrato()
    campos = [c["nome"] for c in contrato["campos"]]
    agora = datetime.now().replace(microsecond=0)
    execucao = agora.isoformat()
    with open(LOTE, newline="", encoding="utf-8") as f:
        lote = list(csv.DictReader(f))
    bronze = sqlite3.connect(BRONZE)
    bronze.row_factory = sqlite3.Row
    try:
        bronze.execute("""CREATE TABLE IF NOT EXISTS pedidos_lote (
            linha_lote INTEGER PRIMARY KEY AUTOINCREMENT, id INTEGER, cliente_id INTEGER,
            valor_centavos INTEGER, status TEXT, criado_em TEXT, observacao TEXT,
            _carregado_em TEXT NOT NULL, _execucao TEXT NOT NULL)""")
        bronze.execute("""CREATE TABLE IF NOT EXISTS quarentena_pedidos (
            quarentena_id INTEGER PRIMARY KEY AUTOINCREMENT, execucao TEXT NOT NULL,
            lote TEXT NOT NULL, linha_lote INTEGER NOT NULL, id INTEGER,
            cliente_id INTEGER, valor_centavos INTEGER, status TEXT, criado_em TEXT,
            observacao TEXT, motivo TEXT NOT NULL)""")
        bronze.execute("""CREATE TABLE IF NOT EXISTS silver_pedidos (
            id INTEGER PRIMARY KEY, cliente_id INTEGER, valor_centavos INTEGER,
            status TEXT, criado_em TEXT, atualizado_em TEXT, observacao TEXT,
            _validado_em TEXT NOT NULL, _contrato TEXT NOT NULL)""")
        # Cada execução carrega uma nova cópia do lote, preservando inclusive linhas duplicadas.
        ids_lote = []
        for linha in lote:
            cur = bronze.execute(
                "INSERT INTO pedidos_lote (id,cliente_id,valor_centavos,status,criado_em,observacao,_carregado_em,_execucao) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (int(linha["id"]), int(linha["cliente_id"]) if linha["cliente_id"] else None,
                 int(linha["valor_centavos"]) if linha["valor_centavos"] else 0,
                 linha["status"], linha["criado_em"], linha["observacao"] or None, execucao, execucao),
            )
            ids_lote.append(cur.lastrowid)
        # Silver é reconstruída a partir dos pedidos atuais da bronze mais as linhas aprovadas.
        bronze.execute("DELETE FROM silver_pedidos")
        bronze.execute("DELETE FROM quarentena_pedidos WHERE execucao = ?", (execucao,))
        vistos = {c["nome"]: set() for c in contrato["campos"] if c.get("unico")}
        base = bronze.execute("SELECT id,cliente_id,valor_centavos,status,criado_em,atualizado_em,observacao FROM pedidos ORDER BY id").fetchall()
        validos_base = 0
        for row in base:
            linha = dict(row)
            motivo, norm = validar_linha(linha, contrato, vistos, agora)
            if motivo:
                raise ValueError(f"Pedido já existente na bronze não cumpre o contrato (id={linha.get('id')}): {motivo}")
            bronze.execute(
                "INSERT INTO silver_pedidos VALUES (?,?,?,?,?,?,?,?,?)",
                (norm["id"], norm["cliente_id"], norm["valor_centavos"], norm["status"],
                 norm["criado_em"].isoformat(), norm.get("atualizado_em"), norm.get("observacao"), execucao, contrato["conjunto"] + ":" + str(contrato["versao"])),
            )
            validos_base += 1
        aceitos, rejeitados, motivos = 0, 0, []
        for linha_lote_id, linha in zip(ids_lote, lote):
            linha = {k: (None if v == "" else v) for k, v in linha.items()}
            motivo, norm = validar_linha(linha, contrato, vistos, agora)
            if motivo:
                bronze.execute(
                    "INSERT INTO quarentena_pedidos (execucao,lote,linha_lote,id,cliente_id,valor_centavos,status,criado_em,observacao,motivo) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (execucao, LOTE.name, linha_lote_id, int(linha["id"]),
                     int(linha["cliente_id"]) if linha["cliente_id"] else None,
                     int(linha["valor_centavos"]) if linha["valor_centavos"] else 0,
                     linha["status"], linha["criado_em"], linha["observacao"], motivo),
                )
                rejeitados += 1
                motivos.append((int(linha["id"]), motivo))
                continue
            bronze.execute(
                "INSERT INTO silver_pedidos VALUES (?,?,?,?,?,?,?,?,?)",
                (norm["id"], norm["cliente_id"], norm["valor_centavos"], norm["status"],
                 norm["criado_em"].isoformat(), None, norm.get("observacao"), execucao,
                 contrato["conjunto"] + ":" + str(contrato["versao"])),
            )
            aceitos += 1
        receita_centavos = bronze.execute(
            "SELECT COALESCE(SUM(valor_centavos),0) FROM silver_pedidos WHERE status='pago'"
        ).fetchone()[0]
        receita_sem_validacao = bronze.execute(
            "SELECT COALESCE(SUM(valor_centavos),0) FROM pedidos WHERE status='pago'"
        ).fetchone()[0] + sum(int(x["valor_centavos"]) for x in lote if x["status"] == "pago")
        bronze.commit()
        resultado = {
            "execucao": execucao, "contrato": f'{contrato["conjunto"]} v{contrato["versao"]}',
            "pedidos_base": validos_base, "linhas_lote": len(lote), "aceitos": aceitos,
            "quarentena": rejeitados, "total_silver": validos_base + aceitos,
            "receita_paga_centavos": receita_centavos,
            "receita_sem_validacao_centavos": receita_sem_validacao,
            "motivos": motivos,
        }
        return resultado
    except Exception:
        bronze.rollback()
        raise
    finally:
        bronze.close()


def reais(centavos):
    return f"R$ {centavos // 100:,.0f}".replace(",", ".") + f",{centavos % 100:02d}"


if __name__ == "__main__":
    r = executar()
    print(f"Contrato: {r['contrato']} | execução: {r['execucao']}")
    print(f"Pedidos existentes validados: {r['pedidos_base']}")
    print(f"Lote: {r['linhas_lote']} | aceitos: {r['aceitos']} | quarentena: {r['quarentena']}")
    print(f"Silver: {r['total_silver']} pedidos | receita paga: {reais(r['receita_paga_centavos'])}")
    print(f"Sem validação: {reais(r['receita_sem_validacao_centavos'])}")
    for pedido, motivo in r["motivos"]:
        print(f"Pedido {pedido}: {motivo}")
