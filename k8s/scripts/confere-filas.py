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

# Fila que existe no broker e NAO aparece em ConfigMap nenhum, de proposito.
# Cada uma precisa de um motivo escrito aqui: sem isso, a conferencia vira um
# check vermelho cronico e todo mundo aprende a ignorar, que e pior do que nao
# ter check nenhum.
SEM_REFERENCIA_DE_PROPOSITO = {
    "billing.aguardando-aprovacao":
        "sala de espera do ADR-0010: a mensagem fica parada ate o TTL de 7 dias "
        "vencer e o dead-letter manda para billing.aprovacao-expirada. "
        "Consumidor nela quebraria o timeout.",
    "os.saga.eventos":
        "o nome e constante no ConsumirEventosSaga do OS Service, nao vem de "
        "env. Declarar a chave no ConfigMap daria a impressao de que mudar o "
        "valor ali muda a fila consumida, e nao muda.",
    "os.readmodel.eventos":
        "sem consumidor nesta fase: o projetor do read model nao existe ainda "
        "(ADR-0009). Por isso ela e limitada em x-max-length 10000 com "
        "drop-head e TTL de 24h — fila ligada ao exchange sem ninguem drenando "
        "cresce para sempre e, no limite de memoria, o RabbitMQ BLOQUEIA os "
        "publicadores e para a saga dos tres servicos.",
}


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
            # A chave nao precisa COMECAR com FILA_/EXCHANGE_: a execucao usa
            # RABBITMQ_FILA_ENVIAR e RABBITMQ_EXCHANGE_EVENTOS. Ancorar no
            # inicio fazia o script ignorar os dois e dizer que as filas da
            # execucao nao eram referenciadas por ninguem.
            m = re.match(r'\s+([A-Z0-9_]*(?:FILA|EXCHANGE)[A-Z0-9_]*):\s*"(.+)"', linha)
            if not m:
                continue
            chave, valor = m.group(1), m.group(2)
            alvo = refs_fila if "FILA" in chave else refs_exchange
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
        if not q.startswith("dlq.") and q not in SEM_REFERENCIA_DE_PROPOSITO
    )
    for nome in orfas:
        problemas.append(f"fila '{nome}' existe no broker mas nenhum ConfigMap a referencia")

    print(f"filas no broker: {len(filas)}  |  referenciadas nos manifestos: {len(refs_fila)}")

    toleradas = sorted(SEM_REFERENCIA_DE_PROPOSITO.keys() & filas)
    if toleradas:
        print(f"sem referencia de proposito: {', '.join(toleradas)}")

    fantasmas = sorted(SEM_REFERENCIA_DE_PROPOSITO.keys() - filas)
    for nome in fantasmas:
        problemas.append(
            f"fila '{nome}' esta na lista de excecoes mas nao existe mais no "
            "definitions.json — tire da lista"
        )

    if problemas:
        print()
        for p in problemas:
            print(f"  DIVERGENCIA: {p}")
        return 1

    print("ok: nenhuma divergencia entre os manifestos e a topologia do broker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
