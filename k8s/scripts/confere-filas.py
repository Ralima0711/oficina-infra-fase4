#!/usr/bin/env python3
"""Confere os nomes de fila dos ConfigMaps contra a topologia do RabbitMQ.

O erro que este script pega nao aparece em teste e nao aparece em `kubectl apply`:
o servico sobe, conecta no broker, declara uma fila com nome errado — e fica
consumindo uma fila que ninguem publica. A saga simplesmente para no meio, sem
log de erro. Em producao isso e um incidente; na gravacao do video e pior.

uso:
    python3 scripts/confere-filas.py            # sai 1 se achar divergencia
"""
import json
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
K8S = AQUI.parent

# Fila declarada no broker que NAO tem consumidor por decisao de projeto.
# billing.aguardando-aprovacao e a sala de espera: a mensagem fica parada ate o
# TTL de 7 dias vencer e o dead-letter manda para billing.aprovacao-expirada.
# Consumidor nela quebraria o timeout.
SEM_CONSUMIDOR_DE_PROPOSITO = {"billing.aguardando-aprovacao"}


def acha_raiz_do_repo(inicio: pathlib.Path) -> pathlib.Path | None:
    """Sobe a arvore procurando quem tem rabbitmq/definitions.json.

    Os manifestos vivem em k8s/ dentro do oficina-infra-fase4, e o
    definitions.json fica na raiz do repo. Procurar em vez de fixar o caminho
    deixa o script rodar da raiz ou de dentro de k8s/, sem pegadinha.
    """
    for diretorio in [inicio, *inicio.parents]:
        if (diretorio / "rabbitmq" / "definitions.json").is_file():
            return diretorio
    return None


def main() -> int:
    raiz = acha_raiz_do_repo(AQUI)
    if raiz is None:
        print("ERRO: nao achei rabbitmq/definitions.json subindo a partir de "
              f"{AQUI}", file=sys.stderr)
        return 1

    topo = json.loads((raiz / "rabbitmq" / "definitions.json").read_text(encoding="utf-8"))
    filas = {q["name"] for q in topo.get("queues", [])}
    exchanges = {e["name"] for e in topo.get("exchanges", [])}

    refs_fila: dict[str, str] = {}
    refs_exchange: dict[str, str] = {}
    for arquivo in sorted(K8S.rglob("*-configmap.yaml")):
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\s+(FILA_\w+|EXCHANGE_\w+):\s*"(.+)"', linha)
            if not m:
                continue
            chave, valor = m.group(1), m.group(2)
            alvo = refs_fila if chave.startswith("FILA") else refs_exchange
            alvo[valor] = str(arquivo.relative_to(K8S))

    problemas = []

    for nome, onde in sorted(refs_fila.items()):
        if nome not in filas:
            problemas.append(f"fila '{nome}' referenciada em {onde} nao existe no definitions.json")

    for nome, onde in sorted(refs_exchange.items()):
        if nome not in exchanges:
            problemas.append(f"exchange '{nome}' referenciado em {onde} nao existe no definitions.json")

    orfas = sorted(
        q for q in filas - set(refs_fila)
        if not q.startswith("dlq.") and q not in SEM_CONSUMIDOR_DE_PROPOSITO
    )
    for nome in orfas:
        problemas.append(f"fila '{nome}' existe no broker mas nenhum ConfigMap a referencia")

    print(f"filas no broker: {len(filas)}  |  referenciadas nos manifestos: {len(refs_fila)}")

    if problemas:
        print()
        for p in problemas:
            print(f"  DIVERGENCIA: {p}")
        return 1

    print("ok: nenhuma divergencia entre os manifestos e a topologia do broker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
